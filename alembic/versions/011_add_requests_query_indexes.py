"""add query/FK indexes on requests (DB-050/052)

The `requests` table is the hottest in the schema — filtered by `status`
(Kanban columns), joined/filtered by `user_id` and `executor_id`, and ordered
by `created_at`. None of these had an index (only `apartment_id` did), so each
becomes a sequential scan as the table grows. This adds single-column indexes
for the four hot columns.

Idempotent on purpose: the CI/dev bootstrap runs `create_all` from the ORM
models (which now declare `index=True`) BEFORE `alembic upgrade head`, so the
indexes may already exist when this migration runs. `CREATE INDEX IF NOT EXISTS`
makes the migration a no-op in that path and a real create on a pre-existing
prod schema (where create_all never ran). Index names match SQLAlchemy's
`index=True` default (`ix_<table>_<column>`) so both paths converge on the same
objects.

Index creation is plain (not CONCURRENTLY): `requests` is small (tens–hundreds
of rows) so the brief lock is negligible; if the table grows to where an online
build matters, switch to a CONCURRENTLY autocommit-block migration.

Revision ID: 011
Revises: 010
Create Date: 2026-05-31
"""
from typing import Sequence, Union

from alembic import op

revision: str = '011'
down_revision: Union[str, None] = '010'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_INDEXES = (
    ("ix_requests_status", "status"),
    ("ix_requests_user_id", "user_id"),
    ("ix_requests_executor_id", "executor_id"),
    ("ix_requests_created_at", "created_at"),
)


def upgrade() -> None:
    for index_name, column in _INDEXES:
        op.execute(
            f'CREATE INDEX IF NOT EXISTS {index_name} ON requests ("{column}")'
        )


def downgrade() -> None:
    for index_name, _column in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {index_name}")
