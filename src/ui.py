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
"""اجزای رابط شیشه‌ای: دکمه‌های رنگی، نمایش/ویرایش پیام، صفحه‌بندی."""
from __future__ import annotations

from typing import Any, Sequence

from baleropy import Button
from baleropy.exceptions import BaleAPIError, BaleNetworkError
from baleropy.types import CallbackQuery, InlineKeyboardButton, Message

from .core import App, log

PRIMARY, SUCCESS, DANGER = "primary", "success", "danger"
Rows = list[list[InlineKeyboardButton]]


def b(text: str, data: str, style: str | None = None) -> InlineKeyboardButton:
    return Button.inline(text, data[:64], style=style)


def url(text: str, link: str, style: str | None = None) -> InlineKeyboardButton:
    return Button.url(text, link, style=style)


def home_row(text: str = "🏠 منوی اصلی") -> list[InlineKeyboardButton]:
    return [b(text, "m:home")]


def nav(back: str | None = None, home: bool = True) -> list[list[InlineKeyboardButton]]:
    row: list[InlineKeyboardButton] = []
    if back:
        row.append(b("🔙 بازگشت", back))
    if home:
        row.append(b("🏠 منو", "m:home"))
    return [row] if row else []


def chunk(buttons: Sequence[InlineKeyboardButton], size: int) -> Rows:
    return [list(buttons[i:i + size]) for i in range(0, len(buttons), size)]


def pager(prefix: str, page: int, total: int, per_page: int) -> list[InlineKeyboardButton]:
    """ردیف صفحه‌بندی؛ prefix + شماره صفحه به‌عنوان callback."""
    pages = max(1, -(-total // per_page))
    if pages <= 1:
        return []
    row = []
    if page > 0:
        row.append(b("◀️ قبلی", f"{prefix}{page - 1}"))
    row.append(b(f"{page + 1}/{pages}", "noop"))
    if page < pages - 1:
        row.append(b("بعدی ▶️", f"{prefix}{page + 1}"))
    return row


def clean(rows: Sequence[Sequence[InlineKeyboardButton]] | None) -> Rows | None:
    if not rows:
        return None
    out = [list(r) for r in rows if r]
    return out or None


async def show(app: App, event: Message | CallbackQuery, text: str,
               rows: Sequence[Sequence[InlineKeyboardButton]] | None = None) -> int | None:
    """اگر رویداد دکمه بود پیام را ویرایش می‌کند، وگرنه پیام تازه می‌فرستد."""
    rows_c = clean(rows)
    text = text[:4096]
    if isinstance(event, CallbackQuery):
        msg = event.message
        uid = event.from_user.id
        if msg is not None:
            try:
                if msg.photo or msg.video or msg.document or msg.animation:
                    await msg.edit_caption(text[:1024], buttons=rows_c)
                else:
                    await msg.edit_text(text, buttons=rows_c)
                return msg.message_id
            except BaleAPIError as error:
                if "not modified" in str(error).lower():
                    return msg.message_id
                log.debug("edit failed (%s); sending a new message", error)
            except BaleNetworkError:
                return None
            await app.delete(uid, msg.message_id)
        return await app.send(uid, text, rows_c)
    try:
        sent = await event.answer(text, buttons=rows_c)
        return sent.message_id
    except (BaleAPIError, BaleNetworkError) as error:
        log.warning("show failed: %s", error)
        return None


async def toast(event: CallbackQuery, text: str | None = None, alert: bool = False) -> None:
    try:
        await event.answer(text, show_alert=alert or None)
    except (BaleAPIError, BaleNetworkError):
        pass


def card(title: str, *lines: Any) -> str:
    """کادر متنی ساده با عنوان."""
    body = "\n".join(str(l) for l in lines if l is not None and l != "")
    return f"✦ **{title}**\n━━━━━━━━━━━━━━\n{body}"
