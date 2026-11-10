# ==================================================
# Project Author: Reza Mardani
# Bale ID: @MrHanzo
# GitHub: https://github.com/rezamardani01
#
# This project is open-source and publicly available.
# You are free to use, study, modify, and distribute
# this source code in accordance with its license.
#
# Contributions, improvements, and suggestions are welcome.
# Please give proper credit to the original author
# when using or redistributing this project.
# ==================================================
# -*- coding: utf-8 -*-
"""ساخت و اجرای ربات."""
from __future__ import annotations

import asyncio
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from baleropy import Bot, Dispatcher
from baleropy.dispatcher.event.bases import ErrorEvent
from baleropy.types import CallbackQuery

import config

from . import __version__, matching
from .admin import router as admin_router
from .core import App
from .db import Database
from .handlers import fallback, friends, links, misc, onboarding, profile, start, stranger, wallet
from .middlewares import user_mw
from .settings import Settings
from .util import jdate, now

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "binam.db"
log = logging.getLogger("binam")


def setup_logging() -> None:
    (ROOT / "data").mkdir(exist_ok=True)
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    console = logging.StreamHandler()
    console.setFormatter(fmt)
    file = RotatingFileHandler(ROOT / "data" / "binam.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    file.setFormatter(fmt)
    logging.basicConfig(level=logging.INFO, handlers=[console, file])
    logging.getLogger("aiosqlite").setLevel(logging.WARNING)


def build_dispatcher(app: App) -> Dispatcher:
    dp = Dispatcher(app=app)
    for observer in (dp.message, dp.edited_message, dp.callback_query):
        observer.outer_middleware(user_mw)

    dp.include_routers(
        admin_router,
        start.router,
        onboarding.router,
        wallet.router,
        profile.router,
        links.router,
        friends.router,
        misc.router,
        stranger.router,
        fallback.router,
    )

    @dp.error()
    async def on_error(event: ErrorEvent, exception: Exception) -> bool:
        await app.error("handler", f"{type(exception).__name__}: {exception}")
        log.error("unhandled error", exc_info=exception)
        update = event.update
        cq = update.callback_query
        if isinstance(cq, CallbackQuery):
            try:
                await cq.answer("⚠️ خطایی رخ داد، دوباره امتحان کن", show_alert=True)
            except Exception:  # noqa: BLE001
                pass
        return True

    return dp


async def run() -> None:
    setup_logging()
    if not config.TOKEN or config.TOKEN.startswith("PUT_"):
        sys.exit("❌ توکن ربات را در config.py قرار بده (TOKEN).")
    if not isinstance(config.OWNER_ID, int) or config.OWNER_ID <= 0:
        sys.exit("❌ شناسه عددی مالک را در config.py قرار بده (OWNER_ID).")

    db = Database(DB_PATH)
    await db.connect()
    settings = Settings(db)
    await settings.load()
    bot = Bot(config.TOKEN)
    me = await bot.get_me()
    app = App(bot=bot, db=db, settings=settings, owner_id=config.OWNER_ID, username=me.username or "")
    dp = build_dispatcher(app)

    @dp.on_startup
    async def startup() -> None:
        await matching.recover_state(app)
        await db.execute("UPDATE broadcasts SET status = 'interrupted' WHERE status = 'running'")
        app.spawn(matching.cleanup_loop(app))
        log.info("BiNam %s started as @%s (%s)", __version__, me.username, jdate(now(), "full"))
        await app.send(app.owner_id, f"🟢 ربات بینام ({__version__}) روشن شد.\n/panel برای ورود به پنل مدیریت")

    @dp.on_shutdown
    async def shutdown() -> None:
        for task in list(app.tasks):
            task.cancel()
        await asyncio.gather(*app.tasks, return_exceptions=True)
        await db.close()
        log.info("BiNam stopped")

    await dp.start_polling(bot, handle_as_tasks=True, max_concurrent_updates=60)


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass
