"""What the bot says. Short phrases, no exclamation storms (11.11)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

START_PARAM = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
SCREENS = frozenset({"today", "path", "progress", "confidence", "profile", "exam", "students"})

GREETING = (
    "Привет! Я «Байт» — подготовка к ЕГЭ‑2027 по информатике.\n"
    "15 минут в день — и к июню ты знаешь, что решать."
)
HELP = (
    "Команды:\n"
    "/start — открыть приложение\n"
    "/web — ссылка для входа в веб‑версию с компьютера\n"
    "/help — эта справка\n\n"
    "Уведомления настраиваются в приложении: Профиль → Уведомления."
)


@dataclass(frozen=True, slots=True)
class Reply:
    text: str
    buttons: list[tuple[str, str, str]] = field(default_factory=list)
    """(title, kind, value): kind is ``webapp`` (Mini App URL) or ``url``."""


def app_url(base: str, start: str = "") -> str:
    """URL of the Mini App page inside Telegram; ``start`` becomes the start parameter."""
    return f"{base}/?startapp={start}" if start else f"{base}/"


def parse_start(text: str | None) -> str:
    parts = (text or "").split(maxsplit=1)
    payload = parts[1].strip() if len(parts) > 1 else ""
    return payload if START_PARAM.fullmatch(payload) else ""


def start_reply(payload: str, result: dict[str, Any], base: str) -> Reply:
    """Answer to ``/start <payload>`` after the API registered the chat."""
    open_app = ("Открыть «Байт»", "webapp", app_url(base))
    if payload.startswith("cur_"):
        if "curator" in result:
            return Reply(
                "Вы стали куратором. Ученик сейчас выберет, что вам будет видно: "
                "факт занятий, прогресс или всё. Дашборд — в приложении, вкладка «Ученики».",
                [("Открыть учеников", "webapp", app_url(base, "students"))],
            )
        error = result.get("curator_error") or {}
        message = error.get("message") if isinstance(error, dict) else None
        return Reply(message or "Приглашение не сработало. Попросите новую ссылку.", [open_app])
    if payload.startswith("ref_"):
        return Reply(
            GREETING + "\n\nТебя пригласил друг — начнём с короткого знакомства.", [open_app]
        )
    if payload in SCREENS or payload.startswith(("task_", "exam_")):
        return Reply("Открываю.", [("Открыть", "webapp", app_url(base, payload))])
    return Reply(GREETING, [open_app])


def web_reply(url: str) -> Reply:
    return Reply(
        "Ссылка для входа в веб‑версию (действует 10 минут, одноразовая). "
        "Удобно решать 24–27 за компьютером.",
        [("Войти в веб‑версию", "url", url)],
    )
