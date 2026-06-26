"""Идемпотентный ingestion ANPR-события (§7 шаги 1–11, §10.1, §13.2).

Use case приёма: принимает ``AnprIngestInput``, выполняет идемпотентный приём и
атомарную запись решения/расхода/команды, возвращает ``IngestResult``.

Атомарность и идемпотентность:
* всё выполняется в ОДНОЙ транзакции под ``pg_advisory_xact_lock(barrier_id)``
  (§13.2): сериализует приём, ingestion-резолюцию и ручные открытия по шлагбауму;
* приём идемпотентен по ``(controller_id, event_id)`` (§10.1): повтор возвращает
  РАНЕЕ сохранённое решение и команду, БЕЗ новых записей/расхода/команды;
* короткое окно дедупа ``gate+direction+normalized+captured_at`` (10 c) ловит
  дубликаты без стабильного event_id (§10.1);
* taxi-pass расходуется атомарным ``UPDATE ... WHERE used_entries < max_entries``
  (§10.3): блокируется после первого въезда; повтор event_id не инкрементит;
* при ``allow`` создаётся идемпотентная команда в ``barrier_commands``
  (``UNIQUE(decision_id)``), status=pending, command_id=uuid, expires_at;
* append-only таблицы (access_decisions/access_events) получают hash-chain (§9.7);
* ``manual_review`` пишет решение pending_review + review_deadline (now()+120s),
  команду НЕ создаёт (резолюция — Ф5).

Движок (decision_engine) сам в БД не пишет; запись — здесь (§7 шаг 9).
"""
from __future__ import annotations

import datetime as dt
import logging
import time
import uuid
from dataclasses import dataclass, replace

from sqlalchemy import text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from access_control.domain.commands import BarrierCommand
from access_control.domain.enums import (
    CommandStatus,
    CommandType,
    DecisionReason,
    DecisionStatus,
    DecisionType,
    EventSource,
    PassStatus,
)
from access_control.domain.equipment import EdgeController
from access_control.domain.events import AccessDecision, AccessEvent, CameraEvent
from access_control.services.decision_engine import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    AnprDecisionInput,
    EngineDecision,
    decide,
)
from access_control.services.event_broadcaster import (
    AccessEventMessage,
    get_broker,
    mask_plate,
)
from access_control.services.hashchain import next_hash
from access_control.services.locks import advisory_xact_lock, canonical_lock_key
from access_control.services.metrics import (
    PHASE_DB,
    PHASE_DECISION,
    measure,
    observe_ingestion,
)
from access_control.services.normalization import normalize_plate

DEFAULT_DEDUP_WINDOW_SECONDS = 10
DEFAULT_COMMAND_TTL_SECONDS = 120
MANUAL_REVIEW_DEADLINE_SECONDS = 120
# Макс. допустимый дрейф caller-управляемого ``captured_at`` от backend-времени
# (§7, §9.2): больше — момент решения признаётся несвежим и запрос отвергается,
# иначе устаревший ``captured_at`` обходит сроки пропусков/правил. Конфигурируемо
# (endpoint читает env ACCESS_CAPTURED_AT_MAX_SKEW_SECONDS).
DEFAULT_CAPTURED_AT_MAX_SKEW_SECONDS = 300

logger = logging.getLogger(__name__)


def is_captured_at_fresh(
    captured_at: dt.datetime,
    *,
    now: dt.datetime | None = None,
    max_skew_seconds: int = DEFAULT_CAPTURED_AT_MAX_SKEW_SECONDS,
) -> bool:
    """Свеж ли момент события: ``|now - captured_at| <= max_skew_seconds`` (§7, §9.2).

    Защита от caller-управляемого ``captured_at`` как момента решения: устаревший
    (или из будущего) timestamp обходил бы ``valid_until`` пропусков/правил.
    """
    moment = now if now is not None else _utcnow()
    return abs((moment - captured_at).total_seconds()) <= max_skew_seconds


@dataclass(frozen=True)
class AnprIngestInput:
    """Иммутабельный вход ingestion (§7). ``controller_id`` — БД-id контроллера."""

    controller_id: int
    event_id: str
    zone_id: int | None
    gate_id: int | None
    camera_id: int | None
    barrier_id: int | None
    plate_number_original: str | None
    direction: str
    confidence: float | None
    captured_at: dt.datetime
    plate_photo_url: str | None = None
    overview_photo_url: str | None = None
    attributes: dict | None = None
    source: str = EventSource.CONNECTED.value


@dataclass(frozen=True)
class CommandOut:
    """Команда открытия для fast-path ответа (§9.2)."""

    command_id: str
    barrier_id: int
    expires_at: dt.datetime | None


@dataclass(frozen=True)
class IngestResult:
    """Иммутабельный результат ingestion."""

    decision: str
    status: str
    reason: str | None
    decision_id: int | None
    decision_group_id: str | None
    command: CommandOut | None
    replayed: bool


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


@dataclass(frozen=True)
class _Scope:
    """Авторитетный scope точки въезда, выведенный из аутентифицированного контроллера.

    ``violation`` — причина отказа (``DecisionReason``), если payload заявил чужую
    зону/точку; в этом случае zone берётся контроллера, gate/barrier обнуляются и
    решение форсируется в deny без создания команды.
    """

    zone_id: int | None
    gate_id: int | None
    barrier_id: int | None
    violation: str | None


def _authorize_scope(db: Session, data: AnprIngestInput) -> _Scope:
    """Вывести zone/gate/barrier из контроллера, отвергнув чужие из payload (§9.1).

    zone_id/gate_id/barrier_id из payload НЕ доверяются: они выводятся из
    аутентифицированного ``controller`` (``controller.zone_id`` + принадлежащие ему
    gate/barrier). Если payload явно заявил зону/точку другого контроллера —
    ``violation=zone_not_allowed`` (команда чужой зоны не создаётся). ``barrier_id``
    всегда резолвится по gate контроллера, произвольный payload игнорируется.
    """
    controller = db.get(EdgeController, data.controller_id)
    ctrl_zone = controller.zone_id if controller is not None else None

    # Зона: payload не может объявить чужую зону.
    if (
        data.zone_id is not None
        and ctrl_zone is not None
        and data.zone_id != ctrl_zone
    ):
        return _Scope(ctrl_zone, None, None, DecisionReason.ZONE_NOT_ALLOWED.value)
    zone_id = ctrl_zone if ctrl_zone is not None else data.zone_id

    # Точка проезда: gate из payload должен принадлежать контроллеру; иначе выводим
    # активную точку контроллера.
    if data.gate_id is not None:
        owns_gate = db.execute(
            text(
                "SELECT 1 FROM access_gates WHERE id = :g AND controller_id = :c"
            ),
            {"g": data.gate_id, "c": data.controller_id},
        ).scalar()
        if owns_gate is None:
            return _Scope(zone_id, None, None, DecisionReason.ZONE_NOT_ALLOWED.value)
        gate_id = data.gate_id
    else:
        gate_id = db.execute(
            text(
                "SELECT id FROM access_gates "
                "WHERE controller_id = :c AND is_active = true "
                "ORDER BY id LIMIT 1"
            ),
            {"c": data.controller_id},
        ).scalar()

    # Шлагбаум резолвится по gate контроллера, не по произвольному payload.
    barrier_id = None
    if gate_id is not None:
        barrier_id = db.execute(
            text(
                "SELECT id FROM access_barriers "
                "WHERE gate_id = :g AND is_active = true ORDER BY id LIMIT 1"
            ),
            {"g": gate_id},
        ).scalar()
    return _Scope(zone_id, gate_id, barrier_id, None)


def _load_existing_result(db: Session, camera_event_id: int) -> IngestResult:
    """Собрать IngestResult из РАНЕЕ сохранённого решения/команды (idempotent replay)."""
    decision = (
        db.query(AccessDecision)
        .filter(
            AccessDecision.camera_event_id == camera_event_id,
            AccessDecision.supersedes_decision_id.is_(None),
        )
        .first()
    )
    command = None
    if decision is not None:
        cmd = (
            db.query(BarrierCommand)
            .filter(BarrierCommand.decision_id == decision.id)
            .first()
        )
        if cmd is not None:
            command = CommandOut(
                command_id=str(cmd.command_id),
                barrier_id=cmd.barrier_id,
                expires_at=cmd.expires_at,
            )
    return IngestResult(
        decision=decision.decision if decision else DecisionType.DENY.value,
        status=decision.status if decision else DecisionStatus.DENIED.value,
        reason=decision.reason if decision else None,
        decision_id=decision.id if decision else None,
        decision_group_id=str(decision.decision_group_id)
        if decision and decision.decision_group_id
        else None,
        command=command,
        replayed=True,
    )


def _find_window_duplicate(
    db: Session, data: AnprIngestInput, normalized: str | None, window_seconds: int
) -> int | None:
    """Найти camera_event-кандидат на дубль в окне (§10.1), исключая текущий ключ.

    Возвращает id найденного раннего события с начальным решением либо ``None``.
    """
    if normalized is None or data.gate_id is None:
        return None
    lo = data.captured_at - dt.timedelta(seconds=window_seconds)
    hi = data.captured_at + dt.timedelta(seconds=window_seconds)
    row = db.execute(
        text(
            """
            SELECT ce.id
            FROM camera_events ce
            JOIN access_decisions ad
              ON ad.camera_event_id = ce.id AND ad.supersedes_decision_id IS NULL
            WHERE ce.gate_id = :gate
              AND ce.direction = :direction
              AND ce.plate_number_normalized = :normalized
              AND ce.captured_at BETWEEN :lo AND :hi
              AND NOT (ce.controller_id = :cid AND ce.event_id = :eid)
            ORDER BY ce.captured_at ASC
            LIMIT 1
            """
        ),
        {
            "gate": data.gate_id,
            "direction": data.direction,
            "normalized": normalized,
            "lo": lo,
            "hi": hi,
            "cid": data.controller_id,
            "eid": data.event_id,
        },
    ).first()
    return row[0] if row else None


def _insert_camera_event(
    db: Session, data: AnprIngestInput, normalized: str | None
) -> int | None:
    """Идемпотентная вставка camera_events (ON CONFLICT DO NOTHING).

    ``normalized`` пробрасывается как ``str | None``: для no-plate колонка
    ``plate_number_normalized`` остаётся NULL (согласовано с access_events) —
    окно дедупа по NULL не срабатывает, но запись не падает (§10.1).

    Возвращает id новой строки либо ``None`` при конфликте (§10.1).
    """
    stmt = (
        pg_insert(CameraEvent.__table__)
        .values(
            controller_id=data.controller_id,
            event_id=data.event_id,
            gate_id=data.gate_id,
            camera_id=data.camera_id,
            zone_id=data.zone_id,
            plate_number_original=data.plate_number_original,
            plate_number_normalized=normalized,
            direction=data.direction,
            confidence=data.confidence,
            captured_at=data.captured_at,
            received_at=_utcnow(),
            plate_photo_url=data.plate_photo_url,
            overview_photo_url=data.overview_photo_url,
            attributes=data.attributes,
            source=data.source,
        )
        .on_conflict_do_nothing(constraint="uq_camera_events_controller_event")
        .returning(CameraEvent.__table__.c.id)
    )
    return db.execute(stmt).scalar()


def _existing_camera_event_id(db: Session, data: AnprIngestInput) -> int | None:
    return db.execute(
        text(
            "SELECT id FROM camera_events "
            "WHERE controller_id = :c AND event_id = :e"
        ),
        {"c": data.controller_id, "e": data.event_id},
    ).scalar()


def _recent_manual_open_exists(
    db: Session, barrier_id: int, captured_at: dt.datetime
) -> bool:
    """Создана ли ручная команда (manual_opening) для barrier ПОСЛЕ captured_at (§13.2).

    Под per-barrier lock ingestion: если оператор уже открыл шлагбаум вручную после
    момента события, решение фиксируется allowed_manually, новый pending не создаётся.

    TODO(accepted-risk L2, post-pilot): окно «любой manual_opening >= captured_at»
    не сужается по событию/направлению — редкое ручное открытие может «накрыть»
    несвязанный последующий проезд того же barrier. Для одной пилотной точки
    приемлемо; сузить (по event/времени окна) — после пилота.
    """
    return (
        db.execute(
            text(
                "SELECT 1 FROM manual_openings "
                "WHERE barrier_id = :b AND created_at >= :ts LIMIT 1"
            ),
            {"b": barrier_id, "ts": captured_at},
        ).scalar()
        is not None
    )


def _consume_taxi(db: Session, pass_id: int) -> bool:
    """Атомарно израсходовать один въезд taxi-pass (§10.3).

    ``UPDATE ... SET used_entries = used_entries + 1 WHERE id = :p AND
    used_entries < max_entries``. Возвращает True при успехе (выделена ёмкость),
    False — если лимит уже исчерпан. При достижении max — статус 'used'.
    """
    updated = db.execute(
        text(
            "UPDATE access_passes "
            "SET used_entries = used_entries + 1, "
            "    status = CASE WHEN used_entries + 1 >= max_entries "
            "                  THEN :used ELSE status END "
            "WHERE id = :p AND used_entries < max_entries"
        ),
        {"p": pass_id, "used": PassStatus.USED.value},
    )
    return updated.rowcount == 1


def _write_decision(
    db: Session,
    *,
    camera_event_id: int,
    engine: EngineDecision,
    final_status: str,
    review_deadline_at: dt.datetime | None,
    source: str,
) -> AccessDecision:
    """Записать начальную строку решения (append-only) с hash-chain (§9.5, §9.7)."""
    group_id = uuid.uuid4()
    payload = {
        "camera_event_id": camera_event_id,
        "decision_group_id": str(group_id),
        "decision": engine.decision,
        "status": final_status,
        "reason": engine.reason,
        "matched_vehicle_id": engine.matched_vehicle_id,
        "matched_pass_id": engine.matched_pass_id,
        "source": source,
    }
    prev_hash, row_hash = next_hash(db, "access_decisions", payload)
    decision = AccessDecision(
        camera_event_id=camera_event_id,
        decision_group_id=group_id,
        decision=engine.decision,
        status=final_status,
        reason=engine.reason,
        matched_vehicle_id=engine.matched_vehicle_id,
        matched_pass_id=engine.matched_pass_id,
        review_deadline_at=review_deadline_at,
        source=source,
        prev_hash=prev_hash,
        row_hash=row_hash,
    )
    db.add(decision)
    db.flush()
    return decision


def _write_access_event(
    db: Session,
    *,
    data: AnprIngestInput,
    camera_event_id: int,
    decision: AccessDecision,
    normalized: str | None,
) -> None:
    """Записать иммутабельный журнал проезда (§9.7) с hash-chain и связностью (§15.10)."""
    apartment_id = None
    if decision.matched_vehicle_id is not None:
        apartment_id = db.execute(
            text(
                "SELECT apartment_id FROM vehicle_apartments "
                "WHERE vehicle_id = :v AND status = 'active' "
                "ORDER BY id ASC LIMIT 1"
            ),
            {"v": decision.matched_vehicle_id},
        ).scalar()
    payload = {
        "controller_id": data.controller_id,
        "event_id": data.event_id,
        "camera_event_id": camera_event_id,
        "decision_id": decision.id,
        "vehicle_id": decision.matched_vehicle_id,
        "pass_id": decision.matched_pass_id,
        "apartment_id": apartment_id,
        "gate_id": data.gate_id,
        "zone_id": data.zone_id,
        "direction": data.direction,
        "plate_number_normalized": normalized,
        "decision": decision.decision,
        "reason": decision.reason,
        "source": data.source,
    }
    prev_hash, row_hash = next_hash(db, "access_events", payload)
    db.add(
        AccessEvent(
            controller_id=data.controller_id,
            event_id=data.event_id,
            camera_event_id=camera_event_id,
            decision_id=decision.id,
            vehicle_id=decision.matched_vehicle_id,
            pass_id=decision.matched_pass_id,
            apartment_id=apartment_id,
            gate_id=data.gate_id,
            zone_id=data.zone_id,
            direction=data.direction,
            plate_number_normalized=normalized,
            decision=decision.decision,
            reason=decision.reason,
            occurred_at=data.captured_at,
            source=data.source,
            prev_hash=prev_hash,
            row_hash=row_hash,
        )
    )


def _create_command(
    db: Session,
    *,
    data: AnprIngestInput,
    barrier_id: int,
    decision_id: int,
    command_ttl_seconds: int,
) -> CommandOut:
    """Идемпотентно создать команду открытия (§9.2, UNIQUE(decision_id))."""
    expires_at = _utcnow() + dt.timedelta(seconds=command_ttl_seconds)
    new_command_id = uuid.uuid4()
    stmt = (
        pg_insert(BarrierCommand.__table__)
        .values(
            command_id=new_command_id,
            decision_id=decision_id,
            controller_id=data.controller_id,
            barrier_id=barrier_id,
            command_type=CommandType.OPEN_BARRIER.value,
            status=CommandStatus.PENDING.value,
            expires_at=expires_at,
        )
        .on_conflict_do_nothing(
            index_elements=["decision_id"],
            index_where=text("decision_id IS NOT NULL"),
        )
        .returning(BarrierCommand.__table__.c.command_id)
    )
    inserted = db.execute(stmt).scalar()
    if inserted is None:
        # Команда на это решение уже существует — вернуть сохранённую (idempotent).
        existing = (
            db.query(BarrierCommand)
            .filter(BarrierCommand.decision_id == decision_id)
            .first()
        )
        return CommandOut(
            command_id=str(existing.command_id),
            barrier_id=existing.barrier_id,
            expires_at=existing.expires_at,
        )
    return CommandOut(
        command_id=str(new_command_id), barrier_id=barrier_id, expires_at=expires_at
    )


def _run_ingest(
    db: Session,
    data: AnprIngestInput,
    *,
    dedup_window_seconds: int = DEFAULT_DEDUP_WINDOW_SECONDS,
    command_ttl_seconds: int = DEFAULT_COMMAND_TTL_SECONDS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> IngestResult:
    """Принять ANPR-событие идемпотентно и атомарно (§7 шаги 1–11)."""
    # §9.1: zone/gate/barrier выводятся из аутентифицированного контроллера, а не
    # из доверия payload. Дальше работаем с санитизированными значениями.
    scope = _authorize_scope(db, data)
    data = replace(
        data, zone_id=scope.zone_id, gate_id=scope.gate_id, barrier_id=scope.barrier_id
    )
    barrier_id = scope.barrier_id
    # Канонический ключ advisory-lock (§13.2, общий с resolve/manual-open/expiry):
    # активный barrier → gate → контроллер. Один ключ на физический проезд.
    lock_key = canonical_lock_key(barrier_id, data.gate_id, data.controller_id)
    advisory_xact_lock(db, lock_key)

    # Шаг 2: идемпотентный приём — повтор того же (controller_id,event_id).
    existing_id = _existing_camera_event_id(db, data)
    if existing_id is not None:
        result = _load_existing_result(db, existing_id)
        db.commit()
        return result

    # Шаг 3: нормализация номера (§12). Держим полный результат, чтобы передать
    # реальный recognition_key движку (поле не должно вводить в заблуждение).
    plate = (
        normalize_plate(data.plate_number_original)
        if data.plate_number_original
        else None
    )
    normalized = plate.normalized if plate else None
    recognition_key = plate.recognition_key if plate else None

    # Короткое окно дедупа (§10.1): дубль без стабильного event_id → прежнее решение.
    window_dup_id = _find_window_duplicate(db, data, normalized, dedup_window_seconds)
    if window_dup_id is not None:
        result = _load_existing_result(db, window_dup_id)
        db.commit()
        return result

    # Вставка camera_events (ON CONFLICT DO NOTHING — защита от гонки).
    camera_event_id = _insert_camera_event(db, data, normalized)
    if camera_event_id is None:
        # Конкурентная вставка успела раньше — вернуть её результат идемпотентно.
        existing_id = _existing_camera_event_id(db, data)
        if existing_id is None:
            # ON CONFLICT сработал, но строки нет — рассинхрон БД, а не deny.
            raise RuntimeError(
                "ON CONFLICT сработал, но camera_event не найден — рассинхрон БД"
            )
        result = _load_existing_result(db, existing_id)
        db.commit()
        return result

    # Шаги 4–8: решение движка (без записи в БД). При scope-violation (§9.1) —
    # форсируем deny zone_not_allowed, движок не вызываем и команду не создаём.
    if scope.violation is not None:
        engine = EngineDecision(
            decision=DecisionType.DENY.value,
            reason=scope.violation,
            status=DecisionStatus.DENIED.value,
        )
    else:
        # §10.2: чистое время Decision Engine измеряется отдельно от ingestion/DB.
        with measure(PHASE_DECISION):
            engine = decide(
                db,
                AnprDecisionInput(
                    controller_id=data.controller_id,
                    zone_id=data.zone_id,
                    gate_id=data.gate_id,
                    camera_id=data.camera_id,
                    plate_number_normalized=normalized or "",
                    recognition_key=recognition_key,
                    direction=data.direction,
                    confidence=data.confidence,
                    captured_at=data.captured_at,
                ),
                confidence_threshold=confidence_threshold,
            )

    # Шаг 8/9: атомарный расход taxi-pass. Неуспех → переигрываем в deny.
    final_status = engine.status
    review_deadline_at = None
    is_taxi_allow = (
        engine.decision == DecisionType.ALLOW.value
        and engine.reason == DecisionReason.TEMPORARY_PASS_ALLOWED.value
        and engine.matched_pass_id is not None
    )
    if is_taxi_allow:
        if not _consume_taxi(db, engine.matched_pass_id):
            engine = EngineDecision(
                decision=DecisionType.DENY.value,
                reason=DecisionReason.PASS_ALREADY_USED.value,
                status=DecisionStatus.DENIED.value,
                matched_pass_id=engine.matched_pass_id,
            )
            final_status = engine.status

    if engine.decision == DecisionType.MANUAL_REVIEW.value:
        if barrier_id is not None and _recent_manual_open_exists(
            db, barrier_id, data.captured_at
        ):
            # §13.2: ручная команда для barrier уже создана после captured_at →
            # решение сразу allowed_manually, pending не создаём, команду не дублируем
            # (ручная команда уже доставляется durable-каналом).
            engine = replace(
                engine,
                decision=DecisionType.ALLOW.value,
                status=DecisionStatus.ALLOWED_MANUALLY.value,
            )
            final_status = DecisionStatus.ALLOWED_MANUALLY.value
        else:
            final_status = DecisionStatus.PENDING_REVIEW.value
            review_deadline_at = _utcnow() + dt.timedelta(
                seconds=MANUAL_REVIEW_DEADLINE_SECONDS
            )

    # Шаг 9: запись решения (append-only + hash-chain).
    decision = _write_decision(
        db,
        camera_event_id=camera_event_id,
        engine=engine,
        final_status=final_status,
        review_deadline_at=review_deadline_at,
        source=data.source,
    )

    # Иммутабельный журнал проезда + связность идентификаторов (§15.10).
    _write_access_event(
        db,
        data=data,
        camera_event_id=camera_event_id,
        decision=decision,
        normalized=normalized,
    )

    # Шаг 10: при allow — идемпотентная команда открытия. manual_review — без команды.
    command = None
    if (
        engine.decision == DecisionType.ALLOW.value
        and final_status == DecisionStatus.ALLOWED.value
        and barrier_id is not None
    ):
        command = _create_command(
            db,
            data=data,
            barrier_id=barrier_id,
            decision_id=decision.id,
            command_ttl_seconds=command_ttl_seconds,
        )

    # §10.2: время записи транзакции (commit round-trip к БД) — отдельная фаза.
    with measure(PHASE_DB):
        db.commit()

    # §9.6/§15.13: ПОСЛЕ коммита публикуем PD-safe live-событие охране (§11 — без
    # полного номера/фото). Только для нового решения (replay-пути сюда не доходят).
    _publish_event(data=data, engine=engine, final_status=final_status, normalized=normalized)

    return IngestResult(
        decision=engine.decision,
        status=final_status,
        reason=engine.reason,
        decision_id=decision.id,
        decision_group_id=str(decision.decision_group_id),
        command=command,
        replayed=False,
    )


def _publish_event(
    *, data: AnprIngestInput, engine: EngineDecision, final_status: str, normalized: str | None
) -> None:
    """Опубликовать PD-safe событие доступа в брокер для WS-панели охраны (§9.6, §11).

    Best-effort: сбой брокера НЕ должен влиять на уже зафиксированное решение —
    исключение проглатывается с логом. ``data`` здесь уже санитизирован
    (zone/gate выведены из контроллера), номер — только маскированный хвост.
    """
    try:
        get_broker().publish(
            AccessEventMessage(
                decision=engine.decision,
                status=final_status,
                reason=engine.reason,
                zone_id=data.zone_id,
                gate_id=data.gate_id,
                direction=data.direction,
                occurred_at=data.captured_at.isoformat(),
                plate_masked=mask_plate(normalized),
            )
        )
    except Exception:  # noqa: BLE001 — трансляция не критична для приёма события
        logger.exception("access event publish failed (event delivered, broadcast dropped)")


def ingest_anpr(
    db: Session,
    data: AnprIngestInput,
    *,
    dedup_window_seconds: int = DEFAULT_DEDUP_WINDOW_SECONDS,
    command_ttl_seconds: int = DEFAULT_COMMAND_TTL_SECONDS,
    confidence_threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
) -> IngestResult:
    """Принять ANPR-событие (§7) с PD-safe логированием исхода (§11).

    INFO логирует только исход (decision/reason/replayed/длительность) БЕЗ номера,
    фото и кода. Полный номер НЕ попадает в логи ни на одном уровне, включая DEBUG
    (§11: номер не должен оказываться в application logs). Диагностический DEBUG-след
    содержит только event_id/decision/reason.
    """
    started = time.perf_counter()
    result = _run_ingest(
        db,
        data,
        dedup_window_seconds=dedup_window_seconds,
        command_ttl_seconds=command_ttl_seconds,
        confidence_threshold=confidence_threshold,
    )
    duration_ms = (time.perf_counter() - started) * 1000.0
    # §10.2: полная задержка приёма ANPR backend'ом (ingestion-фаза).
    observe_ingestion(duration_ms)
    logger.info(
        "anpr ingest: decision=%s reason=%s replayed=%s duration_ms=%.1f",
        result.decision,
        result.reason,
        result.replayed,
        duration_ms,
    )
    # §11: номер НЕ логируется даже на DEBUG. Диагностический след — только
    # event_id/decision/reason (без номера/фото/кода).
    logger.debug(
        "anpr ingest detail: event_id=%s decision=%s reason=%s",
        data.event_id,
        result.decision,
        result.reason,
    )
    return result
