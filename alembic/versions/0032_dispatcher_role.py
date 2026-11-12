"""Роль «Диспетчер»: приём заявок по телефону.

``rbac_roles``: системная роль ``dispatcher`` (режим меню с одной кнопкой
«Заявка по звонку»; права — ``callcenter.use``, ``addresses.read``,
``elevators.lookup`` в authz/catalog.py). Строка нужна, чтобы роль была видна
в карточке сотрудника и её права можно было менять в админке ролей
(``rbac_role_permissions`` ссылается на ``rbac_roles.key``).

Revision ID: 032
Revises: 031
Create Date: 2026-11-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "032"
down_revision: Union[str, None] = "031"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

ROLE = ("dispatcher", "Диспетчер", "Приём заявок по телефону из Mini App")


def upgrade() -> None:
    # ON CONFLICT: суперадмин мог уже завести свою роль с ключом dispatcher —
    # она становится системной (права и выданные роли сохраняются).
    key, title, description = ROLE
    op.execute(
        sa.text(
            "INSERT INTO rbac_roles (key, title, description, is_system) "
            "VALUES (:key, :title, :description, true) "
            "ON CONFLICT (key) DO UPDATE SET is_system = true"
        ).bindparams(key=key, title=title, description=description)
    )


def downgrade() -> None:
    # Переопределения прав роли уходят каскадом (FK rbac_role_permissions).
    op.execute("DELETE FROM rbac_roles WHERE key = 'dispatcher'")
