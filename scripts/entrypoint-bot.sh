#!/bin/sh
set -e
echo "Running schema preflight..."
python -m uk_management_bot.dbops.db_preflight
echo "Starting bot..."
exec "$@"
