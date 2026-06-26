"""Резолюция manual_review и самостоятельное ручное открытие (§9.5, §13.2).

Сервисный слой Ф5. Всё выполняется под per-barrier advisory lock (§13.2), общим с
ingestion: создание pending, его резолюция, самостоятельный manual-open и expiry
сериализуются по ``barrier_id``.

Append-only (решение CTO #3): переходы lifecycle — НОВЫЕ строки access_decisions
(``decision_group_id`` + ``supersedes_decision_id``), не UPDATE. Триггер §9.7
запрещает UPDATE/DELETE. Каждая новая строка получает hash-chain (§9.7).

Идемпотентность (§9.5): после терминального перехода повторная резолюция
возвращает СОХРАНЁННЫЙ результат, не создавая второй переход/команду. Lazy
expiry: если pending просрочен, resolve сначала переводит его в expired (под lock),
и резолюция становится невозможна — остановка worker не даёт обработать
просроченное.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from access_control.domain.audit import AccessAuditLog, ManualOpening
from access_control.domain.commands import BarrierCommand
from access_control.domain.enums import (
    CommandStatus,
    CommandType,
    DecisionStatus,
    DecisionType,
)
from access_control.domain.events import AccessDecision
from access_control.services.event_broadcaster import AccessEventMessage, get_broker
from access_control.services.hashchain import next_hash
from access_control.services.locks import (
    advisory_xact_lock,
    barrier_advisory_lock,
    lock_key_for_event,
)

# TTL ручной команды открытия (§9.2): согласован с ingestion DEFAULT_COMMAND_TTL.
MANUAL_COMMAND_TTL_SECONDS = 120

RESOLVE_ACTIONS = ("manual_open", "deny")


# --------------------------- исключения/DTO ---------------------------


class NoPendingReviewError(Exception):
    """Нет активного pending_review для резолюции по событию (§9.5)."""


class InvalidResolveAction(Exception):
    """Недопустимое действие резолюции или отсутствуют обязательные поля (§13.2)."""


class UnknownBarrierError(Exception):
    """Шлагбаум не найден/неактивен — самостоятельный manual-open невозможен."""


class PendingReviewConflict(Exception):
    """Прямой manual-open при активном pending_review (§13.2): 409 + event_id."""

    def __init__(self, event_id: int) -> None:
        super().__init__(f"active pending_review exists for event {event_id}")
        self.event_id = event_id


class DecisionIdMismatch(Exception):
    """Переданный decision_id не совпадает с текущим pending решением (§9.5): 409.

    Идемпотентность резолюции — по event И decision: если оператор шлёт чужой/
    устаревший decision_id для активного pending, действие отклоняется.
    """


class BarrierUnavailableError(Exception):
    """Barrier деактивирован после приёма события — manual_open невозможен (M3/M4).

    Команда требует ``controller_id`` (NOT NULL); если активного barrier для
    события больше нет, не падаем в БД и не залипаем в pending — возвращаем
    понятную ошибку, а pending остаётся для worker/lazy-expiry (истечёт по
    deadline, либо оператор может ``deny``).
    """


@dataclass(frozen=True)
class ResolveResult:
    """Результат резолюции: терминальный статус + (для manual_open) команда."""

    status: str
    decision_id: int
    decision_group_id: str
    command_id: str | None
    replayed: bool


@dataclass(frozen=True)
class ManualOpenResult:
    """Результат самостоятельного ручного открытия."""

    manual_opening_id: int
    command_id: str
    barrier_id: int


@dataclass(frozen=True)
class _CommandRef:
    command_id: str
    barrier_id: int
    expires_at: dt.datetime | None


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _publish_lifecycle_event(
    *, decision: str, status: str, reason: str | None, now: dt.datetime
) -> None:
    """Опубликовать PD-safe событие смены статуса в WS-брокер (§9.6, §11).

    Best-effort: сбой брокера не влияет на уже зафиксированный переход. Номер/фото
    не передаются (§11) — только исход. Вызывается ПОСЛЕ commit.
    """
    try:
        get_broker().publish(
            AccessEventMessage(
                decision=decision,
                status=status,
                reason=reason,
                occurred_at=now.isoformat(),
            )
        )
    except Exception:  # noqa: BLE001 — трансляция не критична
        pass


# --------------------------- чтение состояния ---------------------------


def _barrier_and_controller_for_event(
    db: Session, camera_event_id: int
) -> tuple[int | None, int | None]:
    """Авторитетный barrier/controller события (по gate камеры), не из payload."""
    row = db.execute(
        text(
            "SELECT b.id, b.controller_id "
            "FROM camera_events ce "
            "JOIN access_barriers b ON b.gate_id = ce.gate_id AND b.is_active = true "
            "WHERE ce.id = :e ORDER BY b.id LIMIT 1"
        ),
        {"e": camera_event_id},
    ).first()
    return (row[0], row[1]) if row is not None else (None, None)


def _controller_for_barrier(db: Session, barrier_id: int) -> int | None:
    return db.execute(
        text(
            "SELECT controller_id FROM access_barriers "
            "WHERE id = :b AND is_active = true"
        ),
        {"b": barrier_id},
    ).scalar()


def _current_decision(db: Session, camera_event_id: int) -> AccessDecision | None:
    """Текущая (не замещённая) строка группы решений события.

    Транзишн всегда имеет больший id, чем замещаемая строка, поэтому ``max(id)``
    группы события = «текущее» решение.
    """
    return (
        db.query(AccessDecision)
        .filter(AccessDecision.camera_event_id == camera_event_id)
        .order_by(AccessDecision.id.desc())
        .first()
    )


def _active_pending_event_for_barrier(
    db: Session, barrier_id: int, now: dt.datetime
) -> int | None:
    """camera_event_id активного (несовершённого, несгоревшего) pending по barrier."""
    return db.execute(
        text(
            "SELECT ad.camera_event_id "
            "FROM access_decisions ad "
            "JOIN camera_events ce ON ce.id = ad.camera_event_id "
            "JOIN access_barriers b ON b.gate_id = ce.gate_id "
            "WHERE b.id = :barrier "
            "  AND ad.status = 'pending_review' "
            "  AND ad.id = (SELECT max(id) FROM access_decisions "
            "               WHERE camera_event_id = ad.camera_event_id) "
            "  AND (ad.review_deadline_at IS NULL OR ad.review_deadline_at >= :now) "
            "ORDER BY ad.id DESC LIMIT 1"
        ),
        {"barrier": barrier_id, "now": now},
    ).scalar()


# --------------------------- запись (append-only) ---------------------------


def _write_transition(
    db: Session,
    *,
    current: AccessDecision,
    new_status: str,
    new_decision: str,
    operator_user_id: int | None,
    now: dt.datetime,
) -> AccessDecision:
    """Append-строка перехода lifecycle: supersedes текущую, hash-chain (§9.5, §9.7).

    ``source`` решения наследуется от исходного события (connected|edge_offline,
    §8.4) — это происхождение события, а не актор. Оператор/worker фиксируются в
    ``resolved_by_user_id`` и в access_audit_logs (audit source).
    """
    payload = {
        "camera_event_id": current.camera_event_id,
        "decision_group_id": str(current.decision_group_id),
        "supersedes_decision_id": current.id,
        "decision": new_decision,
        "status": new_status,
        "reason": current.reason,
        "source": current.source,
    }
    prev_hash, row_hash = next_hash(db, "access_decisions", payload)
    row = AccessDecision(
        camera_event_id=current.camera_event_id,
        decision_group_id=current.decision_group_id,
        supersedes_decision_id=current.id,
        decision=new_decision,
        status=new_status,
        reason=current.reason,
        matched_vehicle_id=current.matched_vehicle_id,
        matched_pass_id=current.matched_pass_id,
        review_deadline_at=None,
        resolved_by_user_id=operator_user_id,
        resolved_at=now,
        source=current.source,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )
    db.add(row)
    db.flush()
    return row


def _create_command(
    db: Session,
    *,
    controller_id: int,
    barrier_id: int,
    decision_id: int | None,
    ttl_seconds: int = MANUAL_COMMAND_TTL_SECONDS,
) -> _CommandRef:
    """Создать команду открытия в durable outbox (§9.2).

    ``decision_id`` задан (manual_open) — идемпотентно по ``UNIQUE(decision_id)``;
    ``decision_id`` NULL (самостоятельный manual-open) — каждая операция = новая
    команда (нет ключа идемпотентности, ручные открытия независимы).
    """
    expires_at = _utcnow() + dt.timedelta(seconds=ttl_seconds)
    new_command_id = uuid.uuid4()
    base = pg_insert(BarrierCommand.__table__).values(
        command_id=new_command_id,
        decision_id=decision_id,
        controller_id=controller_id,
        barrier_id=barrier_id,
        command_type=CommandType.OPEN_BARRIER.value,
        status=CommandStatus.PENDING.value,
        expires_at=expires_at,
    )
    if decision_id is not None:
        stmt = base.on_conflict_do_nothing(
            index_elements=["decision_id"],
            index_where=text("decision_id IS NOT NULL"),
        ).returning(BarrierCommand.__table__.c.command_id)
        inserted = db.execute(stmt).scalar()
        if inserted is None:
            existing = (
                db.query(BarrierCommand)
                .filter(BarrierCommand.decision_id == decision_id)
                .first()
            )
            return _CommandRef(
                command_id=str(existing.command_id),
                barrier_id=existing.barrier_id,
                expires_at=existing.expires_at,
            )
        return _CommandRef(str(new_command_id), barrier_id, expires_at)
    db.execute(base)
    return _CommandRef(str(new_command_id), barrier_id, expires_at)


def _write_manual_opening(
    db: Session,
    *,
    barrier_id: int,
    command_id: str,
    decision_id: int | None,
    operator_user_id: int,
    reason: str,
    captured_event_id: int | None,
) -> int:
    """Append-строка manual_openings с hash-chain (§9.5, §9.7)."""
    payload = {
        "barrier_id": barrier_id,
        "command_id": command_id,
        "decision_id": decision_id,
        "operator_user_id": operator_user_id,
        "reason": reason,
        "captured_event_id": captured_event_id,
    }
    prev_hash, row_hash = next_hash(db, "manual_openings", payload)
    row = ManualOpening(
        barrier_id=barrier_id,
        command_id=uuid.UUID(command_id),
        decision_id=decision_id,
        operator_user_id=operator_user_id,
        reason=reason,
        captured_event_id=captured_event_id,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )
    db.add(row)
    db.flush()
    return row.id


def _write_audit(
    db: Session,
    *,
    actor_user_id: int | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    barrier_id: int | None,
    source: str,
    reason: str | None,
    ip_address: str | None = None,
    extra_details: dict | None = None,
) -> None:
    """Append-строка access_audit_logs с hash-chain (§9.7, §6.3).

    ``ip_address`` (§6.3) фиксирует источник запроса оператора. ``extra_details``
    дополняет ``details`` (например ``triggered_by_user_id`` для system-действий,
    где ``actor_user_id`` = None). IP включён в hash-payload — tamper-evident.
    """
    details = {"barrier_id": barrier_id, "source": source, "reason": reason}
    if extra_details:
        details.update(extra_details)
    payload = {
        "actor_user_id": actor_user_id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": str(entity_id) if entity_id is not None else None,
        "details": details,
        "ip_address": ip_address,
    }
    prev_hash, row_hash = next_hash(db, "access_audit_logs", payload)
    db.add(
        AccessAuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=str(entity_id) if entity_id is not None else None,
            details=details,
            ip_address=ip_address,
            prev_hash=prev_hash,
            row_hash=row_hash,
        )
    )


def _replay_result(db: Session, current: AccessDecision) -> ResolveResult:
    """Сохранённый результат уже терминального решения (idempotent replay, §9.5)."""
    command_id = None
    if current.status == DecisionStatus.ALLOWED_MANUALLY.value:
        cmd = (
            db.query(BarrierCommand)
            .filter(BarrierCommand.decision_id == current.id)
            .first()
        )
        command_id = str(cmd.command_id) if cmd is not None else None
    return ResolveResult(
        status=current.status,
        decision_id=current.id,
        decision_group_id=str(current.decision_group_id),
        command_id=command_id,
        replayed=True,
    )


# --------------------------- публичные операции ---------------------------


def resolve_event(
    db: Session,
    *,
    event_id: int,
    action: str,
    operator_user_id: int,
    reason: str | None = None,
    barrier_id: int | None = None,
    decision_id: int | None = None,
    source: str = "operator_resolve",
    ip_address: str | None = None,
    now: dt.datetime | None = None,
) -> ResolveResult:
    """Зарезолвить manual_review: manual_open | deny (§9.5, §13.2).

    Под per-barrier advisory lock: lazy-expiry просроченного pending, идемпотентный
    replay терминального решения, иначе append-переход + (для manual_open) durable
    команда и manual_opening. Все ветви — append-only.
    """
    now = now or _utcnow()
    if action not in RESOLVE_ACTIONS:
        raise InvalidResolveAction(f"unknown action {action!r}")

    derived_barrier, controller_id = _barrier_and_controller_for_event(db, event_id)
    # H1/L3: lock-ключ — по АВТОРИТЕТНОМУ источнику события (активный barrier →
    # gate → controller), НЕ из тела запроса. Тот же ключ, что у ingestion/worker.
    lock_key = lock_key_for_event(db, event_id)
    if lock_key is None:
        db.rollback()
        raise NoPendingReviewError(f"no barrier resolvable for event {event_id}")
    advisory_xact_lock(db, lock_key)

    current = _current_decision(db, event_id)
    if current is None:
        db.commit()
        raise NoPendingReviewError(f"no decision for event {event_id}")

    # Lazy expiry (§9.5): просроченный pending → expired ДО любой резолюции.
    if (
        current.status == DecisionStatus.PENDING_REVIEW.value
        and current.review_deadline_at is not None
        and current.review_deadline_at < now
    ):
        expired = _write_transition(
            db,
            current=current,
            new_status=DecisionStatus.EXPIRED.value,
            new_decision=DecisionType.MANUAL_REVIEW.value,
            operator_user_id=None,
            now=now,
        )
        # L4: lazy-expiry — системное действие (actor=None); инициатора фиксируем
        # в details.triggered_by_user_id, не как actor (он не «истёк» решение).
        _write_audit(
            db,
            actor_user_id=None,
            action="access.review_expired_lazy",
            entity_type="access_decision",
            entity_id=expired.id,
            barrier_id=derived_barrier,
            source=source,
            reason=None,
            ip_address=ip_address,
            extra_details={"triggered_by_user_id": operator_user_id},
        )
        db.commit()
        return ResolveResult(
            status=DecisionStatus.EXPIRED.value,
            decision_id=expired.id,
            decision_group_id=str(current.decision_group_id),
            command_id=None,
            replayed=False,
        )

    # Уже терминально → идемпотентный сохранённый результат.
    if current.status != DecisionStatus.PENDING_REVIEW.value:
        result = _replay_result(db, current)
        db.commit()
        return result

    # M5: идемпотентность по event И decision — переданный decision_id обязан
    # совпасть с текущим pending. Проверяем только для активного pending (на replay
    # current.id уже = id перехода, а не исходного pending — там сверка не нужна).
    if decision_id is not None and decision_id != current.id:
        db.rollback()
        raise DecisionIdMismatch(
            f"decision_id {decision_id} mismatch (current pending {current.id})"
        )

    # Активный pending → выполнить действие (append-only переход).
    if action == "manual_open":
        if not (reason and reason.strip()) or barrier_id is None or decision_id is None:
            db.rollback()
            raise InvalidResolveAction(
                "manual_open requires reason, barrier_id and decision_id"
            )
        # M3/M4: barrier деактивирован после приёма → активного barrier/controller
        # нет. Команда NOT NULL по controller_id — не падаем в БД и не залипаем в
        # pending: откатываем и сообщаем ошибку. Pending останется (worker/lazy
        # expiry истечёт по deadline; либо оператор может deny без команды).
        if derived_barrier is None or controller_id is None:
            db.rollback()
            raise BarrierUnavailableError(
                f"barrier for event {event_id} inactive — manual_open impossible"
            )
        new = _write_transition(
            db,
            current=current,
            new_status=DecisionStatus.ALLOWED_MANUALLY.value,
            new_decision=DecisionType.ALLOW.value,
            operator_user_id=operator_user_id,
            now=now,
        )
        command = _create_command(
            db,
            controller_id=controller_id,
            barrier_id=derived_barrier,
            decision_id=new.id,
        )
        _write_manual_opening(
            db,
            barrier_id=derived_barrier,
            command_id=command.command_id,
            decision_id=new.id,
            operator_user_id=operator_user_id,
            reason=reason,
            captured_event_id=event_id,
        )
        _write_audit(
            db,
            actor_user_id=operator_user_id,
            action="access.manual_open",
            entity_type="access_decision",
            entity_id=new.id,
            barrier_id=derived_barrier,
            source=source,
            reason=reason,
            ip_address=ip_address,
        )
        db.commit()
        _publish_lifecycle_event(
            decision=DecisionType.ALLOW.value,
            status=DecisionStatus.ALLOWED_MANUALLY.value,
            reason=current.reason,
            now=now,
        )
        return ResolveResult(
            status=DecisionStatus.ALLOWED_MANUALLY.value,
            decision_id=new.id,
            decision_group_id=str(current.decision_group_id),
            command_id=command.command_id,
            replayed=False,
        )

    # deny — фиксация отказа без команды.
    if not (reason and reason.strip()):
        db.rollback()
        raise InvalidResolveAction("deny requires reason")
    new = _write_transition(
        db,
        current=current,
        new_status=DecisionStatus.DENIED_MANUALLY.value,
        new_decision=DecisionType.DENY.value,
        operator_user_id=operator_user_id,
        now=now,
    )
    _write_audit(
        db,
        actor_user_id=operator_user_id,
        action="access.deny",
        entity_type="access_decision",
        entity_id=new.id,
        barrier_id=derived_barrier,
        source=source,
        reason=reason,
        ip_address=ip_address,
    )
    db.commit()
    _publish_lifecycle_event(
        decision=DecisionType.DENY.value,
        status=DecisionStatus.DENIED_MANUALLY.value,
        reason=current.reason,
        now=now,
    )
    return ResolveResult(
        status=DecisionStatus.DENIED_MANUALLY.value,
        decision_id=new.id,
        decision_group_id=str(current.decision_group_id),
        command_id=None,
        replayed=False,
    )


def _lazy_expire_barrier_pending(
    db: Session, barrier_id: int, now: dt.datetime
) -> None:
    """Перевести в expired все просроченные текущие pending этого barrier (§9.5)."""
    rows = db.execute(
        text(
            "SELECT ad.id FROM access_decisions ad "
            "JOIN camera_events ce ON ce.id = ad.camera_event_id "
            "JOIN access_barriers b ON b.gate_id = ce.gate_id "
            "WHERE b.id = :barrier "
            "  AND ad.status = 'pending_review' "
            "  AND ad.review_deadline_at IS NOT NULL "
            "  AND ad.review_deadline_at < :now "
            "  AND ad.id = (SELECT max(id) FROM access_decisions "
            "               WHERE camera_event_id = ad.camera_event_id)"
        ),
        {"barrier": barrier_id, "now": now},
    ).fetchall()
    for (did,) in rows:
        current = db.get(AccessDecision, did)
        if current is None or current.status != DecisionStatus.PENDING_REVIEW.value:
            continue
        _write_transition(
            db,
            current=current,
            new_status=DecisionStatus.EXPIRED.value,
            new_decision=DecisionType.MANUAL_REVIEW.value,
            operator_user_id=None,
            now=now,
        )


def manual_open_barrier(
    db: Session,
    *,
    barrier_id: int,
    operator_user_id: int,
    reason: str,
    source: str,
    ip_address: str | None = None,
    now: dt.datetime | None = None,
) -> ManualOpenResult:
    """Самостоятельное ручное открытие шлагбаума (§13.2): только при отсутствии pending.

    Под per-barrier advisory lock: lazy-expiry просроченных pending, затем повторная
    проверка активного pending → при наличии ``PendingReviewConflict`` (409 + event_id),
    команда НЕ создаётся. Иначе — manual_opening (decision_id NULL) + durable команда
    + audit.

    Known-limitation (принятый риск пилота): standalone manual-open НЕ имеет
    idempotency-key — каждый POST = новая команда/открытие (повтор от клиента
    создаст дубль). Для пилота приемлемо (ручная аварийная операция оператора).
    """
    now = now or _utcnow()
    if not (reason and reason.strip()):
        db.rollback()
        raise InvalidResolveAction("manual-open requires non-empty reason")
    controller_id = _controller_for_barrier(db, barrier_id)
    if controller_id is None:
        db.rollback()
        raise UnknownBarrierError(f"barrier {barrier_id} not found/inactive")

    barrier_advisory_lock(db, barrier_id)
    _lazy_expire_barrier_pending(db, barrier_id, now)
    active_event = _active_pending_event_for_barrier(db, barrier_id, now)
    if active_event is not None:
        db.commit()
        raise PendingReviewConflict(active_event)

    command = _create_command(
        db, controller_id=controller_id, barrier_id=barrier_id, decision_id=None
    )
    mo_id = _write_manual_opening(
        db,
        barrier_id=barrier_id,
        command_id=command.command_id,
        decision_id=None,
        operator_user_id=operator_user_id,
        reason=reason,
        captured_event_id=None,
    )
    _write_audit(
        db,
        actor_user_id=operator_user_id,
        action="access.barrier_manual_open",
        entity_type="access_barrier",
        entity_id=barrier_id,
        barrier_id=barrier_id,
        source=source,
        reason=reason,
        ip_address=ip_address,
    )
    db.commit()
    _publish_lifecycle_event(
        decision=DecisionType.ALLOW.value,
        status=DecisionStatus.ALLOWED_MANUALLY.value,
        reason="barrier_manual_open",
        now=now,
    )
    return ManualOpenResult(
        manual_opening_id=mo_id, command_id=command.command_id, barrier_id=barrier_id
    )
