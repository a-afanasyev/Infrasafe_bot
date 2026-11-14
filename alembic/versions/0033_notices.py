"""Новости и уведомления: таблица ``notices`` + перенос из JSON витрины.

``notices`` — единый источник всего, что УК сообщает жителям (ручные новости,
плановые отключения, одобренные новости каналов, отключения от сотрудников).
Существующие ``board_config.data.announcements`` и ``planned_works`` переносятся
в таблицу и вычищаются из JSON: витрина теперь собирает эти списки из
``notices`` (services/notices/board.py), контракт ответа прежний.

Downgrade удаляет таблицу; перенесённые записи обратно в JSON не возвращаются
(перед upgrade на проде — бэкап БД).

Revision ID: 033
Revises: 032
Create Date: 2026-11-14
"""
import json
import os
from datetime import date, datetime, time, timezone
from typing import Optional, Sequence, Union
from zoneinfo import ZoneInfo

import sqlalchemy as sa
from alembic import op

revision: str = "033"
down_revision: Union[str, None] = "032"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TZ = ZoneInfo(os.environ.get("DISPLAY_TZ") or "Asia/Tashkent")


def _loc(value: object, lang: str) -> str:
    return str(value.get(lang) or "") if isinstance(value, dict) else ""


def _wall(raw: object) -> Optional[datetime]:
    """Наивная дата-время редактора витрины — настенное время объекта."""
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    return parsed.replace(tzinfo=_TZ) if parsed.tzinfo is None else parsed


def _work_window(work: dict) -> tuple[Optional[datetime], Optional[datetime], bool]:
    try:
        day = date.fromisoformat(str(work.get("date")))
    except ValueError:
        return None, None, True

    def at(raw: object, fallback: time) -> tuple[datetime, bool]:
        try:
            return datetime.combine(day, time.fromisoformat(str(raw)), tzinfo=_TZ), True
        except ValueError:
            return datetime.combine(day, fallback, tzinfo=_TZ), False

    start, has_start = at(work.get("time_from") or "", time.min)
    end, has_end = at(work.get("time_to") or "", time(23, 59))
    if end < start:  # «с 14:00 до 10:00» из старого редактора — до конца дня
        end = datetime.combine(day, time(23, 59), tzinfo=_TZ)
    return start, end, not (has_start or has_end)


def upgrade() -> None:
    notices = op.create_table(
        "notices",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="news"),
        sa.Column("resource", sa.String(length=20), nullable=True),
        sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
        sa.Column("news_item_id", sa.Integer(), nullable=True),
        sa.Column("title_ru", sa.Text(), nullable=False, server_default=""),
        sa.Column("title_uz", sa.Text(), nullable=False, server_default=""),
        sa.Column("text_ru", sa.Text(), nullable=False, server_default=""),
        sa.Column("text_uz", sa.Text(), nullable=False, server_default=""),
        sa.Column("place_ru", sa.Text(), nullable=False, server_default=""),
        sa.Column("place_uz", sa.Text(), nullable=False, server_default=""),
        sa.Column("icon", sa.String(length=16), nullable=False, server_default=""),
        sa.Column("important", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="draft"),
        sa.Column("publish_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("all_day", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope", sa.String(length=20), nullable=False, server_default="all"),
        sa.Column("scope_ids", sa.JSON(), nullable=False, server_default="[]"),
        sa.Column("broadcast_status", sa.String(length=20), nullable=False, server_default="none"),
        sa.Column("broadcast_attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("broadcast_next_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("broadcast_started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("broadcast_cursor", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("broadcast_details", sa.JSON(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("closed_by", sa.Integer(), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["news_item_id"], ["news_items.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["closed_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("news_item_id", name="uq_notices_news_item_id"),
    )
    op.create_index("ix_notices_status", "notices", ["status"])
    op.create_index("ix_notices_publish_at", "notices", ["publish_at"])
    op.create_index("ix_notices_broadcast_status", "notices", ["broadcast_status"])

    bind = op.get_bind()
    row = bind.execute(sa.text("SELECT data FROM board_config WHERE id = 1")).first()
    data = row[0] if row else None
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        return

    now = datetime.now(timezone.utc)
    known_news = {r[0] for r in bind.execute(sa.text("SELECT id FROM news_items"))}
    rows: list[dict] = []

    def items(key: str) -> list:
        value = data.get(key)
        return value if isinstance(value, list) else []

    linked: set[int] = set()
    for ann in items("announcements"):
        if not isinstance(ann, dict):
            continue
        legacy_id = str(ann.get("id") or "")
        news_id = int(legacy_id[5:]) if legacy_id.startswith("news-") and legacy_id[5:].isdigit() else None
        # Связь с новостью канала уникальна: повтор и осиротевшая ссылка — без связи.
        news_id = news_id if news_id in known_news and news_id not in linked else None
        if news_id is not None:
            linked.add(news_id)
        rows.append({
            "kind": "news", "source": "news_watch" if news_id else "manual", "news_item_id": news_id,
            "title_ru": _loc(ann.get("title"), "ru"), "title_uz": _loc(ann.get("title"), "uz"),
            "text_ru": _loc(ann.get("text"), "ru"), "text_uz": _loc(ann.get("text"), "uz"),
            "icon": str(ann.get("icon") or "")[:16], "important": bool(ann.get("important")),
            # Дата в будущем раньше не скрывала объявление — не скрываем и теперь.
            "status": "published", "publish_at": min(_wall(ann.get("published_at")) or now, now),
        })
    for work in items("planned_works"):
        if not isinstance(work, dict):
            continue
        starts_at, ends_at, all_day = _work_window(work)
        rows.append({
            "kind": "outage", "resource": "other", "source": "manual",
            "title_ru": _loc(work.get("title"), "ru"), "title_uz": _loc(work.get("title"), "uz"),
            "text_ru": _loc(work.get("text"), "ru"), "text_uz": _loc(work.get("text"), "uz"),
            "place_ru": _loc(work.get("place"), "ru"), "place_uz": _loc(work.get("place"), "uz"),
            "status": "published", "publish_at": now,
            "starts_at": starts_at, "ends_at": ends_at, "all_day": all_day,
        })
    if rows:
        # Пакетная вставка требует одинакового набора ключей у всех строк:
        # у новости нет окна и места, у плановой работы — иконки и связи с каналом.
        blank = {
            "resource": None, "news_item_id": None, "text_ru": "", "text_uz": "", "place_ru": "", "place_uz": "",
            "icon": "", "important": False, "starts_at": None, "ends_at": None, "all_day": False, "scope_ids": [],
        }
        op.bulk_insert(notices, [{**blank, **r} for r in rows])

    cleaned = {**data, "announcements": [], "planned_works": []}
    bind.execute(
        sa.text("UPDATE board_config SET data = CAST(:data AS JSONB) WHERE id = 1")
        .bindparams(data=json.dumps(cleaned, ensure_ascii=False))
    )


def downgrade() -> None:
    op.drop_index("ix_notices_broadcast_status", table_name="notices")
    op.drop_index("ix_notices_publish_at", table_name="notices")
    op.drop_index("ix_notices_status", table_name="notices")
    op.drop_table("notices")
