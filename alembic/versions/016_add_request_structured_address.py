"""structured 3-level request address: building_id / yard_id / address_type

План «Обходчик» (2026-06). Заявка получает 3-уровневый адрес (двор/дом/
квартира) со серверной проверкой принадлежности. Добавляем nullable
`building_id`, `yard_id` (FK ON DELETE RESTRICT) и дискриминатор `address_type`
(legacy|yard|building|apartment) с CHECK на соответствие типа заполненному FK.

**Пилотный путь (одна revision, writers остановлены).** Система в пилоте,
трафик низкий → zero-downtime-машинерия (expand/contract в 2 релиза,
CREATE INDEX CONCURRENTLY, возобновляемый батч-backfill, NOT VALID→VALIDATE)
избыточна. Эта revision применяется при остановленных writers
(`docker compose stop app api`) и делает всё разом:
  1. ADD COLUMN building_id / yard_id / address_type (nullable) + индексы;
  2. inline-backfill address_type одним UPDATE (writers стоят, строк мало);
  3. SET NOT NULL на address_type + CHECK(тип↔FK);
  4. FK building_id/yard_id → ON DELETE RESTRICT.

Существующий apartment_id FK остаётся ON DELETE SET NULL (миграция 007): для
немигрированных/legacy строк (address_type IS NULL) обнуление безопасно, а для
address_type='apartment' CHECK сам блокирует обнуление; от каскадного удаления
дополнительно защищает purge-гард на уровне приложения (addresses/router).

Тесты схему строят через Base.metadata.create_all (CHECK живёт и в модели),
поэтому эта миграция исполняется только в api-контейнере/на проде (Postgres).
SQLite-fallback оставлен для совместимости с возможным replay миграций.

Revision ID: 016
Revises: 015
Create Date: 2026-06-09
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '016'
down_revision: Union[str, None] = '015'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


CHECK_NAME = 'ck_requests_address_type_fk'
CHECK_SQL = (
    "address_type IS NULL OR ("
    " (address_type = 'apartment' AND apartment_id IS NOT NULL AND building_id IS NULL AND yard_id IS NULL)"
    " OR (address_type = 'building' AND building_id IS NOT NULL AND apartment_id IS NULL AND yard_id IS NULL)"
    " OR (address_type = 'yard' AND yard_id IS NOT NULL AND apartment_id IS NULL AND building_id IS NULL)"
    " OR (address_type = 'legacy' AND apartment_id IS NULL AND building_id IS NULL AND yard_id IS NULL)"
    ")"
)
BACKFILL_SQL = (
    "UPDATE requests SET address_type = CASE "
    "WHEN apartment_id IS NOT NULL THEN 'apartment' "
    "WHEN building_id IS NOT NULL THEN 'building' "
    "WHEN yard_id IS NOT NULL THEN 'yard' "
    "ELSE 'legacy' END "
    "WHERE address_type IS NULL"
)


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == 'postgresql'


def upgrade() -> None:
    # 1. Колонки (nullable) + индексы.
    op.add_column('requests', sa.Column('building_id', sa.Integer(), nullable=True))
    op.add_column('requests', sa.Column('yard_id', sa.Integer(), nullable=True))
    op.add_column('requests', sa.Column('address_type', sa.String(length=20), nullable=True))
    op.create_index('ix_requests_building_id', 'requests', ['building_id'])
    op.create_index('ix_requests_yard_id', 'requests', ['yard_id'])

    # 2. Inline-backfill дискриминатора (строго WHERE address_type IS NULL —
    #    чтобы не перезаписать уже проставленные значения при повторном прогоне).
    op.execute(BACKFILL_SQL)

    # 3. NOT NULL на address_type + CHECK(тип↔FK).
    op.alter_column('requests', 'address_type', nullable=False)
    op.create_check_constraint(CHECK_NAME, 'requests', CHECK_SQL)

    # 4. FK building_id/yard_id → ON DELETE RESTRICT.
    op.create_foreign_key(
        'requests_building_id_fkey', 'requests', 'buildings',
        ['building_id'], ['id'], ondelete='RESTRICT',
    )
    op.create_foreign_key(
        'requests_yard_id_fkey', 'requests', 'yards',
        ['yard_id'], ['id'], ondelete='RESTRICT',
    )


def downgrade() -> None:
    op.drop_constraint('requests_yard_id_fkey', 'requests', type_='foreignkey')
    op.drop_constraint('requests_building_id_fkey', 'requests', type_='foreignkey')
    op.drop_constraint(CHECK_NAME, 'requests', type_='check')
    op.drop_index('ix_requests_yard_id', table_name='requests')
    op.drop_index('ix_requests_building_id', table_name='requests')
    op.drop_column('requests', 'address_type')
    op.drop_column('requests', 'yard_id')
    op.drop_column('requests', 'building_id')
