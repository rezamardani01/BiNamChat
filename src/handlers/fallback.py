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
"""دریافت‌کننده نهایی: پیام‌ها و دکمه‌هایی که هیچ هندلری نداشتند."""
from __future__ import annotations

from baleropy import Router
from baleropy.types import CallbackQuery, Message

from ..core import App
from ..ui import b, toast

router = Router(name="fallback")


@router.callback_query()
async def stale_button(event: CallbackQuery) -> None:
    await toast(event, "این دکمه دیگر معتبر نیست. /menu را بزن.", True)


@router.message()
async def stray_message(message: Message, app: App, user: dict) -> None:
    if message.content_type in ("successful_payment", "invoice", "new_chat_members", "left_chat_member", "unknown"):
        return
    if user["state"] == "searching":
        return await app.send(user["id"], "🔎 هنوز در حال جستجو هستیم...", [[b("❌ لغو جستجو", "s:cancel")]])
    await app.send(user["id"], "👇 برای ادامه از منوی زیر استفاده کن", [[b("🏠 منوی اصلی", "m:home")]])
