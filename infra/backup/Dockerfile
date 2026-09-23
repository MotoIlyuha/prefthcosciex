# Backup sidecar: pg_dump plus the MinIO client to copy dumps to S3 (12.7).
FROM postgres:16-alpine
# Pin a release with --build-arg MC_URL=.../archive/mc.RELEASE.<date> when needed.
ARG MC_URL=https://dl.min.io/client/mc/release/linux-amd64/mc
RUN wget -q -O /usr/local/bin/mc "${MC_URL}" \
    && chmod +x /usr/local/bin/mc && mc --version
COPY scripts/backup-loop.sh /usr/local/bin/backup-loop.sh
ENTRYPOINT ["/bin/sh", "/usr/local/bin/backup-loop.sh"]
