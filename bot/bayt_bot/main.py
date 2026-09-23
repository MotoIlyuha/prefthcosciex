"""Entry point: webhook server on :8090 (``/bot/webhook``) or long polling locally."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
    WebAppInfo,
)
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bayt_bot.api import ApiClient
from bayt_bot.config import Config
from bayt_bot.texts import HELP, Reply, parse_start, start_reply, web_reply
from bayt_bot.throttle import Throttle

log = logging.getLogger("bayt.bot")
WEBHOOK_PATH = "/bot/webhook"


def keyboard(reply: Reply) -> InlineKeyboardMarkup | None:
    if not reply.buttons:
        return None
    rows = []
    for title, kind, value in reply.buttons:
        if kind == "webapp" and value.startswith("https://"):
            rows.append([InlineKeyboardButton(text=title, web_app=WebAppInfo(url=value))])
        else:
            rows.append([InlineKeyboardButton(text=title, url=value)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def tg_user(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "first_name": user.first_name,
        "username": user.username,
        "language_code": user.language_code,
    }


def build_router(config: Config, api: ApiClient) -> Router:
    router = Router()

    @router.message(CommandStart())
    async def start(message: Message) -> None:
        if message.from_user is None:
            return
        payload = parse_start(message.text)
        if payload == "web":
            url = await api.web_link(tg_user(message.from_user))
            reply = web_reply(url)
        else:
            result = await api.start(tg_user(message.from_user), payload)
            reply = start_reply(payload, result, config.public_base_url)
        await message.answer(reply.text, reply_markup=keyboard(reply))

    @router.message(Command("web"))
    async def web_login(message: Message) -> None:
        if message.from_user is None:
            return
        reply = web_reply(await api.web_link(tg_user(message.from_user)))
        await message.answer(reply.text, reply_markup=keyboard(reply))

    @router.message(Command("help"))
    async def help_(message: Message) -> None:
        await message.answer(HELP)

    @router.message()
    async def fallback(message: Message) -> None:
        await message.answer("Я не веду переписку — всё в приложении. /help — команды.")

    return router


def build_dispatcher(config: Config, api: ApiClient) -> Dispatcher:
    dispatcher = Dispatcher()
    dispatcher.message.middleware(Throttle())
    dispatcher.include_router(build_router(config, api))
    return dispatcher


async def health(_: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


async def run() -> None:
    logging.basicConfig(level=logging.INFO)
    config = Config.from_env()
    if not config.token:
        raise SystemExit("TELEGRAM_BOT_TOKEN is required")
    bot = Bot(config.token)
    api = ApiClient(config.api_url, config.internal_token)
    dispatcher = build_dispatcher(config, api)
    if config.mode == "polling":
        await bot.delete_webhook(drop_pending_updates=False)
        await dispatcher.start_polling(bot)
        return
    if not config.webhook_secret:
        raise SystemExit("TELEGRAM_WEBHOOK_SECRET is required in webhook mode")
    await bot.set_webhook(
        f"{config.public_base_url}{WEBHOOK_PATH}",
        secret_token=config.webhook_secret,
        allowed_updates=["message"],
    )
    app = web.Application()
    # Telegram signs each update with the secret header; others get 401.
    SimpleRequestHandler(dispatcher, bot, secret_token=config.webhook_secret).register(
        app, path=WEBHOOK_PATH
    )
    app.router.add_get("/health", health)
    setup_application(app, dispatcher, bot=bot)
    runner = web.AppRunner(app)
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", 8090).start()
    log.info("webhook listening on :8090%s", WEBHOOK_PATH)
    await asyncio.Event().wait()


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
