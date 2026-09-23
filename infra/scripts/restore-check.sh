#!/usr/bin/env bash
# Monthly restore drill (12.7): restore the newest dump into a throwaway database
# and compare row counts of the key tables with production. Does not touch prod data.
set -euo pipefail
cd "$(dirname "$0")/../.."
source .env
compose="docker compose -f compose.yaml -f compose.stage.yaml"
latest=$($compose exec -T backup sh -c 'ls -1t /backups/bayt-*.dump | head -1')
echo "checking $latest"
run() { $compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres "$@"; }
run psql -U "$POSTGRES_USER" -d postgres -qc "DROP DATABASE IF EXISTS restore_check" -c "CREATE DATABASE restore_check"
$compose exec -T backup sh -c "cat '$latest'" | run pg_restore -U "$POSTGRES_USER" -d restore_check --no-owner
for table in users instances attempts transactions; do
  live=$(run psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "select count(*) from $table")
  restored=$(run psql -U "$POSTGRES_USER" -d restore_check -tAc "select count(*) from $table")
  echo "$table: live=$live restored=$restored"
done
run psql -U "$POSTGRES_USER" -d postgres -qc "DROP DATABASE restore_check"
echo "restore check done"
