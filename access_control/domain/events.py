"""ANPR-события, решения и иммутабельный журнал проездов. §7, §9.5, §10.1.

Разделение слоёв (решение CTO #4):
* ``camera_events`` — сырой слой приёма ANPR (фото, retention 30 дн, граница
  идемпотентности). ``UNIQUE(controller_id, event_id)`` — канонический ключ §10.1
  + индекс окна дедупа ``(gate_id, direction, plate_number_normalized, captured_at)``.
* ``access_decisions`` — решение Decision Engine; lifecycle §9.5 моделируется
  НОВЫМИ строками (``decision_group_id`` + ``supersedes_decision_id``, решение
  CTO #3), не UPDATE. ``UNIQUE(camera_event_id) WHERE supersedes_decision_id IS
  NULL`` — ровно одно начальное решение на событие. Append-only (§9.7) + hash-chain.
* ``access_events`` — иммутабельный бизнес-журнал проезда (retention 12 мес,
  hash-chain). ``UNIQUE(controller_id, event_id)`` — один проезд на event.
  Append-only (§9.7).
* ``controller_sync_events`` — отложенные offline-события edge (§8.4).
  ``UNIQUE(controller_id, event_id)``.
"""
from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    text,
)

from uk_management_bot.database.session import Base
from .base import (
    HashChainMixin,
    JSONB_PORTABLE,
    Uuid,
    created_at_column,
    pk_column,
)
from .enums import (
    DecisionReason,
    DecisionStatus,
    DecisionType,
    Direction,
    EntryConfirmationResponse,
    EventSource,
    in_clause,
)


class CameraEvent(Base):
    """Сырое ANPR-событие приёма (§10.1, граница идемпотентности)."""

    __tablename__ = "camera_events"

    id = pk_column()
    controller_id = Column(
        ForeignKey("edge_controllers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # event_id — стабильный/детерминированный ID события (§10.1, решение CTO #1).
    event_id = Column(String(128), nullable=False)
    gate_id = Column(
        ForeignKey("access_gates.id", ondelete="SET NULL"), nullable=True, index=True
    )
    camera_id = Column(
        ForeignKey("access_cameras.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    zone_id = Column(
        ForeignKey("parking_zones.id", ondelete="SET NULL"), nullable=True
    )
    plate_number_original = Column(String(32), nullable=True)
    plate_number_normalized = Column(String(32), nullable=True)
    direction = Column(String(16), nullable=False)
    confidence = Column(Numeric(5, 4), nullable=True)
    captured_at = Column(DateTime(timezone=True), nullable=False)
    received_at = Column(DateTime(timezone=True), nullable=True)
    # Ссылки на приватный storage (§11, решение CTO #7), не сами изображения.
    plate_photo_url = Column(String(1024), nullable=True)
    overview_photo_url = Column(String(1024), nullable=True)
    attributes = Column(JSONB_PORTABLE, nullable=True)
    source = Column(
        String(16), nullable=False, server_default=EventSource.CONNECTED.value
    )
    created_at = created_at_column()

    __table_args__ = (
        UniqueConstraint(
            "controller_id", "event_id", name="uq_camera_events_controller_event"
        ),
        CheckConstraint(
            in_clause("direction", Direction), name="ck_camera_events_direction"
        ),
        CheckConstraint(
            in_clause("source", EventSource), name="ck_camera_events_source"
        ),
        # Окно дедупа §10.1: gate + direction + normalized_plate + captured_at (10 c).
        Index(
            "ix_camera_events_dedup_window",
            "gate_id",
            "direction",
            "plate_number_normalized",
            "captured_at",
        ),
    )


class AccessDecision(Base, HashChainMixin):
    """Решение Decision Engine; lifecycle append-only (§9.5, §9.7, решение CTO #3)."""

    __tablename__ = "access_decisions"

    id = pk_column()
    camera_event_id = Column(
        ForeignKey("camera_events.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Группа решений одного события; «текущее» = последняя строка группы.
    # TODO Ф3: NOT NULL когда сервис будет проставлять decision_group_id.
    decision_group_id = Column(Uuid(), nullable=True, index=True)
    # Транзишн-строка указывает на решение, которое она замещает (append-only).
    supersedes_decision_id = Column(
        ForeignKey("access_decisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decision = Column(String(16), nullable=False)
    status = Column(String(32), nullable=False)
    reason = Column(String(64), nullable=True)
    confidence = Column(Numeric(5, 4), nullable=True)
    matched_vehicle_id = Column(
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    matched_pass_id = Column(
        ForeignKey("access_passes.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Дедлайн manual_review (§9.5: now()+120s).
    review_deadline_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    source = Column(
        String(16), nullable=False, server_default=EventSource.CONNECTED.value
    )
    created_at = created_at_column()

    __table_args__ = (
        CheckConstraint(
            in_clause("decision", DecisionType), name="ck_access_decisions_decision"
        ),
        CheckConstraint(
            in_clause("status", DecisionStatus), name="ck_access_decisions_status"
        ),
        CheckConstraint(
            "reason IS NULL OR " + in_clause("reason", DecisionReason),
            name="ck_access_decisions_reason",
        ),
        CheckConstraint(
            in_clause("source", EventSource), name="ck_access_decisions_source"
        ),
        # Ровно одно начальное решение на событие (транзишн-строки разрешены).
        Index(
            "uq_access_decisions_initial_per_event",
            "camera_event_id",
            unique=True,
            postgresql_where=text("supersedes_decision_id IS NULL"),
            sqlite_where=text("supersedes_decision_id IS NULL"),
        ),
    )


class AccessEvent(Base, HashChainMixin):
    """Иммутабельный бизнес-журнал проезда (§9.7, retention 12 мес)."""

    __tablename__ = "access_events"

    id = pk_column()
    controller_id = Column(
        ForeignKey("edge_controllers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id = Column(String(128), nullable=False)
    camera_event_id = Column(
        ForeignKey("camera_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    decision_id = Column(
        ForeignKey("access_decisions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vehicle_id = Column(
        ForeignKey("vehicles.id", ondelete="SET NULL"), nullable=True
    )
    pass_id = Column(
        ForeignKey("access_passes.id", ondelete="SET NULL"), nullable=True
    )
    apartment_id = Column(
        Integer, ForeignKey("apartments.id", ondelete="SET NULL"), nullable=True
    )
    gate_id = Column(
        ForeignKey("access_gates.id", ondelete="SET NULL"), nullable=True
    )
    zone_id = Column(
        ForeignKey("parking_zones.id", ondelete="SET NULL"), nullable=True
    )
    direction = Column(String(16), nullable=False)
    plate_number_normalized = Column(String(32), nullable=True)
    decision = Column(String(16), nullable=True)
    reason = Column(String(64), nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    source = Column(
        String(16), nullable=False, server_default=EventSource.CONNECTED.value
    )
    created_at = created_at_column()

    __table_args__ = (
        UniqueConstraint(
            "controller_id", "event_id", name="uq_access_events_controller_event"
        ),
        CheckConstraint(
            in_clause("direction", Direction), name="ck_access_events_direction"
        ),
        CheckConstraint(
            in_clause("source", EventSource), name="ck_access_events_source"
        ),
    )


class AccessEntryConfirmation(Base):
    """Ответ жителя на спорный въезд (§6.4, §9.4, §16.2).

    СОВЕЩАТЕЛЬНЫЙ сигнал (решение CTO): фиксируется и показывается оператору, но
    НЕ открывает шлагбаум и НЕ меняет ``access_decisions`` — финальное решение за
    оператором (§9.5). НЕ append-only (в отличие от журналов/аудита §9.7):
    допускается upsert «последнего ответа» по ``UNIQUE(decision_id, user_id)`` —
    житель вправе передумать (confirm→deny). Каждый ответ дополнительно пишет
    append-only ``access_audit_logs`` (там история сохраняется неизменной).
    """

    __tablename__ = "access_entry_confirmations"

    id = pk_column()
    decision_id = Column(
        ForeignKey("access_decisions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # Связь с самим спорным событием (для отчётности/джойнов с camera_events).
    camera_event_id = Column(
        ForeignKey("camera_events.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    apartment_id = Column(
        Integer, ForeignKey("apartments.id", ondelete="SET NULL"), nullable=True
    )
    response = Column(String(8), nullable=False)
    created_at = created_at_column()

    __table_args__ = (
        CheckConstraint(
            in_clause("response", EntryConfirmationResponse),
            name="ck_access_entry_confirmations_response",
        ),
        # Один ответ на решение от пользователя; повтор → upsert (последний ответ).
        UniqueConstraint(
            "decision_id", "user_id", name="uq_access_entry_confirmations_decision_user"
        ),
    )


class ControllerSyncEvent(Base):
    """Отложенное offline-событие синхронизации edge (§8.4)."""

    __tablename__ = "controller_sync_events"

    id = pk_column()
    controller_id = Column(
        ForeignKey("edge_controllers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    event_id = Column(String(128), nullable=False)
    payload = Column(JSONB_PORTABLE, nullable=True)
    # Конфликт/просроченный snapshot попадают в отдельный отчёт (§8.4).
    conflict = Column(Boolean, nullable=False, server_default="false")
    snapshot_expired = Column(Boolean, nullable=False, server_default="false")
    received_at = Column(DateTime(timezone=True), nullable=True)
    created_at = created_at_column()

    __table_args__ = (
        UniqueConstraint(
            "controller_id",
            "event_id",
            name="uq_controller_sync_events_controller_event",
        ),
    )
