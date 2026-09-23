FROM python:3.12-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /srv/bot
COPY bot/pyproject.toml bot/uv.lock ./
COPY bot/bayt_bot ./bayt_bot
RUN uv sync --frozen --no-dev
ENV PATH="/srv/bot/.venv/bin:$PATH"
USER nobody
EXPOSE 8090
CMD ["python", "-m", "bayt_bot.main"]
