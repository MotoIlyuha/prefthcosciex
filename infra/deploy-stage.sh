#!/usr/bin/env bash
# Deploy the stage stand over SSH (build prompt, stage 12).
#
# Needs (environment variables, from GitHub Actions secrets or your shell):
#   STAGE_SSH_HOST, STAGE_SSH_USER, and STAGE_SSH_KEY (key text) or STAGE_SSH_KEY_PATH
#   TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME
#   optional: STAGE_DOMAIN (default <ip>.sslip.io), ADMIN_TELEGRAM_IDS
#
# Every other secret (DB, Redis, S3, JWT, runner, webhook, internal token) is
# generated ON THE SERVER with openssl the first time and never leaves it.
set -euo pipefail

: "${STAGE_SSH_HOST:?STAGE_SSH_HOST is required}"
: "${STAGE_SSH_USER:=root}"
: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required}"
: "${TELEGRAM_BOT_USERNAME:?TELEGRAM_BOT_USERNAME is required}"
ADMIN_TELEGRAM_IDS="${ADMIN_TELEGRAM_IDS:-}"
REMOTE_DIR="${STAGE_REMOTE_DIR:-/opt/bayt}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

key_file="${STAGE_SSH_KEY_PATH:-}"
cleanup() { [[ -n "${tmp_key:-}" ]] && rm -f "$tmp_key"; }
trap cleanup EXIT
if [[ -z "$key_file" ]]; then
  : "${STAGE_SSH_KEY:?STAGE_SSH_KEY or STAGE_SSH_KEY_PATH is required}"
  tmp_key="$(mktemp)"
  printf '%s\n' "$STAGE_SSH_KEY" > "$tmp_key"
  chmod 600 "$tmp_key"
  key_file="$tmp_key"
fi
ssh_opts=(-i "$key_file" -o StrictHostKeyChecking=accept-new -o ServerAliveInterval=30)
target="${STAGE_SSH_USER}@${STAGE_SSH_HOST}"
sudo_cmd=""
[[ "$STAGE_SSH_USER" != "root" ]] && sudo_cmd="sudo"

domain="${STAGE_DOMAIN:-}"
if [[ -z "$domain" ]]; then
  ip="$(ssh "${ssh_opts[@]}" "$target" "curl -fsS4 https://api.ipify.org || hostname -I | awk '{print \$1}'")"
  domain="${ip}.sslip.io"
fi
echo "==> deploying to $target, https://$domain"

echo "==> preparing the server (docker, directory)"
ssh "${ssh_opts[@]}" "$target" "set -e
  if ! command -v docker >/dev/null; then curl -fsSL https://get.docker.com | $sudo_cmd sh; fi
  $sudo_cmd mkdir -p '$REMOTE_DIR' && $sudo_cmd chown \"\$(id -u):\$(id -g)\" '$REMOTE_DIR'"

echo "==> uploading the code"
tar -C "$ROOT" \
  --exclude=.git --exclude='*/node_modules' --exclude='*/.venv' --exclude='*/__pycache__' \
  --exclude='client/dist' --exclude='client/public/pyodide/*' --exclude='.env' \
  -czf - . | ssh "${ssh_opts[@]}" "$target" "tar -C '$REMOTE_DIR' -xzf -"

echo "==> writing .env on the server (secrets generated there)"
ssh "${ssh_opts[@]}" "$target" \
  "BOT_TOKEN=$(printf '%q' "$TELEGRAM_BOT_TOKEN") BOT_USERNAME=$(printf '%q' "$TELEGRAM_BOT_USERNAME") \
   ADMINS=$(printf '%q' "$ADMIN_TELEGRAM_IDS") DOMAIN=$(printf '%q' "$domain") DIR=$(printf '%q' "$REMOTE_DIR") bash -s" <<'REMOTE'
set -euo pipefail
cd "$DIR"
env_file=.env
gen() { openssl rand -hex "$1"; }
if [[ ! -f $env_file ]]; then
  pg=$(gen 24); rd=$(gen 24); s3=$(gen 24)
  cat > $env_file <<ENV
BAYT_ENV=stage
PUBLIC_BASE_URL=https://__DOMAIN__
JWT_SECRET=$(gen 32)
JWT_ACCESS_TTL_MIN=15
JWT_REFRESH_TTL_DAYS=30
DEV_LOGIN=false
POSTGRES_USER=bayt
POSTGRES_PASSWORD=$pg
POSTGRES_DB=bayt
DATABASE_URL=postgresql+asyncpg://bayt:$pg@postgres:5432/bayt
REDIS_PASSWORD=$rd
REDIS_URL=redis://:$rd@redis:6379/0
TELEGRAM_BOT_TOKEN=__BOT_TOKEN__
TELEGRAM_BOT_USERNAME=__BOT_USERNAME__
TELEGRAM_APP_SHORT_NAME=app
TELEGRAM_WEBHOOK_SECRET=$(gen 32)
TELEGRAM_INITDATA_MAX_AGE=600
BOT_MODE=webhook
BOT_API_URL=http://api:8000/api
INTERNAL_TOKEN=$(gen 32)
RUNNER_URL=http://runner:8081
RUNNER_TOKEN=$(gen 32)
S3_ENDPOINT=http://s3:8333
S3_BUCKET=bayt
S3_ACCESS_KEY=bayt
S3_SECRET_KEY=$s3
S3_REGION=us-east-1
ADMIN_TELEGRAM_IDS=__ADMINS__
STAGE_SITE_ADDRESS=__DOMAIN__
ENV
  chmod 600 $env_file
fi
# Values that come from GitHub secrets are refreshed on every deploy.
set_var() { if grep -q "^$1=" $env_file; then sed -i "s|^$1=.*|$1=$2|" $env_file; else echo "$1=$2" >> $env_file; fi; }
set_var TELEGRAM_BOT_TOKEN "$BOT_TOKEN"
set_var TELEGRAM_BOT_USERNAME "$BOT_USERNAME"
set_var ADMIN_TELEGRAM_IDS "$ADMINS"
set_var PUBLIC_BASE_URL "https://$DOMAIN"
set_var STAGE_SITE_ADDRESS "$DOMAIN"
set_var S3_ENDPOINT "http://s3:8333"
REMOTE

echo "==> building and starting"
ssh "${ssh_opts[@]}" "$target" "cd '$REMOTE_DIR' && $sudo_cmd docker compose -f compose.yaml -f compose.stage.yaml up -d --build --remove-orphans"

echo "==> waiting for https://$domain/api/health"
for i in $(seq 1 60); do
  if curl -fsS "https://$domain/api/health" >/dev/null 2>&1; then
    curl -fsS "https://$domain/api/health"; echo
    echo "==> stage is up: https://$domain  (bot: https://t.me/$TELEGRAM_BOT_USERNAME)"
    exit 0
  fi
  sleep 10
done
echo "stage did not become healthy; see: docker compose logs api caddy" >&2
exit 1
