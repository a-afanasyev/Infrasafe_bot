"""request_number_counters — gap-safe счётчик номеров заявок (PR5, SSOT-кластер #1)

Заменяет три расходившиеся стратегии генерации YYMMDD-NNN:
  1. RequestNumberService — лексикографический `ORDER BY request_number DESC`
     (ломается после 999: '260617-1000' < '260617-999') + time-fallback;
  2. api/requests/router._next_count + callcenter — COUNT(*)+1
     (переиспользует номер после удаления строки);
  3. services/inbound_alert — тот же COUNT(*)+1.

Новый механизм: атомарный UPSERT…RETURNING по строке дня в
request_number_counters (см. RequestNumberService.next_number). Счётчик
монотонен — удаление заявки с MAX-суффиксом не приводит к повторной выдаче.

Seed: инициализируем счётчик каждого существующего дня из ЧИСЛОВОГО
MAX(suffix) (CAST(SUBSTR(request_number, 8) AS INTEGER) — суффикс начинается
с 8-й позиции, префикс 'YYMMDD-' = 7 символов). Это атомарно закрывает
коллизии со старыми номерами при переключении генератора (риск 24 плана).
Генератор дополнительно self-seed'ится из MAX при отсутствии строки дня —
покрывает заявки, созданные старым кодом между миграцией и рестартом бота.

ИДЕМПОТЕНТНО: CI/локальный бутстрап = create_all + stamp + upgrade head —
после create_all таблица уже существует (модель RequestNumberCounter);
создаём только при отсутствии, seed — ON CONFLICT DO NOTHING (Postgres).
Тесты строят схему через create_all; эта миграция исполняется в
api-контейнере/на проде (Postgres).

Revision ID: 017
Revises: 016
Create Date: 2026-06-10
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '017'
down_revision: Union[str, None] = '016'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


TABLE = "request_number_counters"

# Postgres-seed: по одному ряду на каждый существующий день, last_seq =
# числовой MAX(suffix). Нечисловые суффиксы исключены WHERE-регэкспом
# (теоретические артефакты time-fallback'а всё равно числовые, но CAST
# на Postgres падает жёстко — защищаемся).
SEED_SQL = """
INSERT INTO request_number_counters (day_prefix, last_seq)
SELECT SUBSTR(request_number, 1, 6) AS day_prefix,
       MAX(CAST(SUBSTR(request_number, 8) AS INTEGER)) AS last_seq
FROM requests
WHERE request_number ~ '^[0-9]{6}-[0-9]+$'
GROUP BY SUBSTR(request_number, 1, 6)
ON CONFLICT (day_prefix) DO NOTHING
"""


def upgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)

    if TABLE not in insp.get_table_names():
        op.create_table(
            TABLE,
            sa.Column("day_prefix", sa.String(length=6), primary_key=True),
            sa.Column("last_seq", sa.Integer(), nullable=False),
        )

    if "requests" in insp.get_table_names():
        if conn.dialect.name == "postgresql":
            op.execute(SEED_SQL)
        else:
            # SQLite (локальные прогоны): нет `~` и INSERT..ON CONFLICT по
            # подзапросу не нужен — seed выполняет self-seed генератора.
            pass


def downgrade() -> None:
    conn = op.get_bind()
    insp = sa.inspect(conn)
    if TABLE in insp.get_table_names():
        op.drop_table(TABLE)
