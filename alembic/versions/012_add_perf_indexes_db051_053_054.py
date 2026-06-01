"""add perf indexes + board_config FK (DB-051 / DB-053 / DB-054)

Hot-path indexes that were missing:

* DB-051 — ``notifications``: FK columns ``user_id`` and ``request_number_fk``
  had no index, and the "unread notifications for a user" query (the badge /
  inbox hot path) did a seq-scan + filter. Adds the two FK indexes plus a
  partial index ``(user_id) WHERE is_read = false``.
* DB-053 — ``webhook_outbox``: the outbox processor polls
  ``WHERE status = 'pending' ORDER BY created_at``. Adds a partial index
  ``(created_at) WHERE status = 'pending'`` so the poll is index-only on the
  (normally tiny) pending set instead of scanning the whole table.
* DB-054 — ``board_config.updated_by`` was a bare ``Integer`` with neither a
  FK nor an index. Adds an index and a ``FOREIGN KEY -> users(id) ON DELETE
  SET NULL`` (so deleting the editing manager nulls the audit pointer instead
  of leaving a dangling id).

Idempotent on purpose (same contract as migration 011): the CI/dev bootstrap
runs ORM ``create_all`` (the models now declare these indexes + FK) BEFORE
``alembic upgrade head``, so the objects may already exist. ``CREATE INDEX IF
NOT EXISTS`` and the ``pg_constraint`` guard make this a no-op on that path and
a real create on a pre-existing prod schema. Names match SQLAlchemy defaults
(``ix_<table>_<column>`` / ``board_config_updated_by_fkey``) so both paths
converge on identical objects.

Plain (not CONCURRENTLY) index builds: the target tables are small; the brief
lock is negligible. Switch to a CONCURRENTLY autocommit-block migration if any
of them grows large enough that an online build matters.

Revision ID: 012
Revises: 011
Create Date: 2026-06-01
"""
from typing import Sequence, Union

from alembic import op

revision: str = '012'
down_revision: Union[str, None] = '011'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# (index_name, raw CREATE body) — plain + partial indexes, all idempotent.
_INDEXES = (
    ("ix_notifications_user_id",
     'CREATE INDEX IF NOT EXISTS ix_notifications_user_id ON notifications ("user_id")'),
    ("ix_notifications_request_number_fk",
     'CREATE INDEX IF NOT EXISTS ix_notifications_request_number_fk ON notifications ("request_number_fk")'),
    ("ix_notifications_user_unread",
     "CREATE INDEX IF NOT EXISTS ix_notifications_user_unread ON notifications (\"user_id\") WHERE is_read = false"),
    ("ix_webhook_outbox_pending",
     "CREATE INDEX IF NOT EXISTS ix_webhook_outbox_pending ON webhook_outbox (\"created_at\") WHERE status = 'pending'"),
    ("ix_board_config_updated_by",
     'CREATE INDEX IF NOT EXISTS ix_board_config_updated_by ON board_config ("updated_by")'),
)

# DB-054 FK — guarded add (idempotent vs create_all having already made it),
# with a defensive orphan-nulling so VALIDATE can't fail on stale data.
_ADD_BOARD_CONFIG_FK = """
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid = 'board_config'::regclass
          AND contype = 'f'
          AND conname = 'board_config_updated_by_fkey'
    ) THEN
        UPDATE board_config SET updated_by = NULL
         WHERE updated_by IS NOT NULL
           AND NOT EXISTS (SELECT 1 FROM users WHERE id = board_config.updated_by);
        ALTER TABLE board_config
            ADD CONSTRAINT board_config_updated_by_fkey
            FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE SET NULL;
    END IF;
END $$;
"""


def upgrade() -> None:
    for _name, ddl in _INDEXES:
        op.execute(ddl)
    op.execute(_ADD_BOARD_CONFIG_FK)


def downgrade() -> None:
    op.execute("ALTER TABLE board_config DROP CONSTRAINT IF EXISTS board_config_updated_by_fkey")
    for name, _ddl in _INDEXES:
        op.execute(f"DROP INDEX IF EXISTS {name}")
