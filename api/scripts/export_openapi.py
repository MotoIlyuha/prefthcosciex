"""Write docs/openapi.json and docs/API.md from the application's OpenAPI schema.

Run from api/: ``uv run python scripts/export_openapi.py``. CI does not need it; the
docs are regenerated whenever the API changes.
"""

from __future__ import annotations

import json
from pathlib import Path

from app.main import app

DOCS = Path(__file__).resolve().parents[2] / "docs"
TAG_TITLES = {
    "health": "Служебное",
    "auth": "Вход",
    "student": "Ученик: профиль, «Сегодня», прогресс, магазин",
    "tasks": "Задачи и «Путь»",
    "exams": "Экзамен",
    "curators": "Кураторы",
    "admin": "Админка",
}


def main() -> None:
    schema = app.openapi()
    (DOCS / "openapi.json").write_text(
        json.dumps(schema, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    by_tag: dict[str, list[tuple[str, str, str]]] = {}
    for path, operations in schema["paths"].items():
        for method, op in operations.items():
            tag = (op.get("tags") or ["other"])[0]
            summary = (op.get("description") or op.get("summary") or "").strip().splitlines()
            by_tag.setdefault(tag, []).append((method.upper(), path, summary[0] if summary else ""))
    lines = [
        "# API «Байта»",
        "",
        "Сгенерировано из OpenAPI (`api/scripts/export_openapi.py`); полная схема —",
        "[`docs/openapi.json`](openapi.json), интерактивно — `/api/docs` на стенде.",
        "",
        "Общие правила:",
        "",
        "* Авторизация — `Authorization: Bearer <access>`; access живёт 15 минут, refresh — 30 дней",
        "  с ротацией (`POST /api/auth/refresh`).",
        "* Все мутации принимают `Idempotency-Key`: повтор с тем же ключом возвращает первый ответ.",
        "* Ошибки: `{\"detail\": {\"code\": \"…\", \"message\": \"текст для ученика\", …}}`.",
        "* Эталонный ответ, `hidden_seed` и решение никогда не приходят в ответах, кроме разбора",
        "  (`/reveal`) после закрытия задачи.",
        "* Лимиты: 60 ответов в минуту, 20 серверных запусков кода в час, 240 запросов в минуту.",
        "",
    ]
    for tag, rows in by_tag.items():
        lines += [f"## {TAG_TITLES.get(tag, tag)}", "", "| Метод | Путь | Назначение |", "|---|---|---|"]
        for method, path, summary in sorted(rows, key=lambda r: (r[1], r[0])):
            lines.append(f"| `{method}` | `{path}` | {summary.replace('|', '/')} |")
        lines.append("")
    (DOCS / "API.md").write_text("\n".join(lines), encoding="utf-8")
    print(f"{sum(len(r) for r in by_tag.values())} operations written")


if __name__ == "__main__":
    main()
