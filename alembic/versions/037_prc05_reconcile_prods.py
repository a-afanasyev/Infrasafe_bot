"""PRC-05: свести infrasafe-прод к profk (канон) ПЕРЕД squash-baseline.

profk и infrasafe оба @036, но infrasafe несёт легаси-объекты, которых на profk
нет: profk fresh-init'ился ПОЗЖЕ через create_all+migrations, и migration-гарды
(например 024 `if not _has_column(...)`) пропускали пере-создание, оставляя
create_all-канон. Итог — profk == будущему baseline (autogenerate из моделей),
infrasafe == baseline + ручной легаси. Сводим infrasafe к profk на СТАРОЙ цепочке
(до сквоша), чтобы diff(profk, infrasafe) == ∅ и baseline воспроизводил ОБА прода.

Изменения (все идемпотентны; на profk — no-op там, где объектов нет / уже есть):

DROP 14 индексов, которых нет на profk:
  * 11 дублей канонических `ix_*` (тот же столбец уже покрыт `ix_*`, либо PK):
      idx_requests_{created_at,executor_id,status,user_id},
      ix_requests_request_number (request_number — PK, уникальный индекс есть),
      idx_request_assignments_{executor_id,request_number},
      idx_request_comments_{request_number,user_id},
      idx_shift_assignments_{request_number,shift_id}.
  * 3 одиночных low-value индекса без канон-твина на profk (решение владельца —
    сводим к profk, который без них работает; столбцы низкокардинальные):
      idx_request_assignments_status, idx_request_comments_created_at,
      idx_shift_assignments_status.

CREATE 2 функциональных индекса на ОБА прода (решение владельца — закрепить):
  * idx_requests_category (объявлен и в модели Request.__table_args__);
  * idx_requests_date_prefix = substring((request_number)::text, 1, 6)
    (expr-индекс, postgres-only, в модель не выносится — ломает sqlite-create_all;
    исключён из alembic check в migration_include.FUNCTIONAL_INDEXES_EXCLUDED).
  IF NOT EXISTS: на infrasafe оба уже есть → no-op; на profk создаются.

RENAME FK shift_transfers: fk_shift_transfers_assigned_by_users (имя из миграции
024) → shift_transfers_assigned_by_fkey (default-имя create_all, канон на profk).

Portable: postgres-only. sqlite (conftest create_all) — ранний return: этих
объектов там нет, а date_prefix drift-гейт исключает.

Revision ID: 037
Revises: 036
Create Date: 2026-07-10
"""
from typing import Sequence, Union

from alembic import op

revision: str = "037"
down_revision: Union[str, None] = "036"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Индексы, которых НЕТ на profk (== baseline). DROP IF EXISTS → на profk no-op.
_DROP_INDEXES = (
    # дубли канонических ix_* (столбец уже покрыт) / PK-покрытый:
    "idx_requests_created_at",
    "idx_requests_executor_id",
    "idx_requests_status",
    "idx_requests_user_id",
    "ix_requests_request_number",
    "idx_request_assignments_executor_id",
    "idx_request_assignments_request_number",
    "idx_request_comments_request_number",
    "idx_request_comments_user_id",
    "idx_shift_assignments_request_number",
    "idx_shift_assignments_shift_id",
    # одиночные low-value без канон-твина (сводим к profk):
    "idx_request_assignments_status",
    "idx_request_comments_created_at",
    "idx_shift_assignments_status",
)

# Функциональные индексы, закрепляемые на ОБА прода (CREATE IF NOT EXISTS).
_CREATE_INDEXES = (
    ("idx_requests_category", "public.requests", "(category)"),
    ("idx_requests_date_prefix", "public.requests",
     '((substring((request_number)::text, 1, 6)))'),
)


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        # sqlite/CI create_all: этих объектов нет; date_prefix исключён из check.
        return

    for name in _DROP_INDEXES:
        op.execute(f'DROP INDEX IF EXISTS {name}')

    for name, table, expr in _CREATE_INDEXES:
        op.execute(f'CREATE INDEX IF NOT EXISTS {name} ON {table} USING btree {expr}')

    # FK rename к канону (create_all-default). Идемпотентно: переименовываем только
    # если старое имя есть, а канон отсутствует (на profk — оба условия ложны → no-op).
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'fk_shift_transfers_assigned_by_users'
                  AND conrelid = 'public.shift_transfers'::regclass
            ) AND NOT EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'shift_transfers_assigned_by_fkey'
                  AND conrelid = 'public.shift_transfers'::regclass
            ) THEN
                ALTER TABLE public.shift_transfers
                    RENAME CONSTRAINT fk_shift_transfers_assigned_by_users
                    TO shift_transfers_assigned_by_fkey;
            END IF;
        END $$;
        """
    )


def downgrade() -> None:
    """Сведение двух дивергентных продов НЕ реверсируется чисто (нельзя знать,
    какие легаси-объекты были на каком инстансе). Обратимо только FK-имя; дропнутые
    легаси idx_* и закреплённые функциональные индексы (последние теперь model-owned
    / контрактные) НЕ трогаем — иначе создали бы drift модель↔БД. Эта миграция всё
    равно уходит в squash-baseline; downgrade нужен лишь для формальной обратимости
    FK-переименования."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint
                WHERE conname = 'shift_transfers_assigned_by_fkey'
                  AND conrelid = 'public.shift_transfers'::regclass
            ) THEN
                ALTER TABLE public.shift_transfers
                    RENAME CONSTRAINT shift_transfers_assigned_by_fkey
                    TO fk_shift_transfers_assigned_by_users;
            END IF;
        END $$;
        """
    )
