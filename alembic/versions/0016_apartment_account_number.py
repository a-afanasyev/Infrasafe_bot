"""Link apartments to the isolated payment-control accounting perimeter.

⚠️ Деплой: create_unique_constraint строит уникальный индекс под ACCESS EXCLUSIVE
и на время построения блокирует чтения и записи по `apartments`. Таблица размером
в тысячи строк — это доли секунды, и рутинный деплой всё равно идёт с окном
`migrate` → пересборка/перезапуск api/app. Если таблица вырастет до сотен тысяч
строк, констрейнт добавлять через CONCURRENTLY-индекс + USING INDEX.
"""
import sqlalchemy as sa
from alembic import op

revision = "016"
down_revision = "015"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("apartments", sa.Column("account_number", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_apartments_account_number", "apartments", ["account_number"])


def downgrade():
    op.drop_constraint("uq_apartments_account_number", "apartments", type_="unique")
    op.drop_column("apartments", "account_number")
