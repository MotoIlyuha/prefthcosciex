#!/usr/bin/env bash
# Restore a dump into the running stack's database. DESTROYS current data.
# Usage: infra/scripts/restore.sh /var/lib/docker/volumes/bayt_backups/_data/bayt-XXXX.dump
set -euo pipefail
dump="${1:?path to .dump}"
cd "$(dirname "$0")/../.."
source .env
compose="docker compose -f compose.yaml -f compose.stage.yaml"
$compose stop api worker bot
$compose exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" postgres \
  pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner < "$dump"
$compose start api worker bot
echo "restored from $dump"
