# PROGRESS — «Байт»

Чекпоинт для возобновления работы. Новая сессия начинает с этого файла и `git log`.

## Текущее состояние

* **Этап:** 2–9 (генераторы) закрыты полностью; идёт этап 1/4 — API, данные, авторизация.
* **Ветка:** `claude/lucid-noether-qn8zi6` (единственная, на которую у сессии есть право пуша).
* **Дизайн‑док:** `docs/DESIGN-DOC.md` (v1.0), трекер задач — `docs/TASKS-TRACKER.md`.

## Секреты и окружение (проверено 2026‑09‑21)

| Переменная | Статус | Последствие |
|---|---|---|
| `GITHUB_REPO` | нет | используется существующий репозиторий `MotoIlyuha/prefthcosciex` |
| `GH_TOKEN` | есть | — |
| `TELEGRAM_BOT_TOKEN` | **нет** | бот и проверка initData на живом Telegram невозможны; код и тесты есть (подпись проверяется на тестовом токене) |
| `TELEGRAM_BOT_USERNAME` | **нет** | deep‑link'и собираются из переменной, заполнить при деплое |
| `STAGE_SSH_HOST/USER/KEY_PATH` | **нет** | деплой на стейдж физически невозможен (раздел 0 б) |
| `STAGE_DOMAIN` | нет | при деплое — `<ip>.sslip.io` |
| `POSTHOG_KEY/HOST` | нет | события пишутся в таблицу `events` |
| `S3_*` | нет | MinIO из compose |
| `ADMIN_TELEGRAM_IDS` | нет | первый авторизовавшийся — админ |

Инструменты: Docker (демон поднят вручную), Node 22, Python 3.12 через `uv`. `gh`, `ssh`, `rsync` в контейнере **отсутствуют**.

## Чек‑лист раздела 8

| Пункт | Статус | Как проверить |
|---|---|---|
| 27 генераторов: ≥3 подтипа, ≥5 шаблонов, два решателя, property+golden, карточки | ✅ | `cd egegen && uv run pytest -q` (987 тестов); `uv run egegen property-check` |
| 10/13/23/27 из `fipi_2027.yaml`, переключение без правки кода | ✅ | `uv run pytest tests/test_fipi.py` |
| Остальные пункты | ⏳ | — |

## Команды

```bash
cd egegen && uv sync --all-extras
uv run egegen list                       # все генераторы и подтипы
uv run egegen show 19 --seed 129         # один экземпляр с разбором
uv run egegen gen 17 --seed 42 --n 200   # 200 экземпляров с проверками
uv run egegen selfcheck                  # golden‑значения из дока
uv run pytest -q                         # полный набор тестов
uv run ruff check . && uv run mypy --strict egegen
```

## Известные проблемы

См. `docs/KNOWN_GAPS.md` и `docs/DECISIONS.md`.
