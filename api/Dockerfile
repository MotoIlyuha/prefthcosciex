# API image. Build from the repository root: it needs ../egegen.
FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir uv==0.8.17
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /srv
COPY egegen ./egegen
COPY api ./api
RUN cd api && uv sync --frozen --no-dev
WORKDIR /srv/api
ENV PATH="/srv/api/.venv/bin:$PATH"
USER nobody
EXPOSE 8000
# Migrations and the idempotent seed run on every start, then the server.
CMD ["sh", "-c", "alembic upgrade head && python -m app.seed && exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*' --workers 2"]
