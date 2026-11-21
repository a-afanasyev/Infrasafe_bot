"""Модуль «Паспорт дома»: рабочий паспорт, подписанные редакции, журнал, фото.

DARK: без ``PASSPORT_ENABLED`` роутер ``/api/v2/passports`` отвечает 404 — таблицы
остаются пустыми. Только создание четырёх таблиц: существующие таблицы и
данные не меняются.

* ``building_passports`` — один рабочий паспорт на дом; значения в JSON, состав
  формы задаёт схема в коде;
* ``building_passport_revisions`` — подписанные редакции со своей копией схемы и
  эталона формы, только добавление;
* ``building_passport_events`` — журнал правок и смен статуса, только добавление;
* ``building_passport_photos`` — операции загрузки фото с ключом от клиента.

Ссылки на ``users`` — ``SET NULL`` (сотрудник удаляется физически, имя хранится
текстом рядом); на ``buildings`` — без каскада (дом деактивируется).

⚠️ После начала заполнения ``downgrade`` не выполнять: он удаляет паспорта.

Revision ID: 036
Revises: 035
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "036"
down_revision: Union[str, None] = "035"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

PASSPORT_STATUSES = ("not_started", "collecting", "inspected", "filled", "signed")
PHOTO_STATES = ("pending", "done", "refused", "abandoned")


def _json() -> sa.types.TypeEngine:
    return sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} IN ({', '.join(repr(v) for v in values)})"


def _now() -> sa.Column:
    return sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def _user(column: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint([column], ["users.id"], ondelete="SET NULL")


def upgrade() -> None:
    op.create_table(
        "building_passports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("building_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("values", _json(), nullable=False),
        sa.Column("unknown", _json(), nullable=False),
        sa.Column("absent", _json(), nullable=False),
        sa.Column("shared_from", _json(), nullable=False),
        sa.Column("field_versions", _json(), nullable=False),
        sa.Column("inspection_date", sa.Date(), nullable=True),
        sa.Column("responsible_name", sa.String(length=200), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        _now(),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_by", sa.Integer(), nullable=True),
        sa.Column("updated_by_name", sa.String(length=200), nullable=True),
        sa.CheckConstraint(_in("status", PASSPORT_STATUSES), name="ck_building_passports_status"),
        sa.ForeignKeyConstraint(["building_id"], ["buildings.id"]),
        _user("updated_by"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("building_id", name="uq_building_passports_building"),
    )

    op.create_table(
        "building_passport_revisions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("passport_id", sa.Integer(), nullable=False),
        sa.Column("revision_no", sa.Integer(), nullable=False),
        sa.Column("passport_version", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False),
        sa.Column("schema", _json(), nullable=False),
        sa.Column("form", _json(), nullable=False),
        sa.Column("values", _json(), nullable=False),
        sa.Column("unknown", _json(), nullable=False),
        sa.Column("absent", _json(), nullable=False),
        sa.Column("shared_from", _json(), nullable=False),
        sa.Column("meta", _json(), nullable=False),
        sa.Column("photos", _json(), nullable=False),
        sa.Column("signed_by", sa.Integer(), nullable=True),
        sa.Column("signed_by_name", sa.String(length=200), nullable=True),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["passport_id"], ["building_passports.id"]),
        _user("signed_by"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("passport_id", "revision_no", name="uq_building_passport_revisions_no"),
    )

    op.create_table(
        "building_passport_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("passport_id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("changes", _json(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("actor_id", sa.Integer(), nullable=True),
        sa.Column("actor_name", sa.String(length=200), nullable=True),
        _now(),
        sa.ForeignKeyConstraint(["passport_id"], ["building_passports.id"]),
        _user("actor_id"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_building_passport_events_passport", "building_passport_events", ["passport_id", "id"])

    op.create_table(
        "building_passport_photos",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("passport_id", sa.Integer(), nullable=False),
        sa.Column("section", sa.String(length=40), nullable=False),
        sa.Column("op_key", sa.String(length=36), nullable=False),
        sa.Column("media_ref", sa.String(length=20), nullable=False),
        sa.Column("upload_sha256", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=10), nullable=False),
        sa.Column("media_id", sa.Integer(), nullable=True),
        sa.Column("claim_token", sa.String(length=36), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("uploaded_by", sa.Integer(), nullable=True),
        sa.Column("uploaded_by_name", sa.String(length=200), nullable=True),
        _now(),
        sa.Column("removed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_in("state", PHOTO_STATES), name="ck_building_passport_photos_state"),
        sa.ForeignKeyConstraint(["passport_id"], ["building_passports.id"]),
        _user("uploaded_by"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("op_key", name="uq_building_passport_photos_op_key"),
        sa.UniqueConstraint("media_ref", name="uq_building_passport_photos_media_ref"),
    )
    op.create_index("ix_building_passport_photos_section", "building_passport_photos", ["passport_id", "section"])


def downgrade() -> None:
    for table in ("building_passport_photos", "building_passport_events", "building_passport_revisions",
                  "building_passports"):
        op.drop_table(table)
