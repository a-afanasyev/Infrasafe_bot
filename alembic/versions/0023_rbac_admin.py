"""Админка ролей: роли, переопределения прав, версия для сброса кэша.

Действия (что вообще проверяется) остаются в коде — ``authz/catalog.py``.
Таблицы хранят только настраиваемое из веба:

* ``rbac_roles`` — роли. Засеваются 8 системных ролей (``is_system``): их нельзя
  удалить, только поменять права. Свои роли создаёт суперадмин.
* ``rbac_role_permissions`` — явное «разрешено/запрещено» для (роль, действие).
  Изначально пусто: без строк действуют права из каталога, то есть ровно
  текущее поведение — миграция полномочий не меняет.
* ``rbac_state`` — одна строка со счётчиком версий; процессы перечитывают
  права, увидев новую версию (``authz/store.py``).

Гранты не нужны: новые таблицы покрывает ALTER DEFAULT PRIVILEGES роли
миграций (scripts/dba_ownership_transfer.sql).

Revision ID: 023
Revises: 022
Create Date: 2026-10-10
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "023"
down_revision: Union[str, None] = "022"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SYSTEM_ROLES = (
    ("applicant", "Житель", "Подаёт заявки, свои авто и пропуска"),
    ("executor", "Исполнитель", "Выполняет заявки, работает в сменах"),
    ("manager", "Менеджер", "Управление заявками, персоналом, сменами"),
    ("inspector", "Обходчик", "Заявки обхода из бота"),
    ("admin", "Администратор бота", "Админ-панель бота наравне с менеджером"),
    ("system_admin", "Администратор охраны", "Модуль охраны целиком, склад, учёт ресурсов"),
    ("security_operator", "Оператор охраны", "Пост охраны: события, пропуска, фото"),
    ("resource_meter_entry", "Контролёр показаний", "Ввод показаний счётчиков из Mini App"),
)


def upgrade() -> None:
    op.create_table(
        "rbac_roles",
        sa.Column("key", sa.String(32), primary_key=True),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_table(
        "rbac_role_permissions",
        sa.Column("role_key", sa.String(32), sa.ForeignKey("rbac_roles.key", ondelete="CASCADE"),
                  primary_key=True),
        sa.Column("action_key", sa.String(64), primary_key=True),
        sa.Column("allowed", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "rbac_state",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("version", sa.BigInteger(), nullable=False, server_default="0"),
    )

    roles = sa.table(
        "rbac_roles",
        sa.column("key", sa.String), sa.column("title", sa.String),
        sa.column("description", sa.Text), sa.column("is_system", sa.Boolean),
    )
    op.bulk_insert(roles, [
        {"key": key, "title": title, "description": description, "is_system": True}
        for key, title, description in SYSTEM_ROLES
    ])
    state = sa.table("rbac_state", sa.column("id", sa.Integer), sa.column("version", sa.BigInteger))
    op.bulk_insert(state, [{"id": 1, "version": 1}])


def downgrade() -> None:
    op.drop_table("rbac_state")
    op.drop_table("rbac_role_permissions")
    op.drop_table("rbac_roles")
