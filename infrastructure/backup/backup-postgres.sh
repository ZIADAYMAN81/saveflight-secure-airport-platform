#!/bin/bash
# Daily encrypted PostgreSQL backup. Intended to run via cron/systemd-timer on
# the Docker host (or inside a scheduled sidecar container):
#   0 2 * * * /opt/airport-system/infrastructure/backup/backup-postgres.sh
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-/var/backups/postgres}"
CONTAINER_NAME="${CONTAINER_NAME:-airport_postgres}"
DB_USER="${DB_USER:?DB_USER must be set}"
DB_NAME="${DB_NAME:?DB_NAME must be set}"
BACKUP_PASSWORD="${BACKUP_PASSWORD:?BACKUP_PASSWORD must be set}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
PLAIN_FILE="$BACKUP_DIR/airport_db_${TIMESTAMP}.sql.gz"
ENCRYPTED_FILE="${PLAIN_FILE}.enc"

docker exec "$CONTAINER_NAME" pg_dump -U "$DB_USER" "$DB_NAME" | gzip > "$PLAIN_FILE"

# Encrypt at rest; the plaintext dump never touches disk unencrypted for long.
openssl enc -aes-256-cbc -pbkdf2 -salt -in "$PLAIN_FILE" -out "$ENCRYPTED_FILE" -k "$BACKUP_PASSWORD"
rm -f "$PLAIN_FILE"

find "$BACKUP_DIR" -name "*.enc" -mtime +"$RETENTION_DAYS" -delete

echo "Backup complete: $ENCRYPTED_FILE"
