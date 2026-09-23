"""Bot behaviour that does not need Telegram: deep links, replies, API calls, flood."""

from __future__ import annotations

import json

import httpx

from bayt_bot.api import ApiClient
from bayt_bot.config import Config
from bayt_bot.main import build_dispatcher, keyboard
from bayt_bot.texts import parse_start, start_reply, web_reply
from bayt_bot.throttle import Throttle

BASE = "https://bayt.example"


def test_start_payload_is_validated() -> None:
    assert parse_start("/start cur_AbC-12") == "cur_AbC-12"
    assert parse_start("/start") == ""
    assert parse_start("/start ../../etc") == ""
    assert parse_start("/start " + "x" * 100) == ""


def test_curator_invite_reply() -> None:
    ok = start_reply("cur_t", {"curator": {"status": "pending"}}, BASE)
    assert "куратором" in ok.text
    assert ok.buttons[0][2] == f"{BASE}/?startapp=students"
    bad = start_reply("cur_t", {"curator_error": {"message": "Приглашение истекло"}}, BASE)
    assert bad.text == "Приглашение истекло"


def test_screen_and_referral_links() -> None:
    assert start_reply("today", {}, BASE).buttons[0][2] == f"{BASE}/?startapp=today"
    assert start_reply("task_15", {}, BASE).buttons[0][2].endswith("startapp=task_15")
    assert "друг" in start_reply("ref_42", {}, BASE).text
    plain = start_reply("", {}, BASE)
    assert plain.buttons[0] == ("Открыть «Байт»", "webapp", f"{BASE}/")


def test_keyboard_uses_web_app_only_over_https() -> None:
    markup = keyboard(start_reply("", {}, BASE))
    assert markup is not None and markup.inline_keyboard[0][0].web_app is not None
    local = keyboard(start_reply("", {}, "http://localhost:8080"))
    assert local is not None and local.inline_keyboard[0][0].url == "http://localhost:8080/"
    link = keyboard(web_reply("https://bayt.example/web/login?token=x"))
    assert link is not None and link.inline_keyboard[0][0].url.endswith("token=x")


async def test_api_client_sends_the_internal_token() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("web-link"):
            return httpx.Response(200, json={"url": "https://x/web/login?token=1"})
        return httpx.Response(200, json={"user_id": 1, "created": True})

    api = ApiClient("http://api/api", "secret", transport=httpx.MockTransport(handler))
    user = {"id": 5, "first_name": "A", "username": None, "language_code": "ru"}
    assert (await api.start(user, "cur_x"))["created"] is True
    assert await api.web_link(user) == "https://x/web/login?token=1"
    assert all(r.headers["X-Internal-Token"] == "secret" for r in seen)
    assert json.loads(seen[0].content)["payload"] == "cur_x"
    assert seen[0].url.path == "/api/internal/bot/start"


def test_throttle() -> None:
    now = [100.0]
    throttle = Throttle(interval_s=1.0, clock=lambda: now[0])
    assert throttle.allow(1)
    assert not throttle.allow(1)
    assert throttle.allow(2)
    now[0] += 1.5
    assert throttle.allow(1)


def test_dispatcher_builds() -> None:
    config = Config("1:x", "http://api/api", "t", BASE, "s", "webhook", "app", "bayt_bot")
    dispatcher = build_dispatcher(config, ApiClient("http://api/api", "t"))
    assert dispatcher.sub_routers
