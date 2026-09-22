"""Общий per-barrier advisory lock + канонический lock-ключ (§13.2).

Создание ``pending_review`` (ingestion), его резолюция, самостоятельный
``manual-open`` и review-expiry сериализуются ОДНОЙ PostgreSQL
transaction-level advisory lock — это исключает гонки «две команды на один
barrier» и «резолюция уже просроченного».

Канонический ключ (H1/L3) — ОДИН источник для всех путей, по АВТОРИТЕТНОМУ
порядку: активный ``barrier_id`` → иначе ``gate_id`` события → иначе
``controller_id``. Для одного физического barrier/gate все пути берут один и тот
же ключ, даже если barrier деактивирован после приёма события (тогда падаем на
``gate_id``). На не-postgres (sqlite CI/dev) lock — корректный no-op.

A9-P3-23: ключ — пара ``(namespace, id)`` → ``pg_advisory_xact_lock(int4, int4)``.
Раньше barrier/gate/controller делили одно пространство bigint-ключей: barrier 7,
gate 7 и controller 7 сериализовались друг с другом, а однопараметрические ключи
пересекались с чужими advisory-локами той же БД (hash-chain crc32, UK-ядро).
Двухпараметрическая форма — отдельное пространство (objsubid=2 в ``pg_locks``).
"""
from __future__ import annotations

import logging

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

# Пространства ключей advisory-lock (§13.2). Значения произвольны, но стабильны:
# это контракт сериализации между путями и воркерами — не менять без ревью.
LOCK_NS_BARRIER = 0x41430001
LOCK_NS_GATE = 0x41430002
LOCK_NS_CONTROLLER = 0x41430003

# Вторая половина ключа — int4; id (BIGINT identity) сворачиваем в диапазон int4.
# Коллизия возможна только для id ≥ 2^31 — это лишняя сериализация, не потеря.
_INT4_MASK = 0x7FFFFFFF

LockKey = tuple[int, int]


def _key(namespace: int, entity_id: int) -> LockKey:
    return (namespace, int(entity_id) & _INT4_MASK)


def _is_postgres(db: Session) -> bool:
    """Надёжно определить, postgres ли это (H2): без тихого пропуска lock.

    Диалект инспектируется через ``bind`` сессии. На ``postgresql`` — True (берём
    lock), на ``sqlite`` — False (корректный no-op). Если диалект на не-sqlite
    определить нельзя — НЕ молчим: ``logger.warning`` и трактуем как no-op, чтобы
    не выполнить ``pg_advisory_xact_lock`` на чужом диалекте.
    """
    try:
        bind = db.get_bind()
    except Exception:  # noqa: BLE001 — диагностика, не падаем на выборе lock
        bind = None
    dialect = getattr(bind, "dialect", None)
    name = getattr(dialect, "name", None)
    if name == "postgresql":
        return True
    if name == "sqlite":
        return False
    logger.warning(
        "advisory lock: неопределённый диалект %r (bind=%r) — lock пропущен как "
        "no-op (§13.2)",
        name,
        bind,
    )
    return False


def canonical_lock_key(
    barrier_id: int | None, gate_id: int | None, controller_id: int | None
) -> LockKey | None:
    """Канонический lock-ключ §13.2: barrier_id → gate_id → controller_id.

    ЕДИНЫЙ источник приоритета для ingestion/resolve/manual-open/expiry: один и
    тот же физический barrier/gate всегда даёт один ключ. Каждый уровень — в
    своём пространстве (A9-P3-23), ``None`` — нечего лочить.
    """
    if barrier_id:
        return _key(LOCK_NS_BARRIER, barrier_id)
    if gate_id:
        return _key(LOCK_NS_GATE, gate_id)
    if controller_id:
        return _key(LOCK_NS_CONTROLLER, controller_id)
    return None


def advisory_xact_lock(db: Session, key: LockKey | None) -> None:
    """Взять transaction-level advisory lock по ключу ``(namespace, id)`` (§13.2).

    Только postgres; на sqlite/неизвестном диалекте — no-op (см. ``_is_postgres``).
    ``key is None`` — нечего лочить (вызывающий обязан проверить заранее).
    """
    if key is None:
        return
    if not _is_postgres(db):
        return
    namespace, entity = key
    db.execute(
        text("SELECT pg_advisory_xact_lock(:ns, :id)"),
        {"ns": int(namespace), "id": int(entity)},
    )


def barrier_advisory_lock(db: Session, barrier_id: int) -> None:
    """Lock по ``barrier_id`` (§13.2). Тонкая обёртка над ``advisory_xact_lock``.

    Используется на путях, где известен активный barrier_id напрямую
    (manual_open_barrier по path-параметру). Тот же ключ, что у ingestion, когда
    barrier активен.
    """
    advisory_xact_lock(db, canonical_lock_key(barrier_id, None, None))


def lock_key_for_event(db: Session, camera_event_id: int) -> LockKey | None:
    """Канонический lock-ключ события по АВТОРИТЕТНОМУ источнику (§13.2).

    ``LEFT JOIN`` на активный barrier: если barrier деактивирован после приёма —
    ключ падает на ``gate_id`` события (а не теряется), сохраняя сериализацию с
    ingestion/worker по тому же физическому проезду.
    """
    row = db.execute(
        text(
            "SELECT b.id AS barrier_id, ce.gate_id, ce.controller_id "
            "FROM camera_events ce "
            "LEFT JOIN access_barriers b "
            "  ON b.gate_id = ce.gate_id AND b.is_active = true "
            "WHERE ce.id = :e "
            "ORDER BY b.id NULLS LAST LIMIT 1"
        ),
        {"e": camera_event_id},
    ).first()
    if row is None:
        return None
    return canonical_lock_key(row[0], row[1], row[2])
