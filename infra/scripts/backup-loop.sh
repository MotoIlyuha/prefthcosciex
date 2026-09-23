#!/bin/sh
# Nightly PostgreSQL dump (design doc 12.7): kept 30 days, restore checked monthly
# with infra/scripts/restore-check.sh. Runs in the `backup` sidecar of compose.stage.yaml.
set -eu
: "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}" "${POSTGRES_DB:?}"
export PGPASSWORD="$POSTGRES_PASSWORD"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
mkdir -p /backups
while true; do
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  file="/backups/bayt-${stamp}.dump"
  if pg_dump -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "${file}.part"; then
    mv "${file}.part" "$file"
    echo "backup ok: $file ($(du -h "$file" | cut -f1))"
  else
    rm -f "${file}.part"
    echo "backup FAILED at $stamp" >&2
  fi
  find /backups -name 'bayt-*.dump' -mtime +"$KEEP_DAYS" -delete
  # Next run at 03:30 UTC.
  now=$(date -u +%s)
  next=$(date -u -d "$(date -u +%Y-%m-%d) 03:30" +%s 2>/dev/null || echo $((now + 86400)))
  [ "$next" -le "$now" ] && next=$((next + 86400))
  sleep $((next - now))
done
