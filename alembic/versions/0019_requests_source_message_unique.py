"""AUD7-CODE-03: одно исходное сообщение группы — не более одной заявки.

Group Intake создаёт заявку из сообщения в ТГ-группе и пишет провенанс
``requests.source_chat_id`` / ``source_message_id``. Идемпотентность «Да»
держалась только на Redis (GETDEL), а правка кандидата шла GET → SETEX без
сравнения и воскрешала уже снятого кандидата — повторное «Да» давало вторую
заявку на то же сообщение. Redis-CAS закрывает гонку, а этот частичный
уникальный индекс — durable-инвариант, который переживает рестарт Redis,
истёкший TTL и повторную доставку апдейта. Заявки без источника (бот,
дашборд, TWA — ``source_message_id IS NULL``) не ограничены.

Перед миграцией дублей на продах не было (проверено 2026-09-18: profk — 38
заявок с источником, 0 дублей; infrasafe/105 — 0/0). При дублях миграция
упадёт на CREATE UNIQUE INDEX — чистить руками, не автоматически.

Revision ID: 019
Revises: 018
Create Date: 2026-09-18
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "019"
down_revision: Union[str, None] = "018"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEX = "uq_requests_source_message"
_WHERE = sa.text("source_message_id IS NOT NULL")


def upgrade() -> None:
    op.create_index(
        _INDEX,
        "requests",
        ["source_chat_id", "source_message_id"],
        unique=True,
        postgresql_where=_WHERE,
        sqlite_where=_WHERE,
    )


def downgrade() -> None:
    op.drop_index(_INDEX, table_name="requests")
