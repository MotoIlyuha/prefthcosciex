# Worker image: the API code base plus the ARQ entry point. Build from the repo root.
FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /srv
COPY egegen ./egegen
COPY api ./api
COPY worker ./worker
RUN cd worker && uv sync --frozen --no-dev
WORKDIR /srv/api
ENV PATH="/srv/worker/.venv/bin:$PATH"
USER nobody
CMD ["arq", "bayt_worker.main.WorkerSettings"]
