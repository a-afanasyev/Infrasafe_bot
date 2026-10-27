"""Роль «Инженер» и счётчик возвратов заявки.

* ``rbac_roles``: системная роль ``engineer`` (капабилити, выдаётся вместе с
  executor; права — действие ``requests.engineering`` в authz/catalog.py).
  Строка нужна, чтобы суперадмин мог менять её права в админке
  (``rbac_role_permissions`` ссылается на ``rbac_roles.key``).
* ``requests.return_count``: сколько раз работу вернули на доработку.
  ADD COLUMN с константным DEFAULT в PG 11+ — изменение только каталога.
  Бэкфилла нет: история возвратов ненадёжна, у старых заявок 0.

Revision ID: 027
Revises: 026
Create Date: 2026-10-27
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "027"
down_revision: Union[str, None] = "026"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

SYSTEM_ROLES = (
    ("engineer", "Инженер", "Эскалации InfraSafe, работа без смены, передача мастеру"),
)


def upgrade() -> None:
    # ON CONFLICT: суперадмин мог уже завести свою роль с ключом engineer —
    # она становится системной (права и выданные роли сохраняются).
    for key, title, description in SYSTEM_ROLES:
        op.execute(
            sa.text(
                "INSERT INTO rbac_roles (key, title, description, is_system) "
                "VALUES (:key, :title, :description, true) "
                "ON CONFLICT (key) DO UPDATE SET is_system = true"
            ).bindparams(key=key, title=title, description=description)
        )
    op.add_column(
        "requests",
        sa.Column("return_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("requests", "return_count")
    # Переопределения прав роли уходят каскадом (FK rbac_role_permissions).
    op.execute("DELETE FROM rbac_roles WHERE key = 'engineer'")
