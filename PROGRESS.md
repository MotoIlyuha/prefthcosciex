# PROGRESS — «Байт»

Чекпоинт для возобновления работы. Новая сессия начинает с этого файла и `git log`.

## Текущее состояние

* **Этапы 0–10 и 12 (кроме стенда)** — закрыты; **этап 11 (деплой)** ждёт сервер и токен
  бота (раздел 0, пп. а, б). Всё для деплоя готово: `infra/deploy-stage.sh`,
  `.github/workflows/deploy-stage.yml` (сам пропускает деплой, пока нет секретов).
* **Ветка:** `claude/lucid-noether-qn8zi6` — единственная, в которую у сессии есть право
  пуша; `main` не трогается (решение D‑001), теги `v0.*` стоят на коммитах этапов.
* **Дизайн‑док:** `docs/DESIGN-DOC.md` (v1.0), трекер — `docs/TASKS-TRACKER.md`.

## Секреты и окружение

| Секрет | Статус | Где задать | Последствие |
|---|---|---|---|
| `TELEGRAM_BOT_TOKEN` | **нет** | GitHub → Settings → Secrets → Actions | живой бот и initData из Telegram не проверены; подпись проверяется тестами |
| `TELEGRAM_BOT_USERNAME` | **нет** | там же | deep‑link'и собираются из переменной |
| `STAGE_SSH_HOST` / `STAGE_SSH_USER` / `STAGE_SSH_KEY` | **нет** | там же | стенд не развёрнут |
| `STAGE_DOMAIN` | нет (необязательно) | там же | будет `<ip>.sslip.io` |
| `ADMIN_TELEGRAM_IDS` | нет (необязательно) | там же | админом станет первый вошедший |
| `POSTHOG_KEY/HOST` | нет (необязательно) | `.env` на сервере | события пишутся в таблицу `events` |
| БД, Redis, S3, JWT, раннер, вебхук, internal | генерируются на сервере | `infra/deploy-stage.sh` (`openssl rand -hex`) | в git и CI не попадают |

## Чек‑лист раздела 8

| Пункт | Статус | Чем проверяется |
|---|---|---|
| 27 генераторов: ≥ 3 подтипа, ≥ 5 шаблонов, два решателя, property+golden, карточки, 200 экземпляров без ошибок | ✅ (на стенде — после деплоя) | `cd egegen && uv run pytest -q` (≈1000 тестов); `uv run egegen gen 17 --n 200`; на стенде — админка → «Смоук‑прогон» |
| 10, 13, 23, 27 из `fipi_2027.yaml`, переключение ответа 10 и входа 23 без правки кода | ✅ | `egegen/tests/test_fipi.py`; `api/tests/test_api_social.py::test_admin_dashboards_and_config` (переключение через админку) |
| Онбординг ≤ 3 мин, первые монеты в первую минуту | ✅ | `client/e2e/journey.spec.ts` (таймер), `onboarding.spec.ts` |
| Дейлики 3+2, порог 30, кэп 120, серия/заморозки/отпуск/лёгкий день, XP, график монет | ✅ | `api/tests/test_api_daily.py`, `test_api_progression.py::test_vacation_and_easy_day`, `test_logic_streak.py`; экран «Прогресс» |
| Экономика: симуляция 5.4, защитные клапаны | ✅ | `api/tests/test_logic_economy.py` (`economy_sim.py`), тесты бесплатного разбора дня, экстерна, возврата по тикету |
| 13 этажей, боссы, монеты и экстерн, магазин 5.3, тикеты с возвратом | ✅ | `test_api_progression.py` (этажи, экстерн, босс, магазин), `test_api_social.py::test_confirmed_ticket_refunds_and_compensates`; e2e `journey.spec.ts` |
| Адаптивность: стартовый тест, Эло/mastery/забывание, уверенность v2, прогноз, 8 причин влияют на подбор | ✅ | `test_logic_skills.py`, `test_logic_planner.py` (после «не понял условие» сложность ниже), `test_api_progression.py::test_placement_eight_steps_open_floors` |
| Код: Pyodide (вендорен), редактор, перепроверка на скрытом варианте, метод‑чек, античит (ответ без кода на 17/24/26/27 не проходит) | ✅ | `test_api_daily.py::test_correct_answer_without_code_is_not_verified[17,24,26,27]`, `test_every_code_task_reference_passes_its_own_recheck`; e2e `task.spec.ts` (Python в браузере) |
| Экзамен трёх форматов, КЕГЭ, 1 бесплатный в месяц, влияет на уверенность | ✅ | `test_api_progression.py` (half, full free, training block); e2e `exam.spec.ts` |
| Куратор: приглашение, 3 уровня, дашборд, пинок, фокус, отчёт, отзыв | ✅ | `test_api_social.py` (кураторские тесты); e2e `curator.spec.ts` |
| Уведомления: все события раздела 10, ≤ 2/день, тихие часы, пояса, отписка | ✅ | `test_logic_misc.py`, `test_api_social.py` (лимит, тихие часы), `test_scheduler.py` (пояса, доставка, отмена) |
| Все экраны раздела 11, веб‑версия, тёмная тема, 360 px без горизонтального скролла | ✅ (живой Telegram — после токена) | e2e `layout.spec.ts`; веб‑вход — `test_api_auth.py` |
| Безопасность: HMAC, JWT, роли, rate‑limit, CSP, раннер без сети, аудит зависимостей, удаление и экспорт | ✅ | `test_api_auth.py` (подделка, истёкший `auth_date`, ротация), `runner/tests` (сеть, ФС, процессы, окружение — в nsjail), CI `pip-audit` и `npm audit`, `test_export_and_deletion` |
| Аналитика: события 15.3, админка с дашбордами 5.4 и переключателями | ✅ | `test_admin_dashboards_and_config`, `test_client_events_are_whitelisted` |
| Стенд: HTTPS, бот и Mini App, CI/CD по пушу, бэкап/восстановление, нагрузка 500 пользователей p95 < 200 мс | ⛔ ждёт секретов | готово: `deploy-stage.yml`, `backup` + `restore-check.sh`, `load/k6-dailies.js` (локально: 25 пользователей, p95 17 мс, 0 % ошибок) |
| Документация | ✅ | `README.md`, `docs/ARCHITECTURE.md`, `API.md` (из OpenAPI), `METHODIST.md`, `RUNBOOK.md`, `DECISIONS.md` (D‑001…D‑039), `KNOWN_GAPS.md`, `LEGAL/` |

## Команды

```bash
make install && make lint && make test     # всё, кроме раннера и e2e
make test-runner                           # sandbox (nsjail, root)
make up                                    # вся система в Docker, http://localhost:8080
# e2e — RUNBOOK, раздел 2; нагрузка — BASE=... BOT_TOKEN=... make load
# деплой — секреты в GitHub, затем push или Actions → «Deploy stage»
```

## Известные проблемы

`docs/KNOWN_GAPS.md` и `docs/DECISIONS.md`.
