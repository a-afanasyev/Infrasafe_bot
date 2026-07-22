"""ARCH-010: entity version counters for deterministic outbox event_id.

- requests.status_version: bumped only on an actual DB-status change
  (workflow_runner compares status before/after the patch loop).
- buildings.building_version: bumped only when update_building/delete_building
  actually changes something (change-gate / no-op guard in addresses/core.py).

Both feed the UUIDv5 name of versioned webhook events
(building.updated / building.deleted / request.status_changed) — see
docs/superpowers/specs/2026-07-22-arch-010-deterministic-event-id-coordination.md §3.

Two-step (add nullable → backfill 0 → NOT NULL + server_default "0") so it never
fails on existing rows; server_default matches the model definition exactly to
keep `alembic check` drift-clean. Reversible downgrade (drops both columns).

WARNING: downgrade is safe ONLY before the deterministic-id cutover ships
events to InfraSafe. After cutover, drop+re-add resets versions to 0 → future
events re-mint historically used UUIDv5 ids, and InfraSafe's indefinite dedup
swallows them permanently.

Revision ID: 004
Revises: 003
Create Date: 2026-07-23
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "004"
down_revision: Union[str, None] = "003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("requests", sa.Column("status_version", sa.Integer(), nullable=True))
    op.add_column("buildings", sa.Column("building_version", sa.Integer(), nullable=True))

    op.execute("UPDATE requests SET status_version = 0 WHERE status_version IS NULL")
    op.execute("UPDATE buildings SET building_version = 0 WHERE building_version IS NULL")

    op.alter_column("requests", "status_version", nullable=False, server_default="0")
    op.alter_column("buildings", "building_version", nullable=False, server_default="0")


def downgrade() -> None:
    op.drop_column("buildings", "building_version")
    op.drop_column("requests", "status_version")
