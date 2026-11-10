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
"""میدلورهای ورودی: بارگذاری کاربر، محدودیت‌ها، حالت تعمیر، مسدودی و عضویت اجباری."""
from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from typing import Any, Awaitable, Callable

from baleropy.dispatcher import BaseMiddleware
from baleropy.exceptions import BaleAPIError, BaleBadRequest, BaleNetworkError, BaleNotFound, CancelHandler
from baleropy.types import CallbackQuery, Message

from . import repo
from .core import App
from .ui import b, url
from .util import duration, jdate, now

_START_REF = re.compile(r"^/start(?:@\w+)?\s+ref_(\d{1,15})\s*$")
JOIN_TTL = 90


class UserMiddleware(BaseMiddleware):
    """کاربر را بارگذاری می‌کند و ورود افراد مسدود/غیرمجاز را متوقف می‌کند."""

    def __init__(self) -> None:
        self._hits: dict[int, deque[float]] = defaultdict(lambda: deque(maxlen=30))
        self._joined: dict[int, float] = {}

    # ------------------------------------------------------------------
    def _flooding(self, uid: int) -> bool:
        hits = self._hits[uid]
        t = time.monotonic()
        hits.append(t)
        return len(hits) >= 30 and t - hits[0] < 12

    async def __call__(self, handler: Callable[[Any, dict], Awaitable[Any]], event: Any, data: dict) -> Any:
        app: App = data["app"]
        if isinstance(event, Message):
            tg_user, chat = event.from_user, event.chat
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user
            chat = event.message.chat if event.message else None
        else:
            return await handler(event, data)

        chat_type = getattr(getattr(chat, "type", None), "value", getattr(chat, "type", None))
        if tg_user is None or tg_user.is_bot or chat is None or chat_type != "private":
            raise CancelHandler()

        uid = tg_user.id
        if self._flooding(uid):
            if isinstance(event, CallbackQuery):
                await _quiet(event.answer("⏳ آروم‌تر، خیلی سریع می‌زنی!"))
            raise CancelHandler()

        referrer = None
        if isinstance(event, Message) and event.text:
            m = _START_REF.match(event.text.strip())
            if m:
                referrer = int(m.group(1))

        is_admin = await app.is_admin(uid)
        existing = await repo.get_user(app, uid)
        if existing is None and not is_admin and not app.settings.on("registration"):
            await _reply(app, event, "⛔️ ثبت‌نام کاربران جدید فعلاً بسته است. کمی بعد دوباره تلاش کن.")
            raise CancelHandler()

        user, is_new = await repo.ensure_user(app, tg_user, referrer)
        if user["state"] != "idle":
            from . import matching
            user = await matching.heal(app, user)
        data["user"] = user
        data["is_new"] = is_new
        data["is_admin"] = is_admin

        if is_new:
            app.spawn(app.event(f"🆕 کاربر جدید\n👤 {user['name']} ({uid})" + (f" — دعوت‌شده از {referrer}" if user["referrer_id"] else ""), "users"))

        paying = isinstance(event, Message) and event.successful_payment is not None
        if not is_admin and not paying:
            if user["banned"]:
                reason = f"\nدلیل: {user['ban_reason']}" if user["ban_reason"] else ""
                await _reply(app, event, f"🚫 حساب شما توسط مدیریت مسدود شده است.{reason}")
                raise CancelHandler()
            if repo.is_suspended(user):
                left = duration(int(user["suspended_until"]) - now())
                await _reply(app, event, f"⏳ حساب شما تا {jdate(user['suspended_until'], 'full')} "
                                          f"({left} دیگر) تعلیق است.")
                raise CancelHandler()
            if app.settings.on("maintenance"):
                await _reply(app, event, "🛠 ربات در حال به‌روزرسانی است؛ لطفاً کمی بعد برگرد.")
                raise CancelHandler()
        if user["onboard"] != "done" and not paying and not (isinstance(event, CallbackQuery) and (event.data or "").startswith("ob:")):
            from .handlers import onboarding
            if isinstance(event, Message) and event.text:
                arg = event.text.strip().partition(" ")[2].strip()
                if event.text.startswith("/start") and arg and not arg.startswith("ref_"):
                    onboarding.PENDING_START[uid] = arg
            if isinstance(event, CallbackQuery):
                await _quiet(event.answer())
            await onboarding.prompt_stage(app, event, user)
            raise CancelHandler()
        panel_access = is_admin and (
            (isinstance(event, CallbackQuery) and (event.data or "").startswith("a:"))
            or (isinstance(event, Message) and (event.text or "").startswith("/panel"))
        )
        if (
            user["onboard"] == "done"
            and app.settings.on("force_join")
            and not paying
            and not panel_access
            and user["state"] != "chat"
            and not (isinstance(event, CallbackQuery) and event.data == "fj:check")
        ):
            missing = await self.missing_channels(app, uid)
            if missing:
                await _send_join_prompt(app, event, missing)
                raise CancelHandler()
        return await handler(event, data)

    async def missing_channels(self, app: App, uid: int, *, force: bool = False) -> list[dict]:
        if not force and now() - self._joined.get(uid, 0) < JOIN_TTL:
            return []
        missing = await missing_channels(app, uid)
        if not missing:
            self._joined[uid] = now()
        else:
            self._joined.pop(uid, None)
        return missing


user_mw = UserMiddleware()


JOINED = {"member", "creator", "owner", "administrator"}


async def channel_status(app: App, ch: dict, uid: int) -> tuple[bool | None, str]:
    """(عضو است؟، توضیح). None یعنی نتوانستیم بررسی کنیم (خطای ربات/شبکه)."""
    try:
        chat_id: int | str = int(ch["chat_id"])
    except ValueError:
        chat_id = ch["chat_id"]
    try:
        member = await app.bot.get_chat_member(chat_id, uid)
    except (BaleBadRequest, BaleNotFound) as error:
        # کاربر عضو کانال نیست (یا برای بله قابل‌پیدا نیست)
        return False, f"error: {error}"
    except BaleAPIError as error:
        await app.error("force_join", f"{ch['chat_id']}: {error}")
        return None, f"error: {error}"
    except BaleNetworkError as error:
        return None, f"network: {error}"
    status = str(getattr(member.status, "value", member.status)).lower()
    if status in JOINED:
        return True, status
    if status == "restricted" and member.is_member is not False:
        return True, status
    return False, status


async def sponsor_track(app: App, ch: dict, uid: int, ok: bool) -> None:
    """شمارش عضویت‌های اسپانسری: فقط کسانی که اول عضو نبودند و بعد از درخواست ربات عضو شدند."""
    if ok is False:
        await app.db.execute("INSERT OR IGNORE INTO sponsor_seen(chat_id, user_id, first_missing_at) VALUES(?,?,?)",
                             (ch["chat_id"], uid, now()))
        return
    done = None
    async with app.db.tx() as tx:
        row = await tx.one("SELECT * FROM sponsor_seen WHERE chat_id = ? AND user_id = ? AND joined_at IS NULL",
                           (ch["chat_id"], uid))
        if not row:
            return
        live = await tx.one("SELECT * FROM channels WHERE chat_id = ? AND status = 'active' AND kind = 'sponsor'",
                            (ch["chat_id"],))
        if not live:
            return
        await tx.execute("UPDATE sponsor_seen SET joined_at = ? WHERE chat_id = ? AND user_id = ?",
                         (now(), ch["chat_id"], uid))
        joined = live["joined"] + 1
        if joined >= live["target"]:
            await tx.execute("UPDATE channels SET joined = ?, status = 'done', finished_at = ? WHERE chat_id = ?",
                             (joined, now(), ch["chat_id"]))
            done = live
        else:
            await tx.execute("UPDATE channels SET joined = ? WHERE chat_id = ?", (joined, ch["chat_id"]))
    if done:
        text = (f"🎯 کمپین اسپانسری تکمیل شد!\n📣 کانال: {done['title'] or done['chat_id']}\n"
                f"👥 هدف: {done['target']} عضو\n🔓 قفل این کانال به‌طور خودکار برداشته شد.")
        for admin_id in await app.admin_ids("channels"):
            await app.send(admin_id, text)
        await app.event(text, "admin")


async def missing_channels(app: App, uid: int) -> list[dict]:
    channels = await app.db.all("SELECT * FROM channels WHERE status = 'active' ORDER BY added_at")
    missing = []
    for ch in channels:
        ok, _ = await channel_status(app, ch, uid)
        if ch["kind"] == "sponsor" and ok is not None:
            await sponsor_track(app, ch, uid, ok)
        if ok is False:
            missing.append(ch)
    return missing


async def send_join_prompt(app: App, uid: int, missing: list[dict]) -> None:
    rows = [[url(f"📣 {ch['title'] or 'کانال'}", ch["link"])] for ch in missing if ch["link"]]
    rows.append([b("✅ عضو شدم", "fj:check", "success")])
    await app.send(uid, "📣 برای ادامه، اول باید عضو کانال(های) زیر بشی و بعد روی «عضو شدم» بزنی:", rows)


async def _send_join_prompt(app: App, event: Any, missing: list[dict]) -> None:
    rows = [[url(f"📣 {ch['title'] or 'کانال'}", ch["link"])] for ch in missing if ch["link"]]
    rows.append([b("✅ عضو شدم", "fj:check", "success")])
    text = "📣 برای استفاده از ربات، اول عضو کانال(های) زیر شو و بعد روی «عضو شدم» بزن:"
    if isinstance(event, CallbackQuery):
        await _quiet(event.answer("اول باید عضو کانال‌ها بشی", show_alert=True))
        uid = event.from_user.id
    else:
        uid = event.from_user.id
    await app.send(uid, text, rows)


async def _reply(app: App, event: Any, text: str) -> None:
    if isinstance(event, CallbackQuery):
        await _quiet(event.answer(text[:190], show_alert=True))
    else:
        await app.send(event.from_user.id, text)


async def _quiet(coro: Awaitable[Any]) -> None:
    try:
        await coro
    except (BaleAPIError, BaleNetworkError):
        pass
