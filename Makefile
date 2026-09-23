.DEFAULT_GOAL := help
SHELL := /bin/bash
COMPOSE := docker compose -f compose.yaml

.PHONY: help
help: ## Show this help
	@grep -hE '^[a-zA-Z0-9_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

.PHONY: up
up: ## Start the whole stack locally (postgres, redis, minio, api, bot, worker, runner, client, caddy)
	@test -f .env || cp .env.example .env
	$(COMPOSE) up -d --build
	@echo "Client: http://localhost:8080  API: http://localhost:8080/api/health"

.PHONY: down
down: ## Stop the stack
	$(COMPOSE) down

.PHONY: clean
clean: ## Stop the stack and delete volumes (DESTROYS local data)
	$(COMPOSE) down -v

.PHONY: logs
logs: ## Tail logs of all services
	$(COMPOSE) logs -f --tail=100

.PHONY: migrate
migrate: ## Apply DB migrations inside the api container
	$(COMPOSE) exec -T api alembic upgrade head

.PHONY: seed
seed: ## Load floors, prices, method cards into the DB
	$(COMPOSE) exec -T api python -m app.seed

.PHONY: install
install: ## Install all dev dependencies locally (uv + npm)
	cd egegen && uv sync --all-extras
	cd api && uv sync --all-extras
	cd runner && uv sync --all-extras
	cd worker && uv sync --all-extras
	cd bot && uv sync --all-extras
	cd client && npm ci

.PHONY: lint
lint: ## Run every linter (ruff, mypy --strict, eslint, tsc)
	cd egegen && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict egegen
	cd api && uv run ruff check . && uv run ruff format --check . && uv run mypy --strict app
	cd runner && uv run ruff check . && uv run mypy --strict bayt_runner
	cd worker && uv run ruff check . && uv run mypy --strict bayt_worker
	cd bot && uv run ruff check . && uv run mypy --strict bayt_bot
	cd client && npm run lint && npm run typecheck

.PHONY: fmt
fmt: ## Auto-format everything
	cd egegen && uv run ruff format . && uv run ruff check --fix .
	cd api && uv run ruff format . && uv run ruff check --fix .
	cd runner && uv run ruff format . && uv run ruff check --fix .
	cd worker && uv run ruff format . && uv run ruff check --fix .
	cd bot && uv run ruff format . && uv run ruff check --fix .

.PHONY: test
test: test-egegen test-api test-services test-client ## Run all test suites (runner: make test-runner)

.PHONY: test-egegen
test-egegen: ## Property + golden tests for all 27 generators
	cd egegen && uv run pytest -q

.PHONY: test-api
test-api: ## API tests (needs postgres+redis: make up first, or CI services)
	cd api && uv run pytest -q

.PHONY: test-client
test-client: ## Vitest unit tests for stores and logic
	cd client && npm test

.PHONY: e2e
e2e: ## Playwright e2e: needs API with DEV_LOGIN=true on :8000 and `VITE_E2E=1 vite preview` on :4173
	cd client && npx playwright test

.PHONY: load
load: ## k6 load test of the core loop: BASE=https://stand BOT_TOKEN=... VUS=500 make load
	k6 run load/k6-dailies.js

.PHONY: vendor-pyodide
vendor-pyodide: ## Copy Pyodide from node_modules into client/public/pyodide (no CDN at runtime)
	cd client && node scripts/vendor-pyodide.mjs

.PHONY: deploy-stage
deploy-stage: ## Deploy to the stage VPS over SSH
	bash infra/deploy-stage.sh

.PHONY: test-runner
test-runner: ## Sandbox tests (nsjail must be installed; run as root like the container)
	cd runner && sudo -E .venv/bin/python -m pytest -q

.PHONY: test-services
test-services: ## Worker and bot tests
	cd worker && uv run pytest -q
	cd bot && uv run pytest -q

.PHONY: restore-check
restore-check: ## Monthly restore drill on the stand (does not touch live data)
	bash infra/scripts/restore-check.sh
