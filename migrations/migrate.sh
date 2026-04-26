#!/usr/bin/env bash
# Run all pending SQL migrations in order.
# Usage: ./migrations/migrate.sh
# Requires: DB_HOST, DB_PORT, DB_NAME, DB_USER, DB_PASSWORD set in environment
#           or config/.env loaded beforehand.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
DB_URL="postgresql://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

echo "Bootstrapping schema_migrations table..."
psql "$DB_URL" -f "$SCRIPT_DIR/000_schema_version.sql"

for migration in "$SCRIPT_DIR"/[0-9][0-9][0-9]_*.sql; do
    version=$(basename "$migration" | grep -o '^[0-9]*')
    already_applied=$(psql "$DB_URL" -tAc \
        "SELECT COUNT(*) FROM schema_migrations WHERE version = $version")
    if [ "$already_applied" -eq 0 ]; then
        echo "Applying migration $version: $(basename "$migration")..."
        psql "$DB_URL" -f "$migration"
    else
        echo "Skipping migration $version (already applied)."
    fi
done

echo "All migrations applied."
