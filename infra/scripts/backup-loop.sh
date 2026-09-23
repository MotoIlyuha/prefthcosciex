#!/bin/sh
# Nightly PostgreSQL dump (design doc 12.7): copied to S3 (bucket
# ${S3_BUCKET}-backups, 30 days) and kept locally for 7 days; restore is checked monthly
# with infra/scripts/restore-check.sh. Runs in the `backup` sidecar of compose.stage.yaml.
set -eu
: "${POSTGRES_USER:?}" "${POSTGRES_PASSWORD:?}" "${POSTGRES_DB:?}"
export PGPASSWORD="$POSTGRES_PASSWORD"
KEEP_DAYS="${BACKUP_KEEP_DAYS:-30}"
LOCAL_DAYS="${BACKUP_LOCAL_DAYS:-7}"
BUCKET="${S3_BUCKET:-bayt}-backups"
mkdir -p /backups
# The rclone remote "s3" comes from RCLONE_CONFIG_S3_* (compose.stage.yaml).
if [ -n "${RCLONE_CONFIG_S3_ENDPOINT:-}" ] && command -v rclone >/dev/null; then
  rclone -q mkdir "s3:$BUCKET"
  remote=1
else
  remote=0
fi
while true; do
  stamp="$(date -u +%Y%m%dT%H%M%SZ)"
  file="/backups/bayt-${stamp}.dump"
  if pg_dump -h postgres -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f "${file}.part"; then
    mv "${file}.part" "$file"
    echo "backup ok: $file ($(du -h "$file" | cut -f1))"
    if [ "$remote" = 1 ]; then
      rclone copyto "$file" "s3:$BUCKET/$(basename "$file")" && echo "copied to s3:$BUCKET"
      rclone -q delete --min-age "${KEEP_DAYS}d" "s3:$BUCKET" || true
    fi
  else
    rm -f "${file}.part"
    echo "backup FAILED at $stamp" >&2
  fi
  find /backups -name 'bayt-*.dump' -mtime +"$LOCAL_DAYS" -delete
  # Next run at 03:30 UTC.
  now=$(date -u +%s)
  next=$(date -u -d "$(date -u +%Y-%m-%d) 03:30" +%s 2>/dev/null || echo $((now + 86400)))
  [ "$next" -le "$now" ] && next=$((next + 86400))
  sleep $((next - now))
done
