# RUNBOOK «Байта»

## 1. Локальный запуск

```bash
cp .env.example .env          # для локального режима достаточно значений по умолчанию
make up                       # вся система в Docker, http://localhost:8080
make logs
```

Без Docker (разработка):

```bash
# PostgreSQL 16 и Redis 7 на localhost
cd api && uv sync --all-extras && uv run alembic upgrade head && uv run python -m app.seed
DEV_LOGIN=true uv run uvicorn app.main:app --reload --port 8000
cd runner && RUNNER_TOKEN=dev-runner-token RUNNER_ALLOW_UNSAFE=1 uv run python -m bayt_runner.server
cd worker && uv run arq bayt_worker.main.WorkerSettings
cd client && npm ci && npm run vendor-pyodide && npm run dev   # http://localhost:5173/?dev=1
```

`?dev=<число>` входит тестовым пользователем с этим Telegram ID — только если API запущен
с `DEV_LOGIN=true` и `BAYT_ENV` не `stage`/`prod`.

## 2. Тесты

```bash
make lint && make test            # всё, кроме раннера и e2e
make test-runner                  # nsjail нужен в системе, запуск от root
# e2e: API с DEV_LOGIN=true на :8000 и клиент с VITE_E2E=1 на :4173
cd client && VITE_E2E=1 npx vite build && npx vite preview --port 4173 &
make e2e
# нагрузка (только на своём стенде)
BASE=https://<стенд> BOT_TOKEN=<токен> VUS=200 make load
```

## 3. Стенд: первый деплой

1. **Сервер**: Ubuntu 22.04/24.04, ≥ 2 vCPU, 4 ГБ RAM, 30 ГБ; открыты 22, 80, 443.
   Для ПДн школьников — сервер в РФ (152‑ФЗ).
2. **Бот**: @BotFather → `/newbot` → имя и username. Сохранить токен.
3. **Секреты** GitHub → Settings → Secrets and variables → Actions:
   `STAGE_SSH_HOST`, `STAGE_SSH_USER`, `STAGE_SSH_KEY` (приватный ключ деплоя),
   `TELEGRAM_BOT_TOKEN`, `TELEGRAM_BOT_USERNAME`; по желанию `STAGE_DOMAIN`,
   `ADMIN_TELEGRAM_IDS`.
4. **Деплой**: push в ветку или Actions → «Deploy stage» → Run workflow. Скрипт
   `infra/deploy-stage.sh` ставит Docker, загружает код, **генерирует на сервере**
   пароли БД/Redis/S3, `JWT_SECRET`, `RUNNER_TOKEN`, `INTERNAL_TOKEN`,
   `TELEGRAM_WEBHOOK_SECRET` (`openssl rand -hex 32`) в `/opt/bayt/.env` (права 600),
   собирает образы и ждёт `https://<домен>/api/health`. Без домена используется
   `<ip>.sslip.io`, TLS выпускает Caddy.
5. **Mini App в BotFather**: `/newapp` → выбрать бота → название, описание, картинка
   640×360 → URL `https://<домен>/` → короткое имя **`app`** (оно зашито в deep‑link'и
   `t.me/<bot>/app?startapp=...`; другое имя — переменная `TELEGRAM_APP_SHORT_NAME`).
   Затем `/setmenubutton` → URL `https://<домен>/`, текст «Открыть Байт».
6. **Вебхук** бот ставит сам при старте (`BOT_MODE=webhook`), проверка —
   `curl https://api.telegram.org/bot<токен>/getWebhookInfo`.
7. **Проверка**: написать боту `/start` → «Открыть «Байт»» → онбординг → первая задача.
   Первый вошедший становится администратором, если `ADMIN_TELEGRAM_IDS` пуст.

Ручной деплой без GitHub: те же переменные в окружении и `bash infra/deploy-stage.sh`
(`STAGE_SSH_KEY_PATH` вместо `STAGE_SSH_KEY`).

## 4. Эксплуатация

| Задача | Команда (на сервере, в `/opt/bayt`) |
|---|---|
| Статус | `docker compose -f compose.yaml -f compose.stage.yaml ps` |
| Логи | `docker compose ... logs -f --tail=200 api worker bot runner` |
| Перезапуск | `docker compose ... restart api worker bot` |
| Миграции | выполняются автоматически при старте `api` |
| Бэкапы | сайдкар `backup`: ежедневно 03:30 UTC; том `backups` — 7 дней, копия в S3 (бакет `${S3_BUCKET}-backups`) — 30 дней. Список: `docker compose -f compose.yaml -f compose.stage.yaml exec backup rclone ls s3:bayt-backups`; вернуть дамп в том: `... exec backup rclone copy s3:bayt-backups/<файл> /backups/`, затем `infra/scripts/restore.sh` |
| Проверка восстановления (раз в месяц) | `bash infra/scripts/restore-check.sh` |
| Восстановление | `bash infra/scripts/restore.sh <файл.dump>` — **затирает текущие данные** |
| Смена цен/переключателей ФИПИ | админка → «Конфиг» (цены — только с новым `season_id`) |
| Бета нового генератора | `PATCH /api/admin/subtypes/<id>` `{"beta": true}` — 3 дня только в «Вызове» |
| Смоук всех генераторов | админка → «Генераторы» → «Смоук‑прогон» |

## 5. Инциденты

* **Раннер недоступен**: ответы на задачи с кодом получают `verify_status=pending`,
  воркер повторяет перепроверку каждую минуту; ученик не блокируется.
* **Telegram недоступен**: уведомления остаются `scheduled` и повторяются через 10 минут;
  заблокировавшие бота помечаются `failed` без повторов.
* **Подтверждённая ошибка генератора**: админка → «Тикеты» → «Подтвердить»
  (возврат + 20 🪙, экземпляр аннулирован) → `GET /api/admin/issues/regressions` →
  добавить seed в регресс‑тесты egegen → исправить генератор, поднять `version`.
* **Всплеск нагрузки**: `api` масштабируется числом воркеров uvicorn (`--workers`),
  раннер — `RUNNER_CONCURRENCY` и дополнительными узлами.

## 6. Ручные шаги, которые код не делает

1. BotFather: бот, Mini App (`/newapp`, короткое имя `app`), кнопка меню — раздел 3.
2. Юрист: проверить `docs/LEGAL/*` (черновики), уведомление Роскомнадзора об обработке
   ПДн, возрастная маркировка (14.4).
3. Ноябрь 2026: сверить задания 10, 13, 23 и формат ответа 27 с утверждённой
   демоверсией ФИПИ, обновить `egegen/egegen/config/fipi_2027.yaml` (`approved: true`,
   `version`, `banner_ru`) и разослать «Утверждена демоверсия» из админки.
4. Май: «финальный спринт» — 4 бесплатных полных варианта включаются автоматически
   (`free_full_exams_in_may`).
5. Ежемесячно — проверка восстановления бэкапа.
