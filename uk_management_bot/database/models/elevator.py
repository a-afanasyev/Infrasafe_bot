"""Модели модуля «Лифты» (реестр, журнал статусов, график ТО/освидетельствований).

Три таблицы одного агрегата:

* ``elevators`` — реестр лифтов с паспортом, текущим статусом, договором
  обслуживания и освидетельствованием (поля, не отдельные таблицы)
* ``elevator_status_events`` — append-only журнал событий по лифту
* ``elevator_maintenance_occurrences`` — плановые ТО / освидетельствования

Политика:

* Идентичность лифта — ``(building_id, entrance_number, elevator_number)``
  среди неархивных (частичный уникальный индекс ``WHERE archived_at IS NULL``):
  архивная запись не мешает завести лифт на её место.
* ``current_status`` NULL до ввода в эксплуатацию (``is_commissioned``).
* ``request_number`` в журнале и графике — plain-строка БЕЗ FK на requests:
  история лифта обязана пережить удаление заявки (образец
  ``material_issues.request_number``).
* Дочерние таблицы — ON DELETE RESTRICT от лифта: журнал append-only, лифт
  архивируется (``archived_at``), а жёсткое удаление при наличии истории БД
  запрещает. ``passive_deletes=True`` на relationship обязателен: без него ORM
  при ``session.delete(elevator)`` попытался бы занулить NOT NULL
  ``elevator_id`` у детей вместо честного отказа FK.
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
    SmallInteger,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from uk_management_bot.database.session import Base

# Канон-ключи статуса лифта (локализация — через get_text/i18n, паттерн urgency)
ELEVATOR_STATUSES = ("working", "not_working", "under_repair", "maintenance")
# Виды событий журнала
ELEVATOR_EVENT_KINDS = (
    "status_changed",
    "commissioned",
    "archived",
    "contract_changed",
    "cert_changed",
    "passport_changed",
)
# Источник события: вручную / подсказка из заявки / InfraSafe / система
ELEVATOR_EVENT_SOURCES = ("manual", "request_hint", "infrasafe", "system")
# Виды плановых работ: техобслуживание / освидетельствование
OCCURRENCE_KINDS = ("maintenance", "certification")
# Состояния плановой работы
OCCURRENCE_STATES = ("planned", "done", "cancelled")


def _in_clause(column: str, values: tuple) -> str:
    return "{} IN ({})".format(column, ", ".join(f"'{v}'" for v in values))


class Elevator(Base):
    """Лифт: идентификация в доме, паспорт, статус, договор, освидетельствование.

    ``public_code`` — уникальный код для публичной страницы (генерируется
    сервисом при создании). ``version`` — оптимистичная блокировка карточки.
    """

    __tablename__ = "elevators"

    id = Column(Integer, primary_key=True)
    # Идентификация
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    entrance_number = Column(Integer, nullable=False)
    elevator_number = Column(Integer, nullable=False)

    # Паспорт: обязательные
    passport_number = Column(String(100), nullable=False)
    manufacturer = Column(String(200), nullable=False)
    serial_number = Column(String(100), nullable=False)
    # Паспорт: опциональные
    factory_number = Column(String(100), nullable=True)
    model = Column(String(200), nullable=True)
    production_year = Column(Integer, nullable=True)
    capacity_kg = Column(Integer, nullable=True)
    floors_served = Column(String(100), nullable=True)
    commissioned_at = Column(Date, nullable=True)

    # Статус (NULL до ввода в эксплуатацию)
    current_status = Column(String(20), nullable=True)
    status_since = Column(DateTime(timezone=True), nullable=True)
    downtime_reason = Column(Text, nullable=True)
    spare_part_expected_on = Column(Date, nullable=True)
    publish_downtime_details = Column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )

    # Договор обслуживания и освидетельствование
    service_org_name = Column(String(200), nullable=True)
    service_org_phone = Column(String(50), nullable=True)
    contract_number = Column(String(100), nullable=True)
    contract_until = Column(Date, nullable=True)
    cert_number = Column(String(100), nullable=True)
    cert_valid_until = Column(Date, nullable=True)
    cert_act_url = Column(String(500), nullable=True)

    # Напоминания: ступень эскалации по договору / освидетельствованию, простой
    contract_reminder_stage = Column(
        SmallInteger, nullable=False, server_default=text("0"), default=0
    )
    cert_reminder_stage = Column(
        SmallInteger, nullable=False, server_default=text("0"), default=0
    )
    downtime_reminded_at = Column(DateTime(timezone=True), nullable=True)

    # Публичность
    public_code = Column(String(32), nullable=False, unique=True)
    is_public = Column(Boolean, nullable=False, server_default=text("false"), default=False)

    # Жизненный цикл
    is_commissioned = Column(
        Boolean, nullable=False, server_default=text("false"), default=False
    )
    archived_at = Column(DateTime(timezone=True), nullable=True)
    archived_reason = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    version = Column(Integer, nullable=False, server_default=text("1"), default=1)

    # Lazy по умолчанию: списочные запросы сервиса ОБЯЗАНЫ грузить дом через
    # selectinload(Elevator.building), иначе N+1 на каждой карточке.
    building = relationship("Building")
    # passive_deletes=True — см. docstring модуля (RESTRICT вместо зануления).
    status_events = relationship(
        "ElevatorStatusEvent",
        back_populates="elevator",
        passive_deletes=True,
        order_by="ElevatorStatusEvent.occurred_at.desc()",
    )
    maintenance_occurrences = relationship(
        "ElevatorMaintenanceOccurrence",
        back_populates="elevator",
        passive_deletes=True,
        order_by="ElevatorMaintenanceOccurrence.due_on",
    )

    __table_args__ = (
        CheckConstraint(
            "current_status IS NULL OR " + _in_clause("current_status", ELEVATOR_STATUSES),
            name="ck_elevators_current_status",
        ),
        # Уникальность места лифта среди неархивных (partial — PostgreSQL и sqlite)
        Index(
            "uq_elevators_building_entrance_number_active",
            "building_id",
            "entrance_number",
            "elevator_number",
            unique=True,
            postgresql_where=text("archived_at IS NULL"),
            sqlite_where=text("archived_at IS NULL"),
        ),
    )

    def __repr__(self):
        return (
            f"<Elevator(id={self.id}, building_id={self.building_id}, "
            f"entrance={self.entrance_number}, number={self.elevator_number}, "
            f"status={self.current_status})>"
        )


class ElevatorStatusEvent(Base):
    """Событие журнала лифта (append-only).

    ``request_number`` — plain-строка без FK (см. docstring модуля).
    ``payload`` — произвольные детали события (snapshot изменённых полей и т.п.).
    """

    __tablename__ = "elevator_status_events"

    id = Column(Integer, primary_key=True)
    elevator_id = Column(
        Integer, ForeignKey("elevators.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    event_kind = Column(String(30), nullable=False)
    old_status = Column(String(20), nullable=True)
    new_status = Column(String(20), nullable=True)
    occurred_at = Column(DateTime(timezone=True), nullable=False)
    actor_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    source = Column(String(20), nullable=False)
    request_number = Column(String(15), nullable=True)
    reason = Column(Text, nullable=True)
    # with_variant → postgresql=JSONB, sqlite=JSON (тест-conftests). ORM==БД.
    payload = Column(JSON().with_variant(JSONB(), "postgresql"), nullable=True)

    elevator = relationship("Elevator", back_populates="status_events")

    __table_args__ = (
        CheckConstraint(
            _in_clause("event_kind", ELEVATOR_EVENT_KINDS),
            name="ck_elevator_status_events_event_kind",
        ),
        CheckConstraint(
            _in_clause("source", ELEVATOR_EVENT_SOURCES),
            name="ck_elevator_status_events_source",
        ),
    )

    def __repr__(self):
        return (
            f"<ElevatorStatusEvent(id={self.id}, elevator_id={self.elevator_id}, "
            f"kind={self.event_kind}, {self.old_status}->{self.new_status})>"
        )


class ElevatorMaintenanceOccurrence(Base):
    """Плановое ТО / освидетельствование лифта на дату.

    Среди неотменённых — не более одной записи на ``(elevator_id, kind, due_on)``
    (частичный уникальный индекс ``WHERE state <> 'cancelled'``).
    ``request_number`` — plain-строка без FK (см. docstring модуля).
    """

    __tablename__ = "elevator_maintenance_occurrences"

    id = Column(Integer, primary_key=True)
    elevator_id = Column(
        Integer, ForeignKey("elevators.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind = Column(String(20), nullable=False)
    due_on = Column(Date, nullable=False)
    state = Column(String(20), nullable=False, server_default="planned", default="planned")
    done_at = Column(DateTime(timezone=True), nullable=True)
    done_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    comment = Column(Text, nullable=True)
    request_number = Column(String(15), nullable=True)
    reminder_stage = Column(SmallInteger, nullable=False, server_default=text("0"), default=0)
    overdue_reminded_at = Column(DateTime(timezone=True), nullable=True)
    created_by_user_id = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    elevator = relationship("Elevator", back_populates="maintenance_occurrences")

    __table_args__ = (
        CheckConstraint(
            _in_clause("kind", OCCURRENCE_KINDS),
            name="ck_elevator_maintenance_occurrences_kind",
        ),
        CheckConstraint(
            _in_clause("state", OCCURRENCE_STATES),
            name="ck_elevator_maintenance_occurrences_state",
        ),
        Index(
            "uq_elevator_maintenance_occurrences_active",
            "elevator_id",
            "kind",
            "due_on",
            unique=True,
            postgresql_where=text("state <> 'cancelled'"),
            sqlite_where=text("state <> 'cancelled'"),
        ),
    )

    def __repr__(self):
        return (
            f"<ElevatorMaintenanceOccurrence(id={self.id}, elevator_id={self.elevator_id}, "
            f"kind={self.kind}, due_on={self.due_on}, state={self.state})>"
        )
