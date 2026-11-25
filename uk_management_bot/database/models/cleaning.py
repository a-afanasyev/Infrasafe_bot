"""Модуль «Уборка»: план дома, назначения, задания на день, фото, журнал, жалобы.

Опорные решения (план ~/.claude/plans/woolly-honking-eclipse.md, ред. 4):

* план дома и назначения версионируются датами действия — задание любого дня
  воспроизводимо, когда бы ни запустилась генерация;
* задание (``cleaning_tasks``) — снимок на (дом, подъезд, дата);
* строка фото (``cleaning_photos``) — одна операция загрузки с сохранённым
  исходом; текущее фото точки — частичный уникальный индекс по ``is_current``;
* точка съёмки — непустая строка ``slot``: ``floor:3`` / ``point:elevator``.
"""
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from uk_management_bot.database.session import Base

TASK_STATUSES = ("planned", "in_progress", "accepted", "review", "rejected", "missed", "expired")
PHOTO_STATES = ("pending", "done")
PHOTO_OUTCOMES = ("activated", "superseded", "evidence", "refused")
TRUST_LEVELS = ("live", "deferred", "offline", "late")
COMPLAINT_OUTCOMES = ("pending", "confirmed", "unfounded")


def _json():
    return JSON().with_variant(JSONB(), "postgresql")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


class CleaningPlanVersion(Base):
    """Неизменяемая версия плана дома; действует с ``valid_from`` по ``valid_to``."""

    __tablename__ = "cleaning_plan_versions"
    __table_args__ = (UniqueConstraint("building_id", "valid_from", name="uq_cleaning_plan_versions_start"),)

    id = Column(Integer, primary_key=True)
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False, index=True)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    # [{work_kind, weekdays, entrances|null, floor_from|null, floor_to|null}]
    items = Column(_json(), nullable=False)
    extra_points = Column(_json(), nullable=False, default=list)
    # Снимок справочника: правка дома позже не меняет прошлые задания.
    floor_count = Column(Integer, nullable=False)
    entrance_count = Column(Integer, nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CleaningAssignment(Base):
    """Ответственный за подъезд на период; закрывается датой, не удаляется."""

    __tablename__ = "cleaning_assignments"
    __table_args__ = (
        Index("ix_cleaning_assignments_entrance", "building_id", "entrance", "valid_from"),
    )

    id = Column(Integer, primary_key=True)
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    entrance = Column(Integer, nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    valid_from = Column(Date, nullable=False)
    valid_to = Column(Date, nullable=True)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CleaningBuildingSettings(Base):
    """Живые настройки дома: показ жителям и площади для нагрузки; на задания не влияют."""

    __tablename__ = "cleaning_building_settings"

    building_id = Column(Integer, ForeignKey("buildings.id"), primary_key=True)
    show_to_residents = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    show_photos = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Площади мест общего пользования по подъездам (services/cleaning/areas.py); NULL — не заданы.
    areas = Column(_json(), nullable=True)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CleaningRules(Base):
    """Append-only версии настроек и порогов; текущая — с наибольшим id."""

    __tablename__ = "cleaning_rules"

    id = Column(Integer, primary_key=True)
    data = Column(_json(), nullable=False)
    created_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CleaningDay(Base):
    """Маркер дня: идемпотентность генерации/закрытия и снимок конца дня."""

    __tablename__ = "cleaning_days"

    work_date = Column(Date, primary_key=True)
    day_end_at = Column(DateTime(timezone=True), nullable=False)
    rules_version = Column(Integer, ForeignKey("cleaning_rules.id"), nullable=True)
    generated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    skipped = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    # Отметки «сообщение бота за этот день уже отправлено» (services/cleaning/notify.py).
    morning_sent_at = Column(DateTime(timezone=True), nullable=True)
    reminded_at = Column(DateTime(timezone=True), nullable=True)
    summary_sent_at = Column(DateTime(timezone=True), nullable=True)


class CleaningTask(Base):
    """Задание на (дом, подъезд, дата) — снимок плана и ответственного."""

    __tablename__ = "cleaning_tasks"
    __table_args__ = (
        UniqueConstraint("building_id", "entrance", "work_date", name="uq_cleaning_tasks_entrance_day"),
        CheckConstraint(_in("status", TASK_STATUSES), name="ck_cleaning_tasks_status"),
        Index("ix_cleaning_tasks_day_status", "work_date", "status"),
        Index("ix_cleaning_tasks_responsible_day", "responsible_id", "work_date"),
    )

    id = Column(Integer, primary_key=True)
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    entrance = Column(Integer, nullable=False)
    work_date = Column(Date, nullable=False)
    plan_version_id = Column(Integer, ForeignKey("cleaning_plan_versions.id"), nullable=False)
    works = Column(_json(), nullable=False)
    slots_required = Column(_json(), nullable=False)
    responsible_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(20), nullable=False, default="planned", server_default="planned")
    version = Column(Integer, nullable=False, default=1, server_default=text("1"))
    session_opened_at = Column(DateTime(timezone=True), nullable=True)
    sampled = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class CleaningPhoto(Base):
    """Одна операция загрузки: строка создаётся один раз и хранит свой исход."""

    __tablename__ = "cleaning_photos"
    __table_args__ = (
        CheckConstraint(_in("state", PHOTO_STATES), name="ck_cleaning_photos_state"),
        CheckConstraint("slot LIKE 'floor:_%' OR slot LIKE 'point:_%'", name="ck_cleaning_photos_slot"),
        Index(
            "uq_cleaning_photos_current_slot", "task_id", "slot", unique=True,
            postgresql_where=text("is_current"), sqlite_where=text("is_current"),
        ),
        Index("ix_cleaning_photos_task_slot", "task_id", "slot"),
        Index("ix_cleaning_photos_pixel_sha256", "pixel_sha256"),
    )

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("cleaning_tasks.id"), nullable=False)
    slot = Column(String(40), nullable=False)
    op_key = Column(String(36), nullable=False, unique=True)
    uploaded_by = Column(Integer, ForeignKey("users.id"), nullable=False)
    upload_sha256 = Column(String(64), nullable=False)
    pixel_sha256 = Column(String(64), nullable=True)
    dhash = Column(String(16), nullable=True)
    state = Column(String(10), nullable=False, default="pending")
    outcome = Column(String(12), nullable=True)
    refusal_code = Column(String(40), nullable=True)
    claim_token = Column(String(36), nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    media_id = Column(Integer, nullable=True)
    is_current = Column(Boolean, nullable=False, default=False, server_default=text("false"))
    trust_level = Column(String(10), nullable=True)
    client_captured_at = Column(DateTime(timezone=True), nullable=True)
    received_at = Column(DateTime(timezone=True), nullable=False)
    activated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CleaningTaskEvent(Base):
    """Append-only журнал задания: переходы, решения, поздние доказательства."""

    __tablename__ = "cleaning_task_events"

    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("cleaning_tasks.id"), nullable=False, index=True)
    actor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind = Column(String(30), nullable=False)
    from_status = Column(String(20), nullable=True)
    to_status = Column(String(20), nullable=True)
    reason = Column(Text, nullable=True)
    rules_version = Column(Integer, nullable=True)
    payload = Column(_json(), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class CleaningComplaint(Base):
    """Жалоба жителя на уборку подъезда в день; заявка создаётся вторым шагом."""

    __tablename__ = "cleaning_complaints"
    __table_args__ = (
        UniqueConstraint("author_id", "building_id", "entrance", "work_date", name="uq_cleaning_complaints_author_day"),
        CheckConstraint(_in("outcome", COMPLAINT_OUTCOMES), name="ck_cleaning_complaints_outcome"),
        Index("ix_cleaning_complaints_entrance_day", "building_id", "entrance", "work_date"),
    )

    id = Column(Integer, primary_key=True)
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    entrance = Column(Integer, nullable=False)
    work_date = Column(Date, nullable=False)
    author_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("cleaning_tasks.id"), nullable=True)
    request_number = Column(String(15), nullable=True, unique=True)
    outcome = Column(String(12), nullable=False, default="pending", server_default="pending")
    decided_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
