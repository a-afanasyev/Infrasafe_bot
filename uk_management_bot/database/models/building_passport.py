"""Модуль «Паспорт дома»: рабочий паспорт, подписанные редакции, журнал, фото.

Опорные решения (план ~/.claude/plans/cozy-hopping-nova.md):

* рабочий паспорт (``building_passports``) — один на дом; значения в JSON, состав
  формы задаёт схема в коде (``services/building_passport/schema.py``);
* подписание создаёт неизменяемую редакцию (``building_passport_revisions``) со
  своей копией схемы и эталона формы — старый паспорт воспроизводится после
  любой правки схемы; возврат в работу редакцию не трогает;
* ссылки на ``users`` — только ``SET NULL`` с именем текстом рядом: сотрудник в УК
  удаляется физически, и ни блокировать это, ни терять журнал нельзя;
* ссылка на ``buildings`` без каскада: дом деактивируется, а не удаляется.
"""
from sqlalchemy import (
    JSON,
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
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func

from uk_management_bot.database.session import Base

PASSPORT_STATUSES = ("not_started", "collecting", "inspected", "filled", "signed")
PHOTO_STATES = ("pending", "done", "refused", "abandoned")


def _json():
    return JSON().with_variant(JSONB(), "postgresql")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _user_fk():
    return Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)


class BuildingPassport(Base):
    """Рабочий паспорт дома. ``version`` растёт при каждой записи."""

    __tablename__ = "building_passports"
    __table_args__ = (
        UniqueConstraint("building_id", name="uq_building_passports_building"),
        CheckConstraint(_in("status", PASSPORT_STATUSES), name="ck_building_passports_status"),
    )

    id = Column(Integer, primary_key=True)
    building_id = Column(Integer, ForeignKey("buildings.id"), nullable=False)
    status = Column(String(20), nullable=False, default="not_started")
    version = Column(Integer, nullable=False, default=1)
    schema_version = Column(Integer, nullable=False)
    # {ключ поля: значение, ключ группы: [строки], «<ключ>_text»: расшифровка «другое»}
    values = Column(_json(), nullable=False, default=dict)
    unknown = Column(_json(), nullable=False, default=dict)       # {ключ: причина «нет данных»}
    absent = Column(_json(), nullable=False, default=list)        # [ключи групп «нет в доме»]
    shared_from = Column(_json(), nullable=False, default=dict)   # {объект: id основного дома}
    field_versions = Column(_json(), nullable=False, default=dict)  # {ключ: версия последней правки}
    inspection_date = Column(Date, nullable=True)
    responsible_name = Column(String(200), nullable=True)
    note = Column(Text, nullable=True)
    revision_no = Column(Integer, nullable=False, default=0)  # номер последней подписанной редакции
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=True)
    updated_by = _user_fk()
    updated_by_name = Column(String(200), nullable=True)


class BuildingPassportRevision(Base):
    """Подписанная редакция: только добавление, всё нужное для печати — внутри."""

    __tablename__ = "building_passport_revisions"
    __table_args__ = (
        UniqueConstraint("passport_id", "revision_no", name="uq_building_passport_revisions_no"),
    )

    id = Column(Integer, primary_key=True)
    passport_id = Column(Integer, ForeignKey("building_passports.id"), nullable=False)
    revision_no = Column(Integer, nullable=False)
    passport_version = Column(Integer, nullable=False)
    schema_version = Column(Integer, nullable=False)
    schema = Column(_json(), nullable=False)   # копия схемы на момент подписания
    form = Column(_json(), nullable=False)     # копия эталона формы (подзаголовки, названия строк)
    values = Column(_json(), nullable=False)   # с вычисляемыми и скопированными общими значениями
    unknown = Column(_json(), nullable=False)
    absent = Column(_json(), nullable=False)
    shared_from = Column(_json(), nullable=False)
    meta = Column(_json(), nullable=False)     # дата осмотра, ответственный, примечание, адрес дома
    photos = Column(_json(), nullable=False)   # [{section, media_id, uploaded_by_name, uploaded_at}]
    signed_by = _user_fk()
    signed_by_name = Column(String(200), nullable=True)
    signed_at = Column(DateTime(timezone=True), nullable=False)


class BuildingPassportEvent(Base):
    """Журнал правок и смен статуса: только добавление."""

    __tablename__ = "building_passport_events"
    __table_args__ = (Index("ix_building_passport_events_passport", "passport_id", "id"),)

    id = Column(Integer, primary_key=True)
    passport_id = Column(Integer, ForeignKey("building_passports.id"), nullable=False)
    kind = Column(String(20), nullable=False)  # values | status | photo
    changes = Column(_json(), nullable=False)  # {ключ: [было, стало]}
    reason = Column(Text, nullable=True)
    actor_id = _user_fk()
    actor_name = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class BuildingPassportPhoto(Base):
    """Фото раздела: одна строка — одна операция загрузки с ключом от клиента."""

    __tablename__ = "building_passport_photos"
    __table_args__ = (
        UniqueConstraint("op_key", name="uq_building_passport_photos_op_key"),
        UniqueConstraint("media_ref", name="uq_building_passport_photos_media_ref"),
        CheckConstraint(_in("state", PHOTO_STATES), name="ck_building_passport_photos_state"),
        Index("ix_building_passport_photos_section", "passport_id", "section"),
    )

    id = Column(Integer, primary_key=True)
    passport_id = Column(Integer, ForeignKey("building_passports.id"), nullable=False)
    section = Column(String(40), nullable=False)
    op_key = Column(String(36), nullable=False)
    # «Номер заявки» для медиа-сервиса, выведенный из ключа операции: по нему
    # находится уже загруженный файл, если media_id не успел записаться.
    media_ref = Column(String(20), nullable=False)
    upload_sha256 = Column(String(64), nullable=False)
    state = Column(String(10), nullable=False, default="pending")
    media_id = Column(Integer, nullable=True)
    claim_token = Column(String(36), nullable=True)
    claimed_at = Column(DateTime(timezone=True), nullable=True)
    uploaded_by = _user_fk()
    uploaded_by_name = Column(String(200), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    removed_at = Column(DateTime(timezone=True), nullable=True)  # убрано из рабочего набора
