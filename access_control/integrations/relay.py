"""Relay adapter: физическое открытие шлагбаума (§14.2 п.11, §9.2).

``RelayAdapter`` — Protocol с ``open(command)``. ``MockRelay`` для тестов/стенда
считает физические открытия по ``command_id`` и ДЕДУПЛИЦИРУЕТ повтор: реле
срабатывает не более одного раза на ``command_id`` (§9.2), повторный вызов
возвращает сохранённый результат. ``HTTPRelay`` — тонкий скелет под реальный
edge-relay (конфигурируемый URL); в тестах реального вызова не делает.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, replace
from typing import Any, Protocol

from access_control.services.metrics import observe_relay


@dataclass(frozen=True)
class RelayCommand:
    """Команда на физическое открытие, подаваемая в relay-адаптер."""

    command_id: str
    barrier_id: int
    command_type: str = "open_barrier"


@dataclass(frozen=True)
class RelayResult:
    """Результат обращения к реле. ``deduplicated`` — повтор того же command_id."""

    command_id: str
    opened: bool
    deduplicated: bool = False
    detail: str | None = None


class RelayAdapter(Protocol):
    """Контракт адаптера реле (§14.2 п.11)."""

    def open(self, command: RelayCommand) -> RelayResult:  # pragma: no cover
        ...


class MockRelay:
    """In-memory реле: дедуп по command_id, счётчик физических открытий (§9.2).

    Моделирует инвариант edge «исполняет реле не более одного раза»: повторный
    ``open`` того же ``command_id`` не открывает реле второй раз и возвращает
    сохранённый результат с ``deduplicated=True``.
    """

    def __init__(self) -> None:
        # Все вызовы open (для наблюдаемости тестов).
        self.calls: list[str] = []
        # Сохранённый результат на command_id (idempotent replay).
        self._results: dict[str, RelayResult] = {}
        # Число ФИЗИЧЕСКИХ открытий на command_id (дедуп держит ≤1).
        self._opens: dict[str, int] = {}

    def open(self, command: RelayCommand) -> RelayResult:
        cid = command.command_id
        self.calls.append(cid)
        saved = self._results.get(cid)
        if saved is not None:
            # Повтор: реле НЕ трогаем, возвращаем сохранённый результат (дедуп не
            # считается физическим открытием — латентность реле не записываем).
            return replace(saved, deduplicated=True)
        # §10.2: измеряем латентность ФИЗИЧЕСКОГО открытия реле (фаза relay).
        started = time.perf_counter()
        self._opens[cid] = self._opens.get(cid, 0) + 1
        result = RelayResult(command_id=cid, opened=True, deduplicated=False)
        self._results[cid] = result
        observe_relay((time.perf_counter() - started) * 1000.0)
        return result

    def open_count(self, command_id: str) -> int:
        """Число физических открытий реле по command_id (0 или 1 при дедупе)."""
        return self._opens.get(command_id, 0)


class HTTPRelay:
    """Тонкий скелет HTTP-реле (§14.2 п.11). Реальный вызов — не в тестах.

    Требует явно переданного HTTP-клиента (duck-typed: ``.post(url, json, timeout)``);
    без него ``open`` поднимает ``RuntimeError`` — так тесты не делают сетевых
    вызовов, а прод-конфигурация инжектит клиент. Полная интеграция с конкретным
    контроллером реле — после обследования (§14.2 п.4).
    """

    def __init__(
        self, base_url: str, *, client: Any | None = None, timeout: float = 1.5
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout

    def open(self, command: RelayCommand) -> RelayResult:
        if self._client is None:
            raise RuntimeError(
                "HTTPRelay требует HTTP-клиент (прод/Ф6); в пилотных тестах не вызывается"
            )
        # §10.2: латентность физического открытия реле (фаза relay).
        started = time.perf_counter()
        resp = self._client.post(
            f"{self._base_url}/open",
            json={
                "command_id": command.command_id,
                "barrier_id": command.barrier_id,
                "command_type": command.command_type,
            },
            timeout=self._timeout,
        )
        observe_relay((time.perf_counter() - started) * 1000.0)
        opened = getattr(resp, "status_code", None) == 200
        return RelayResult(
            command_id=command.command_id,
            opened=opened,
            detail=f"http {getattr(resp, 'status_code', '?')}",
        )
