"""APIFE-14 / F-02: refresh-token family reuse detection.

Adds token-family lineage so a replayed *rotated* token can be detected and the
whole family revoked fail-closed, without the migration-free "any revoked token
nukes all sessions" foot-gun (a stale logout token would DoS the account).

- family_id: one family per login; rotation keeps the family, so a reused rotated
  token maps to exactly the sessions to kill.
- parent_token_id: lineage (self-FK, SET NULL) — audit only.
- revocation_reason: distinguishes rotated | logout | reuse | admin, so only a
  `rotated` replay triggers family revocation.

Backfill: every existing token becomes its own family (family_id = id). Existing
revoked rows get NO reason (NULL) — labelling them would make an old logout look
like a proven rotation replay.

Two-step family_id (add nullable → backfill → NOT NULL) so it never fails on
existing rows. Reversible downgrade (drops the three columns + index + FK).

Revision ID: 003
Revises: 002
Create Date: 2026-07-11
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("refresh_tokens", sa.Column("family_id", sa.String(length=36), nullable=True))
    op.add_column("refresh_tokens", sa.Column("parent_token_id", sa.Integer(), nullable=True))
    op.add_column("refresh_tokens", sa.Column("revocation_reason", sa.String(length=16), nullable=True))

    # Each pre-existing token is its own family. NULL reason on already-revoked
    # rows is intentional (see module docstring).
    op.execute("UPDATE refresh_tokens SET family_id = id::text WHERE family_id IS NULL")

    op.alter_column("refresh_tokens", "family_id", nullable=False)
    op.create_index(op.f("ix_refresh_tokens_family_id"), "refresh_tokens", ["family_id"], unique=False)
    # Unnamed FK → Postgres auto-names it refresh_tokens_parent_token_id_fkey,
    # matching the model's unnamed ForeignKey (keeps `alembic check` drift-clean).
    op.create_foreign_key(
        None, "refresh_tokens", "refresh_tokens",
        ["parent_token_id"], ["id"], ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("refresh_tokens_parent_token_id_fkey", "refresh_tokens", type_="foreignkey")
    op.drop_index(op.f("ix_refresh_tokens_family_id"), table_name="refresh_tokens")
    op.drop_column("refresh_tokens", "revocation_reason")
    op.drop_column("refresh_tokens", "parent_token_id")
    op.drop_column("refresh_tokens", "family_id")
