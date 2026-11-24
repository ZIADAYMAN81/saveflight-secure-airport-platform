#!/bin/bash
# Restore an encrypted backup produced by backup-postgres.sh
#   ./restore-postgres.sh /var/backups/postgres/airport_db_20260101_020000.sql.gz.enc
set -euo pipefail

ENCRYPTED_FILE="${1:?Usage: restore-postgres.sh <backup-file.sql.gz.enc>}"
CONTAINER_NAME="${CONTAINER_NAME:-airport_postgres}"
DB_USER="${DB_USER:?DB_USER must be set}"
DB_NAME="${DB_NAME:?DB_NAME must be set}"
BACKUP_PASSWORD="${BACKUP_PASSWORD:?BACKUP_PASSWORD must be set}"

openssl enc -aes-256-cbc -pbkdf2 -d -in "$ENCRYPTED_FILE" -k "$BACKUP_PASSWORD" | \
  gunzip | docker exec -i "$CONTAINER_NAME" psql -U "$DB_USER" "$DB_NAME"

echo "Restore complete from $ENCRYPTED_FILE"
