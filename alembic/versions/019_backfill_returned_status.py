"""backfill requests.status: legacy-кодировка → канон (SSOT cutover PR3)

Приводит хранилище к канон-модели A:
  - Исполнено + is_returned=True → «Возвращена» (is_returned сохраняется);
  - Выполнена + manager_confirmed=True ¬возвращена → «Исполнено».

Идемпотентна и self-verifying (postflight-гейт). Логика — в
``uk_management_bot.database.returned_status_backfill`` (общая с тестом).

После этой миграции canonical-writer пишет «Возвращена» напрямую
(_storage_status=identity), а наружу статус проецируется как «Исполнено»
до PR7 (project_public_status). downgrade откатывает только чистую часть
(Возвращена→Исполнено); конверсия Выполнена→Исполнено помечена one-way.

Revision ID: 019
Revises: 018
Create Date: 2026-06-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from uk_management_bot.database.returned_status_backfill import (
    backfill_returned_status,
    revert_returned_status,
)

revision: str = '019'
down_revision: Union[str, None] = '018'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "requests" not in insp.get_table_names():
        return  # no-op: пустой/новый bootstrap, заявок ещё нет
    backfill_returned_status(conn)


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "requests" not in insp.get_table_names():
        return
    revert_returned_status(conn)
