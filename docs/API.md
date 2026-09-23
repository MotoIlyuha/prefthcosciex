# API «Байта»

Сгенерировано из OpenAPI (`api/scripts/export_openapi.py`); полная схема —
[`docs/openapi.json`](openapi.json), интерактивно — `/api/docs` на стенде.

Общие правила:

* Авторизация — `Authorization: Bearer <access>`; access живёт 15 минут,
  refresh — 30 дней с ротацией (`POST /api/auth/refresh`).
* Все мутации принимают `Idempotency-Key`: повтор с тем же ключом
  возвращает первый ответ.
* Ошибки: `{"detail": {"code": "…", "message": "текст для ученика", …}}`.
* Эталонный ответ, `hidden_seed` и решение никогда не приходят в ответах, кроме разбора
  (`/reveal`) после закрытия задачи.
* Лимиты: 60 ответов в минуту, 20 серверных запусков кода в час, 240 запросов в минуту.

## Служебное

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/config/public` | What the web version needs before sign-in: the bot for the login redirect. |
| `GET` | `/api/health` | Health |

## Вход

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/auth/logout` | Logout |
| `POST` | `/api/auth/refresh` | Refresh |
| `POST` | `/api/auth/telegram` | Mini App sign-in with ``initData``: HMAC-checked, at most 10 minutes old. |
| `POST` | `/api/auth/web-link` | Exchange the bot's one-time link for a session in the web version. |
| `POST` | `/api/auth/widget` | Web version sign-in with the Telegram Login Widget. |

## Ученик: профиль, «Сегодня», прогресс, магазин

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/confidence` | Confidence |
| `GET` | `/api/confidence/{task_no}` | Confidence Task |
| `POST` | `/api/events` | Client-side analytics (15.3): only the whitelisted events, no personal data. |
| `DELETE` | `/api/me` | Full deletion in 7 days; signing in before that cancels it (14.3). |
| `GET` | `/api/me` | Me |
| `POST` | `/api/me/easy-day` | One «лёгкий день» a week: the threshold drops to 10 (4.3). |
| `GET` | `/api/me/export` | All personal data as JSON (12.7, 14.3). |
| `PATCH` | `/api/me/onboarding` | Update Onboarding |
| `PATCH` | `/api/me/settings` | Update Settings |
| `POST` | `/api/me/vacation` | Up to 7 days a month, booked at least a day ahead; the streak is frozen (4.3). |
| `POST` | `/api/notifications/{notification_id}/opened` | Notification Opened |
| `POST` | `/api/onboarding/first-task` | First Task |
| `POST` | `/api/placement/start` | «Я уже готовился — проверь меня» (6.5): eight adaptive tasks. |
| `GET` | `/api/progress` | Progress View |
| `GET` | `/api/reports` | My Reports |
| `POST` | `/api/reports/issue` | Report Issue |
| `GET` | `/api/shop` | Shop Catalogue |
| `POST` | `/api/shop/buy` | Shop Buy |
| `GET` | `/api/theory/card/{card_id}` | Theory Card |
| `GET` | `/api/theory/{task_no}` | Method cards: free, always, whatever the balance (5.5). |
| `GET` | `/api/today` | Today |
| `GET` | `/api/wallet` | Wallet |
| `GET` | `/api/wallet/tx` | Wallet Tx |

## Задачи и «Путь»

| Метод | Путь | Назначение |
|---|---|---|
| `POST` | `/api/instances/similar` | A fresh instance of the same kind — free and unlimited (5.5). |
| `GET` | `/api/instances/{instance_id}` | Get Instance |
| `POST` | `/api/instances/{instance_id}/answer` | The only place where right and wrong are revealed; the answer itself never is. |
| `GET` | `/api/instances/{instance_id}/assets/{name}` | Task files (``17.txt``, ``9.ods``…); regenerated from the seed if missing. |
| `PATCH` | `/api/instances/{instance_id}/draft` | Draft |
| `POST` | `/api/instances/{instance_id}/feedback` | «Что было сложным?» (6.4). |
| `POST` | `/api/instances/{instance_id}/hint` | Hint |
| `POST` | `/api/instances/{instance_id}/ran` | The browser (Pyodide) ran the program: it counts as "ran at least once" (7.5.2). |
| `POST` | `/api/instances/{instance_id}/reveal` | Reveal |
| `POST` | `/api/instances/{instance_id}/run` | Run the student's program on the server runner (nsjail, no network, 10 s). |
| `GET` | `/api/path` | Path |
| `GET` | `/api/path/python` | «Python‑минимум» progress (Appendix C). |
| `GET` | `/api/path/trials/{trial_id}` | Trial |
| `POST` | `/api/path/{floor}/boss` | Boss |
| `POST` | `/api/path/{floor}/extern` | Three tasks at difficulty 4, all three right opens the floor for free (5.5). |
| `POST` | `/api/path/{floor}/unlock` | Unlock |

## Экзамен

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/exams` | List Exams |
| `POST` | `/api/exams` | Start |
| `GET` | `/api/exams/{exam_id}` | Get Exam |
| `POST` | `/api/exams/{exam_id}/answers` | KEGE-style «Сохранить»: stored without feedback until the finish. |
| `POST` | `/api/exams/{exam_id}/finish` | Finish |
| `POST` | `/api/exams/{exam_id}/pause` | Pause |
| `POST` | `/api/exams/{exam_id}/resume` | Resume |

## Кураторы

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/curator/students` | Students |
| `GET` | `/api/curator/students/{student_id}` | Student |
| `POST` | `/api/curator/students/{student_id}/focus` | Focus |
| `PATCH` | `/api/curator/students/{student_id}/link` | Link Settings |
| `POST` | `/api/curator/students/{student_id}/nudge` | Nudge |
| `GET` | `/api/curator/students/{student_id}/report` | Weekly report as a printable HTML page (9.3). |
| `GET` | `/api/curators` | My Curators |
| `POST` | `/api/curators/accept` | Accept |
| `POST` | `/api/curators/invite` | A ``t.me/<bot>?start=cur_<token>`` link living 48 hours (9.1). |
| `DELETE` | `/api/curators/{link_id}` | Revoke |
| `PATCH` | `/api/curators/{link_id}/access` | Access |
| `GET` | `/api/curators/{link_id}/preview` | «Так вас видит куратор» (14.3). |
| `GET` | `/api/league` | League |

## Админка

| Метод | Путь | Назначение |
|---|---|---|
| `GET` | `/api/admin/anomalies` | Anomalies |
| `GET` | `/api/admin/audit` | Audit |
| `POST` | `/api/admin/broadcast/demo` | Broadcast Demo |
| `GET` | `/api/admin/config` | Config |
| `PUT` | `/api/admin/config/{section}` | Prices, floors, FIPI toggles for 10/13/23/27 — validated, applied without a deploy. |
| `GET` | `/api/admin/economy` | Economy Health |
| `GET` | `/api/admin/feedback/other` | Other Reasons |
| `GET` | `/api/admin/funnel` | Funnel |
| `GET` | `/api/admin/generators` | Generators |
| `POST` | `/api/admin/generators/smoke` | Smoke |
| `GET` | `/api/admin/issues` | Issues |
| `GET` | `/api/admin/issues/regressions` | Regressions |
| `POST` | `/api/admin/issues/{issue_id}/resolve` | Resolve |
| `POST` | `/api/admin/notify/test` | Notify Test |
| `POST` | `/api/admin/runner/smoke` | Runner Smoke |
| `PATCH` | `/api/admin/subtypes/{subtype_id}` | Subtype Beta |
| `GET` | `/api/admin/users` | Users |
| `POST` | `/api/admin/users/{user_id}/coins` | Grant |
