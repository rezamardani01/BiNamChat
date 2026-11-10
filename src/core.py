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
"""هستهٔ برنامه: شیء App، ارسال امن پیام، کپی پیام، لاگ‌ها و مدیریت دسترسی‌ها."""
from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, ClassVar

from baleropy import Bot, Button
from baleropy.exceptions import BaleAPIError, BaleBadRequest, BaleForbidden, BaleNetworkError
from baleropy.methods.base import BaleMethod
from baleropy.types import InlineKeyboardMarkup, MessageId, ReplyKeyboardMarkup, ReplyKeyboardRemove
from baleropy.types.markup import ButtonRows, ReplyMarkup, _build_inline_markup

from .db import Database
from .settings import Settings
from .util import now

log = logging.getLogger("binam")

ALL_PERMS: dict[str, str] = {
    "stats": "📊 آمار و داشبورد",
    "users": "👥 مدیریت کاربران",
    "coins": "🪙 مدیریت سکه",
    "premium": "👑 مدیریت حساب ویژه",
    "ban": "🚫 مسدودسازی و تعلیق",
    "reports": "🚨 گزارش‌ها",
    "broadcast": "📢 ارسال همگانی",
    "channels": "📣 قفل کانال‌ها",
    "settings": "⚙️ تنظیمات",
    "gifts": "🎁 کدهای هدیه",
    "finance": "💰 امور مالی",
    "support": "🎧 پشتیبانی",
    "logs": "🗂 لاگ‌ها",
}


class _CopyMessageEx(BaleMethod[MessageId]):
    """copyMessage با پارامترهای اختیاری reply و دکمه."""

    __api_method__: ClassVar[str] = "copyMessage"
    __returning__: ClassVar = MessageId

    chat_id: int | str
    from_chat_id: int | str
    message_id: int
    reply_to_message_id: int | None = None
    reply_markup: InlineKeyboardMarkup | None = None


@dataclass
class App:
    bot: Bot
    db: Database
    settings: Settings
    owner_id: int
    username: str = ""
    match_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    tasks: set[asyncio.Task] = field(default_factory=set)
    started_at: int = field(default_factory=now)
    broadcast_cancel: set[int] = field(default_factory=set)

    # ------------------------------------------------------------------ لینک‌ها
    def start_link(self, param: str) -> str:
        return f"https://ble.ir/{self.username}?start={param}"

    # ------------------------------------------------------------------ تسک‌ها
    def spawn(self, coro: Any) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self._task_done)
        return task

    def _task_done(self, task: asyncio.Task) -> None:
        self.tasks.discard(task)
        if not task.cancelled() and task.exception() is not None:
            log.error("background task failed", exc_info=task.exception())

    # ------------------------------------------------------------------ ارسال
    async def _mark_blocked(self, uid: int) -> None:
        await self.db.execute("UPDATE users SET bot_blocked = 1 WHERE id = ?", (uid,))

    @staticmethod
    def _is_gone(error: BaleAPIError) -> bool:
        text = str(error).lower()
        return isinstance(error, BaleForbidden) or any(
            s in text for s in ("blocked", "chat not found", "user not found", "deactivated", "forbidden")
        )

    async def send(self, uid: int, text: str, rows: ButtonRows | ReplyMarkup | None = None,
                   reply_to: int | None = None) -> int | None:
        """ارسال متن؛ شناسه پیام یا None در صورت شکست.

        `rows` می‌تواند ردیف دکمه‌ها یا یک ReplyMarkup (مثلاً ReplyKeyboardRemove) باشد.
        """
        try:
            if isinstance(rows, (InlineKeyboardMarkup, ReplyKeyboardMarkup, ReplyKeyboardRemove)):
                msg = await self.bot.send_message(uid, text[:4096], reply_to_message_id=reply_to,
                                                  reply_markup=rows)
            else:
                msg = await self.bot.send_message(uid, text[:4096], reply_to_message_id=reply_to,
                                                  buttons=rows or None)
            return msg.message_id
        except BaleAPIError as error:
            if self._is_gone(error):
                await self._mark_blocked(uid)
            elif reply_to is not None and isinstance(error, BaleBadRequest):
                return await self.send(uid, text, rows)
            else:
                log.warning("send to %s failed: %s", uid, error)
        except BaleNetworkError as error:
            log.warning("network error sending to %s: %s", uid, error)
        return None

    async def send_photo(self, uid: int, photo: str, caption: str, rows: ButtonRows | None = None) -> int | None:
        try:
            markup = _build_inline_markup(rows) if rows else None
            msg = await self.bot.send_photo(uid, photo, caption[:1024], reply_markup=markup)
            return msg.message_id
        except BaleAPIError as error:
            if self._is_gone(error):
                await self._mark_blocked(uid)
            else:
                log.warning("send_photo to %s failed: %s", uid, error)
        except BaleNetworkError:
            pass
        return None

    async def copy(self, uid: int, from_chat: int, mid: int, reply_to: int | None = None,
                   rows: ButtonRows | None = None) -> int | None:
        """کپی پیام (متن/رسانه) بدون نمایش فرستنده."""
        markup = _build_inline_markup(rows) if rows else None
        try:
            res = await self.bot(_CopyMessageEx(chat_id=uid, from_chat_id=from_chat, message_id=mid,
                                                reply_to_message_id=reply_to, reply_markup=markup))
            return res.message_id
        except BaleAPIError as error:
            if self._is_gone(error):
                await self._mark_blocked(uid)
                return None
            if isinstance(error, BaleBadRequest) and (reply_to is not None or markup is not None):
                try:
                    res = await self.bot.copy_message(uid, from_chat, mid)
                    return res.message_id
                except BaleAPIError as inner:
                    if self._is_gone(inner):
                        await self._mark_blocked(uid)
                    else:
                        log.warning("copy to %s failed: %s", uid, inner)
                    return None
            log.warning("copy to %s failed: %s", uid, error)
        except BaleNetworkError as error:
            log.warning("network error copying to %s: %s", uid, error)
        return None

    async def delete(self, chat_id: int, mid: int | None) -> None:
        if not mid:
            return
        try:
            await self.bot.delete_message(chat_id, mid)
        except (BaleAPIError, BaleNetworkError):
            pass

    async def edit(self, chat_id: int, mid: int, text: str, rows: ButtonRows | None = None) -> bool:
        try:
            await self.bot.edit_message_text(chat_id, mid, text[:4096], buttons=rows or None)
            return True
        except BaleAPIError as error:
            if "not modified" in str(error).lower():
                return True
            return False
        except BaleNetworkError:
            return False

    # ------------------------------------------------------------------ دسترسی‌ها
    async def perms_of(self, uid: int) -> set[str]:
        if uid == self.owner_id:
            return set(ALL_PERMS)
        raw = await self.db.val("SELECT perms FROM admins WHERE user_id = ?", (uid,))
        if raw is None:
            return set()
        return {p for p in str(raw).split(",") if p in ALL_PERMS}

    async def is_admin(self, uid: int) -> bool:
        if uid == self.owner_id:
            return True
        return await self.db.one("SELECT 1 FROM admins WHERE user_id = ?", (uid,)) is not None

    async def can(self, uid: int, perm: str) -> bool:
        return perm in await self.perms_of(uid)

    async def admin_ids(self, perm: str | None = None) -> list[int]:
        ids = {self.owner_id} if self.owner_id else set()
        for row in await self.db.all("SELECT user_id, perms FROM admins"):
            if perm is None or perm in str(row["perms"]).split(","):
                ids.add(row["user_id"])
        return sorted(ids)

    # ------------------------------------------------------------------ لاگ
    async def audit(self, admin_id: int, action: str, target: Any = None, details: str = "") -> None:
        await self.db.execute(
            "INSERT INTO audit(admin_id, action, target, details, created_at) VALUES(?,?,?,?,?)",
            (admin_id, action, None if target is None else str(target), details[:500], now()),
        )
        extra = f"\n🎯 هدف: {target}" if target is not None else ""
        extra += f"\n📝 جزئیات: {details[:200]}" if details else ""
        self.spawn(self.event(f"🛠 عملیات مدیر\n👤 مدیر: {admin_id}\n⚙️ عمل: {action}{extra}", "admin"))

    async def error(self, source: str, message: str) -> None:
        log.error("%s: %s", source, message)
        try:
            await self.db.execute(
                "INSERT INTO errors(source, message, created_at) VALUES(?,?,?)",
                (source[:60], message[:500], now()),
            )
        except Exception:  # pragma: no cover
            pass

    async def event(self, text: str, cat: str = "admin") -> None:
        """گزارش رویداد به کانال لاگ (در صورت تنظیم و روشن‌بودن دسته)."""
        target = self.settings.get("log_channel").strip()
        if not target or not self.settings.on(f"log_{cat}"):
            return
        try:
            chat: int | str = int(target)
        except ValueError:
            chat = target
        try:
            await self.bot.send_message(chat, text[:4000])
        except (BaleAPIError, BaleNetworkError):
            pass


def parse_step(raw: str) -> dict:
    try:
        data = json.loads(raw) if raw else {}
        return data if isinstance(data, dict) else {}
    except ValueError:
        return {}


__all__ = ["App", "ALL_PERMS", "Button", "parse_step", "log"]
