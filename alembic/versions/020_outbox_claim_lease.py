"""webhook_outbox claim/lease — PR-5 (CODE-01, closure-plan 2026-06-12)

Доставка outbox перестаёт держать FOR UPDATE SKIP LOCKED на время HTTP:
  1. claim-фаза: маленький батч под локом получает status='in_flight',
     уникальный claim_token, claimed_at; commit — лок снят;
  2. HTTP — вне транзакции (bounded concurrency);
  3. финализация — compare-and-set по (id, claim_token): протухшие/чужие
     попытки отбрасываются без side effects.
Reclaim: in_flight старше lease снова доступны claim'у. attempts расходуется
ТОЛЬКО подтверждённым неуспешным HTTP-результатом; crash → redelivery того же
event_id без расходования retry-budget. claim_count — наблюдаемость
crash-loop'ов, в dead-letter не участвует.

Схема: +claim_token VARCHAR(36) NULL, +claimed_at timestamptz NULL,
+claim_count INT NOT NULL DEFAULT 0; частичный индекс
ix_webhook_outbox_in_flight ON (claimed_at) WHERE status='in_flight'.

ИДЕМПОТЕНТНО: CI/локальный бутстрап = create_all + stamp + upgrade head —
колонки/индекс могут уже существовать из модели; создаём только при
отсутствии (паттерн миграций 016/017).

Rollback-порядок (runbook, строго): (1) остановить outbox-воркеры
(INFRASAFE_WEBHOOK_ENABLED=false + рестарт bot/api); (2) убедиться, что
активных отправок нет; (3) downgrade сам переводит in_flight->pending и
дропает схему; (4) откатить код; (5) запустить. Downgrade при живых воркерах
запрещён — воркер может финализировать запись после удаления схемы.

Revision ID: 020
Revises: 019
Create Date: 2026-06-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '020'
down_revision: Union[str, None] = '019'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLE = "webhook_outbox"
INDEX = "ix_webhook_outbox_in_flight"


def _existing_columns(bind) -> set:
    insp = sa.inspect(bind)
    return {c["name"] for c in insp.get_columns(TABLE)}


def _existing_indexes(bind) -> set:
    insp = sa.inspect(bind)
    return {i["name"] for i in insp.get_indexes(TABLE)}


def upgrade() -> None:
    bind = op.get_bind()
    cols = _existing_columns(bind)

    if "claim_token" not in cols:
        op.add_column(TABLE, sa.Column("claim_token", sa.String(36), nullable=True))
    if "claimed_at" not in cols:
        op.add_column(TABLE, sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    if "claim_count" not in cols:
        op.add_column(
            TABLE,
            sa.Column("claim_count", sa.Integer(), nullable=False, server_default="0"),
        )

    if INDEX not in _existing_indexes(bind):
        if bind.dialect.name == "postgresql":
            op.create_index(
                INDEX, TABLE, ["claimed_at"],
                postgresql_where=sa.text("status = 'in_flight'"),
            )
        else:
            op.create_index(INDEX, TABLE, ["claimed_at"])


def downgrade() -> None:
    bind = op.get_bind()

    # Вернуть зависшие in_flight в pending ДО удаления схемы — иначе записи
    # навсегда выпадут из выборки старого кода (он знает только pending).
    op.execute(sa.text("UPDATE webhook_outbox SET status = 'pending' WHERE status = 'in_flight'"))

    if INDEX in _existing_indexes(bind):
        op.drop_index(INDEX, table_name=TABLE)

    cols = _existing_columns(bind)
    for col in ("claim_count", "claimed_at", "claim_token"):
        if col in cols:
            op.drop_column(TABLE, col)
