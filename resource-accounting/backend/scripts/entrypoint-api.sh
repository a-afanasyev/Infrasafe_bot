#!/bin/sh
set -e

if [ "$1" = "uvicorn" ]; then
  echo "Applying migrations..."
  alembic upgrade head
  python -m app.seed
fi

exec "$@"
