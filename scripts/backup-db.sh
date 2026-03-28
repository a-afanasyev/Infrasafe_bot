#!/bin/bash
# Daily PostgreSQL backup script
# Add to cron: 0 3 * * * /path/to/backup-db.sh
set -euo pipefail

BACKUP_DIR="/opt/uk-management/backups"
CONTAINER="uk-postgres"
DB_NAME="${POSTGRES_DB:-uk_management}"
DB_USER="${POSTGRES_USER:-uk_bot}"
KEEP_DAYS=14

mkdir -p "$BACKUP_DIR"

FILENAME="uk_management_$(date +%Y%m%d_%H%M%S).sql.gz"

docker exec "$CONTAINER" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$BACKUP_DIR/$FILENAME"

# Remove backups older than KEEP_DAYS
find "$BACKUP_DIR" -name "uk_management_*.sql.gz" -mtime +$KEEP_DAYS -delete

echo "Backup created: $BACKUP_DIR/$FILENAME ($(du -h "$BACKUP_DIR/$FILENAME" | cut -f1))"
