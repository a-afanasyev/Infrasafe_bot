"""Health/latency-метрики домена контроля доступа (§10.2, §14.2 п.17).

ТЗ §10.2 требует измерять задержку РАЗДЕЛЬНО по фазам обработки:

* ``ingestion`` — полный приём ANPR-события backend'ом (приём→решение→запись);
* ``decision`` — чистый прогон Decision Engine (§7 шаги 4–8);
* ``db``       — запись транзакции (commit round-trip к PostgreSQL);
* ``relay``    — физическое открытие реле (edge-сторона, §9.2).

Бюджеты §10.2 (локальная сеть пилота):

* p95 decision ≤ 500 мс, p99 decision ≤ 1000 мс;
* p95 edge→реле ≤ 1500 мс.

Реализация двойная и лёгкая:

1. ``LatencyRegistry`` — in-process кольцевой буфер сэмплов на фазу с точными
   перцентилями (p50/p95/p99/max). Нужен для JSON-эндпоинта и проверки бюджета
   §15.16 (prometheus-гистограммы дают только бакеты, не точный перцентиль).
2. Зеркало в ``prometheus_client`` (выделенный ``CollectorRegistry``) — для
   scrape ``GET /metrics`` в текстовом формате Prometheus.

ПД (§11): метки метрик НЕ содержат номер/код/фото — только имя фазы и (для
очереди команд) числовой ``controller_id``. Номер автомобиля сюда не попадает.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass

from prometheus_client import CONTENT_TYPE_LATEST  # noqa: F401  (реэкспорт для роутера)
from prometheus_client import (
    CollectorRegistry,
    Gauge,
    Histogram,
    generate_latest,
)

# Бюджеты задержки §10.2 (миллисекунды). Используются JSON-эндпоинтом и тестом
# §15.16 для отметки breach. Конфигурируемого порога CI здесь нет — мягкий порог
# задаёт сам тест (среда CI медленнее локальной сети пилота).
DECISION_P95_BUDGET_MS = 500.0
DECISION_P99_BUDGET_MS = 1000.0
EDGE_RELAY_P95_BUDGET_MS = 1500.0

# Канонические имена фаз (метка ``phase`` без ПД).
PHASE_INGESTION = "ingestion"
PHASE_DECISION = "decision"
PHASE_DB = "db"
PHASE_RELAY = "relay"
_PHASES = (PHASE_INGESTION, PHASE_DECISION, PHASE_DB, PHASE_RELAY)

# Бакеты prometheus-гистограмм в СЕКУНДАХ (конвенция prometheus): покрывают
# суб-миллисекунды… секунды, с границами на бюджетах 0.5/1.0/1.5 c.
_LATENCY_BUCKETS_SECONDS = (
    0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 1.5, 2.5, 5.0,
)

# Выделенный реестр: не засоряем глобальный default-registry prometheus и
# избегаем коллизий при повторном импорте/сборке приложения в тестах.
REGISTRY = CollectorRegistry()

_LATENCY_HISTOGRAM = Histogram(
    "access_phase_latency_seconds",
    "Задержка обработки по фазе домена контроля доступа (§10.2).",
    labelnames=("phase",),
    buckets=_LATENCY_BUCKETS_SECONDS,
    registry=REGISTRY,
)

_QUEUE_AGE_GAUGE = Gauge(
    "access_barrier_queue_age_seconds",
    "Возраст самой старой pending-команды barrier_commands (§9.2).",
    labelnames=("controller_id",),
    registry=REGISTRY,
)
_QUEUE_PENDING_GAUGE = Gauge(
    "access_barrier_queue_pending",
    "Число pending-команд barrier_commands (§9.2).",
    labelnames=("controller_id",),
    registry=REGISTRY,
)
_QUEUE_LEASED_GAUGE = Gauge(
    "access_barrier_queue_leased",
    "Число leased-команд barrier_commands (§9.2).",
    labelnames=("controller_id",),
    registry=REGISTRY,
)
_QUEUE_DEAD_GAUGE = Gauge(
    "access_barrier_queue_dead",
    "Число dead-letter команд barrier_commands (§9.2).",
    labelnames=("controller_id",),
    registry=REGISTRY,
)


def _percentile(sorted_samples: list[float], q: float) -> float:
    """Перцентиль (nearest-rank) по отсортированному списку. ``q`` в [0, 1]."""
    if not sorted_samples:
        return 0.0
    if q <= 0:
        return sorted_samples[0]
    if q >= 1:
        return sorted_samples[-1]
    rank = int(round(q * (len(sorted_samples) - 1)))
    return sorted_samples[rank]


@dataclass(frozen=True)
class PhaseStats:
    """Снимок статистики задержки одной фазы (мс)."""

    count: int
    p50_ms: float
    p95_ms: float
    p99_ms: float
    max_ms: float


class LatencyRegistry:
    """In-process кольцевой буфер сэмплов задержки на фазу с точными перцентилями.

    Потокобезопасен (``threading.Lock``): ``observe`` зовётся из sync-ingestion
    и из relay-адаптеров. Ёмкость на фазу ограничена (``maxlen``) — память не
    растёт неограниченно, перцентили считаются по последнему окну сэмплов.
    """

    def __init__(self, maxlen: int = 2048) -> None:
        self._maxlen = maxlen
        self._samples: dict[str, deque[float]] = {
            phase: deque(maxlen=maxlen) for phase in _PHASES
        }
        self._lock = threading.Lock()

    def observe(self, phase: str, duration_ms: float) -> None:
        """Записать сэмпл задержки (мс) для фазы. Неизвестная фаза создаётся лениво."""
        with self._lock:
            bucket = self._samples.get(phase)
            if bucket is None:
                bucket = deque(maxlen=self._maxlen)
                self._samples[phase] = bucket
            bucket.append(float(duration_ms))

    def stats(self, phase: str) -> PhaseStats:
        """Снимок перцентилей фазы (мс). Пустая фаза → нули."""
        with self._lock:
            data = sorted(self._samples.get(phase, ()))
        return PhaseStats(
            count=len(data),
            p50_ms=round(_percentile(data, 0.50), 3),
            p95_ms=round(_percentile(data, 0.95), 3),
            p99_ms=round(_percentile(data, 0.99), 3),
            max_ms=round(data[-1], 3) if data else 0.0,
        )

    def snapshot(self) -> dict[str, PhaseStats]:
        """Снимок по всем известным фазам."""
        with self._lock:
            phases = list(self._samples.keys())
        return {phase: self.stats(phase) for phase in phases}

    def reset(self) -> None:
        """Очистить все сэмплы (тесты изоляции)."""
        with self._lock:
            for bucket in self._samples.values():
                bucket.clear()


# Процессный синглтон in-memory реестра.
_latency = LatencyRegistry()


def get_latency_registry() -> LatencyRegistry:
    return _latency


def reset_latency_registry() -> None:
    """Сбросить in-memory сэмплы (для тестов)."""
    _latency.reset()


def observe(phase: str, duration_ms: float) -> None:
    """Записать задержку фазы (мс) в in-memory реестр И в prometheus-гистограмму."""
    _latency.observe(phase, duration_ms)
    _LATENCY_HISTOGRAM.labels(phase=phase).observe(duration_ms / 1000.0)


def observe_ingestion(duration_ms: float) -> None:
    observe(PHASE_INGESTION, duration_ms)


def observe_decision(duration_ms: float) -> None:
    observe(PHASE_DECISION, duration_ms)


def observe_db(duration_ms: float) -> None:
    observe(PHASE_DB, duration_ms)


def observe_relay(duration_ms: float) -> None:
    observe(PHASE_RELAY, duration_ms)


@contextmanager
def measure(phase: str):
    """Контекст-таймер: записывает длительность блока (мс) в указанную фазу.

    Использование::

        with measure(PHASE_DECISION):
            engine = decide(...)
    """
    started = time.perf_counter()
    try:
        yield
    finally:
        observe(phase, (time.perf_counter() - started) * 1000.0)


def set_queue_gauges(
    *, controller_id: int, age_seconds: float | None, pending: int, leased: int, dead: int
) -> None:
    """Обновить prometheus-gauge'и очереди команд для контроллера (§9.2).

    ``controller_id`` — числовой id (не ПД). ``age_seconds=None`` (пустая очередь)
    маппится в 0.
    """
    label = str(controller_id)
    _QUEUE_AGE_GAUGE.labels(controller_id=label).set(age_seconds or 0.0)
    _QUEUE_PENDING_GAUGE.labels(controller_id=label).set(pending)
    _QUEUE_LEASED_GAUGE.labels(controller_id=label).set(leased)
    _QUEUE_DEAD_GAUGE.labels(controller_id=label).set(dead)


def budget_report() -> dict:
    """Сводка соответствия бюджету §10.2 по in-memory перцентилям.

    Возвращает PD-safe dict: перцентили по фазам, бюджеты и флаг ``within_budget``.
    Бюджет считается соблюдённым, если по собранным сэмплам decision-p95/p99 и
    relay-p95 не превышают пороги §10.2 (фазы без сэмплов не нарушают бюджет).
    """
    decision = _latency.stats(PHASE_DECISION)
    relay = _latency.stats(PHASE_RELAY)
    breaches: list[str] = []
    if decision.count and decision.p95_ms > DECISION_P95_BUDGET_MS:
        breaches.append("decision_p95")
    if decision.count and decision.p99_ms > DECISION_P99_BUDGET_MS:
        breaches.append("decision_p99")
    if relay.count and relay.p95_ms > EDGE_RELAY_P95_BUDGET_MS:
        breaches.append("relay_p95")
    return {
        "budgets_ms": {
            "decision_p95": DECISION_P95_BUDGET_MS,
            "decision_p99": DECISION_P99_BUDGET_MS,
            "relay_p95": EDGE_RELAY_P95_BUDGET_MS,
        },
        "within_budget": not breaches,
        "breaches": breaches,
    }


def latency_snapshot_payload() -> dict:
    """PD-safe JSON-представление перцентилей по всем фазам + бюджет §10.2."""
    snap = _latency.snapshot()
    return {
        "phases": {
            phase: {
                "count": s.count,
                "p50_ms": s.p50_ms,
                "p95_ms": s.p95_ms,
                "p99_ms": s.p99_ms,
                "max_ms": s.max_ms,
            }
            for phase, s in snap.items()
        },
        "budget": budget_report(),
    }


def prometheus_text() -> bytes:
    """Сериализовать выделенный реестр в текстовый формат Prometheus (для /metrics)."""
    return generate_latest(REGISTRY)
