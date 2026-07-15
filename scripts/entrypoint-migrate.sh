#!/bin/sh
set -e
echo "Running database migrations..."
python -m alembic upgrade head
echo "Running ACL-reconciliation helper..."
python -m uk_management_bot.dbops.acl_reconcile
echo "Verifying schema..."
python -m alembic check
echo "Migrations complete."
