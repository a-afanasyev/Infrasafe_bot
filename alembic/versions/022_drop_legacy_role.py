"""PR-31 / DB-060: drop legacy users.role column

ARCH-07 (PR-30) свёл все чтения/записи устаревшей колонки ``users.role`` к трём
хелперам ``utils/auth_helpers`` (legacy_role_filter / sync_legacy_role /
legacy_primary_role). PR-31 переключил их нутро на ``roles`` (JSON-массив) +
``active_role`` и удаляет саму колонку. Источник истины ролей — ``users.roles``
(+ ``active_role``).

Идемпотентно и кросс-диалектно: дроп только если колонка реально есть (на CI
схема строится из модели через create_all — колонки role там уже нет → пропуск).
Дроп идёт через batch_alter_table (sqlite требует пересоздания таблицы; postgres —
прямой ALTER).

DB-049 (roles → jsonb + GIN) НЕ входит в эту миграцию: на таблице users в
единицы строк GIN-индекс — преждевременная оптимизация, а «правильный» перевод
на нативный jsonb требует смены write-контракта (код хранит roles как
json.dumps-строку) — отдельная задача при росте таблицы.

Revision ID: 022
Revises: 021
Create Date: 2026-06-19
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '022'
down_revision: Union[str, None] = '021'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_role_column() -> bool:
    bind = op.get_bind()
    return 'role' in {c['name'] for c in sa.inspect(bind).get_columns('users')}


def upgrade() -> None:
    if _has_role_column():
        with op.batch_alter_table('users') as batch:
            batch.drop_column('role')


def downgrade() -> None:
    if not _has_role_column():
        with op.batch_alter_table('users') as batch:
            batch.add_column(
                sa.Column('role', sa.String(50), nullable=False, server_default='applicant')
            )
