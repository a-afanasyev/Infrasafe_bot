"""backfill requests.urgency: legacy-рус → канон-ключи (TASK 17)

Заявки, созданные API/коллцентром/InfraSafe до канонизации, хранят русский
текст ("Обычная"/"Средняя"/"Срочная"/"Критическая"); бот уже писал ключи.
Эта data-миграция приводит всё к канон-ключам low/medium/high/critical.

Идемпотентна (повторный запуск — no-op) и self-verifying: после конвертации
падает, если остались неканонические значения (postflight-gate). Логика —
в ``uk_management_bot.database.urgency_backfill`` (общая с тестом).

Alembic исполняется в api-контейнере на старте (entrypoint-api.sh), до
обслуживания запросов — см. план rollout.

Revision ID: 015
Revises: 014
Create Date: 2026-06-05
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from uk_management_bot.database.urgency_backfill import backfill_urgency_to_keys
from uk_management_bot.utils.constants import URGENCY_RU_TO_KEY

revision: str = '015'
down_revision: Union[str, None] = '014'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "requests" not in insp.get_table_names():
        return  # no-op: пустой/новый bootstrap, заявок ещё нет
    backfill_urgency_to_keys(conn)


def downgrade() -> None:
    # Обратная конвертация ключ→рус (для rollback). Идемпотентна.
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if "requests" not in insp.get_table_names():
        return
    key_to_ru = {k: ru for ru, k in URGENCY_RU_TO_KEY.items()}
    cases = " ".join(f"WHEN '{k}' THEN '{ru}'" for k, ru in key_to_ru.items())
    keys = ", ".join(f"'{k}'" for k in key_to_ru)
    conn.execute(sa.text(
        f"UPDATE requests SET urgency = CASE urgency {cases} ELSE urgency END "
        f"WHERE urgency IN ({keys})"
    ))
