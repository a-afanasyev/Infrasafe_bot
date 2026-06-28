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

Движок (decision_engine) сам в БД не пишет; запись — здесь (§7 шаг 9). Весь доступ
к данным вынесен в ``access_control.repositories`` — здесь только оркестрация
(lock → read → write → commit).
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from access_control.domain.enums import (
    DecisionReason,
    DecisionStatus,
    DecisionType,
    EventSource,
)
from access_control.domain.events import AccessDecision
from access_control.repositories import (
    access_events_repo,
    barrier_commands_repo,
    camera_events_repo,
    decisions_repo,
    equipment_repo,
    manual_openings_repo,
    passes_repo,
)
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
from access_control.services.locks import advisory_xact_lock, canonical_lock_key
from access_control.services.metrics import (
    PHASE_DB,
    PHASE_DECISION,
    measure,
    observe_ingestion,
)
from access_control.services.normalization import normalize_plate
from access_control.services.resident_notify import (
    KIND_DISPUTED_ENTRY,
    publish_resident_notification,
)

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
    controller = equipment_repo.get_controller(db, data.controller_id)
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
        if not equipment_repo.gate_belongs_to_controller(
            db, gate_id=data.gate_id, controller_id=data.controller_id
        ):
            return _Scope(zone_id, None, None, DecisionReason.ZONE_NOT_ALLOWED.value)
        gate_id = data.gate_id
    else:
        gate_id = equipment_repo.first_active_gate_for_controller(
            db, data.controller_id
        )

    # Шлагбаум резолвится по gate контроллера, не по произвольному payload.
    barrier_id = None
    if gate_id is not None:
        barrier_id = equipment_repo.first_active_barrier_for_gate(db, gate_id)
    return _Scope(zone_id, gate_id, barrier_id, None)


def _load_existing_result(db: Session, camera_event_id: int) -> IngestResult:
    """Собрать IngestResult из РАНЕЕ сохранённого решения/команды (idempotent replay)."""
    decision = decisions_repo.initial_for_event(db, camera_event_id)
    command = None
    if decision is not None:
        cmd = barrier_commands_repo.command_for_decision(db, decision.id)
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
    """Найти camera_event-кандидат на дубль в окне (§10.1), исключая текущий ключ."""
    return camera_events_repo.find_window_duplicate(
        db, data, normalized, window_seconds
    )


def _insert_camera_event(
    db: Session, data: AnprIngestInput, normalized: str | None
) -> int | None:
    """Идемпотентная вставка camera_events (ON CONFLICT DO NOTHING)."""
    return camera_events_repo.insert_idempotent(db, data, normalized)


def _existing_camera_event_id(db: Session, data: AnprIngestInput) -> int | None:
    return camera_events_repo.find_event_id(
        db, controller_id=data.controller_id, event_id=data.event_id
    )


def _recent_manual_open_exists(
    db: Session, barrier_id: int, captured_at: dt.datetime
) -> bool:
    """Создана ли ручная команда (manual_opening) для barrier ПОСЛЕ captured_at (§13.2).

    TODO(accepted-risk L2, post-pilot): окно «любой manual_opening >= captured_at»
    не сужается по событию/направлению — редкое ручное открытие может «накрыть»
    несвязанный последующий проезд того же barrier. Для одной пилотной точки
    приемлемо; сузить (по event/времени окна) — после пилота.
    """
    return manual_openings_repo.recent_open_exists(
        db, barrier_id=barrier_id, since=captured_at
    )


def _consume_taxi(db: Session, pass_id: int) -> bool:
    """Атомарно израсходовать один въезд taxi-pass (§10.3)."""
    return passes_repo.consume_taxi_entry(db, pass_id)


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
    return decisions_repo.insert_initial(
        db,
        camera_event_id=camera_event_id,
        decision=engine.decision,
        status=final_status,
        reason=engine.reason,
        matched_vehicle_id=engine.matched_vehicle_id,
        matched_pass_id=engine.matched_pass_id,
        review_deadline_at=review_deadline_at,
        source=source,
    )


def _write_access_event(
    db: Session,
    *,
    data: AnprIngestInput,
    camera_event_id: int,
    decision: AccessDecision,
    normalized: str | None,
) -> None:
    """Записать иммутабельный журнал проезда (§9.7) с hash-chain и связностью (§15.10)."""
    access_events_repo.insert_access_event(
        db,
        data=data,
        camera_event_id=camera_event_id,
        decision=decision,
        normalized=normalized,
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
    row = barrier_commands_repo.create_open_command(
        db,
        controller_id=data.controller_id,
        barrier_id=barrier_id,
        decision_id=decision_id,
        ttl_seconds=command_ttl_seconds,
    )
    return CommandOut(
        command_id=row.command_id, barrier_id=row.barrier_id, expires_at=row.expires_at
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

    # §6.4/§9.4/§16.2: спорный въезд (pending_review) по номеру авто жителя →
    # адресное уведомление жителю с просьбой подтвердить (best-effort, ПОСЛЕ commit).
    if final_status == DecisionStatus.PENDING_REVIEW.value:
        _notify_disputed_entry(
            db,
            decision_id=decision.id,
            camera_event_id=camera_event_id,
            zone_id=data.zone_id,
            normalized=normalized,
        )

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


def _notify_disputed_entry(
    db: Session,
    *,
    decision_id: int,
    camera_event_id: int,
    zone_id: int | None,
    normalized: str | None,
) -> None:
    """Уведомить жителя(ей) о спорном въезде (pending_review) по его авто (§6.4, §9.4).

    Адресат — житель approved-квартиры, к которой active-связью привязан vehicle с
    этим нормализованным номером. Если номер не сопоставлен с резидентом — адресата
    нет, ничего не публикуем. Совещательно: уведомление НЕ открывает шлагбаум.

    Best-effort: любой сбой (резолв адресатов, publish) проглатывается с логом без
    ПД — решение уже зафиксировано (§10.2: вне горячего пути латентности). PD-safe
    (§11): в канал кладём только маскированный хвост номера и идентификаторы.
    """
    if not normalized:
        return
    try:
        # Локальный импорт: resident зависит от management/normalization — избегаем
        # цикла импорта на уровне модуля ingestion.
        from access_control.services.resident import disputed_entry_recipient_ids

        recipient_ids = disputed_entry_recipient_ids(db, normalized)
        if not recipient_ids:
            return
        for user_id in recipient_ids:
            publish_resident_notification(
                kind=KIND_DISPUTED_ENTRY,
                recipient_user_id=user_id,
                payload={
                    "decision_id": decision_id,
                    "camera_event_id": camera_event_id,
                    "zone": zone_id,
                    "plate_masked": mask_plate(normalized),
                    "status": DecisionStatus.PENDING_REVIEW.value,
                },
            )
    except Exception:  # noqa: BLE001 — уведомление не критично для приёма события
        logger.exception(
            "disputed-entry resident notify failed (decision recorded, notify dropped)"
        )


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
