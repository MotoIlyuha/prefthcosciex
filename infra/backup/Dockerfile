# Backup sidecar: pg_dump plus rclone to copy dumps to S3 (12.7).
# rclone comes from the Alpine repository: the MinIO client binary is no longer published
# at a stable download URL.
FROM postgres:16-alpine
RUN apk add --no-cache rclone && rclone version
COPY scripts/backup-loop.sh /usr/local/bin/backup-loop.sh
ENTRYPOINT ["/bin/sh", "/usr/local/bin/backup-loop.sh"]
