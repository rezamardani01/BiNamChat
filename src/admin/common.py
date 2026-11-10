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
"""ابزارهای مشترک پنل مدیریت."""
from __future__ import annotations

from typing import Any

from baleropy.dispatcher import BaseMiddleware
from baleropy.exceptions import CancelHandler
from baleropy.types import CallbackQuery, Message

from .. import repo
from ..core import ALL_PERMS, App
from ..ui import b, toast
from ..util import ago, esc, fa, jdate

OWNER_ONLY = "__owner__"
# پیشوند دومِ callback → مجوز لازم
PERM_FOR: dict[str, str | None] = {
    "home": None, "mt": "settings", "st": "stats", "lv": "stats", "u": "users", "rp": "reports",
    "bc": "broadcast", "ch": "channels", "se": "settings", "gf": "gifts", "fn": "finance",
    "lg": "logs", "tk": "support", "ad": OWNER_ONLY, "bk": OWNER_ONLY,
}
PER_PAGE = 8


class AdminGate(BaseMiddleware):
    """هر callback که با `a:` شروع شود فقط برای مدیر دارای مجوز اجرا می‌شود."""

    async def __call__(self, handler: Any, event: Any, data: dict) -> Any:
        if not isinstance(event, CallbackQuery) or not (event.data or "").startswith("a:"):
            return await handler(event, data)
        app: App = data["app"]
        parts = event.data.split(":")
        need = PERM_FOR.get(parts[1] if len(parts) > 1 else "home", OWNER_ONLY)
        uid = event.from_user.id
        if not await app.is_admin(uid):
            await toast(event, "⛔️ دسترسی ندارید", True)
            raise CancelHandler()
        if need == OWNER_ONLY and uid != app.owner_id:
            await toast(event, "این بخش فقط مخصوص مالک ربات است", True)
            raise CancelHandler()
        if need and need != OWNER_ONLY and not await app.can(uid, need):
            await toast(event, f"مجوز «{ALL_PERMS.get(need, need)}» را ندارید", True)
            raise CancelHandler()
        return await handler(event, data)


def back(to: str = "a:home", text: str = "🔙 بازگشت") -> list[Any]:
    return [b(text, to), b("🏠 پنل", "a:home")] if to != "a:home" else [b("🏠 پنل مدیریت", "a:home")]


def uname(u: dict | None) -> str:
    if not u:
        return "—"
    tag = f" @{u['username']}" if u.get("username") else ""
    return f"{esc(u['name'], 24) or u['id']}{tag}"


def user_line(u: dict) -> str:
    flags = ("🚫" if u["banned"] else "") + ("⏳" if repo.is_suspended(u) else "") + ("👑" if repo.is_premium(u) else "")
    return f"{flags}{repo.gender_text(u['gender'])[:1] if u['gender'] else '👤'} {esc(u['name'], 18) or u['id']} • {u['id']}"


async def user_card(app: App, u: dict) -> str:
    chats = await app.db.val("SELECT COUNT(*) FROM chats WHERE a = ? OR b = ?", (u["id"], u["id"]), 0)
    reports_in = await app.db.val("SELECT COUNT(*) FROM reports WHERE reported_id = ?", (u["id"],), 0)
    reports_out = await app.db.val("SELECT COUNT(*) FROM reports WHERE reporter_id = ?", (u["id"],), 0)
    friends = await app.db.val("SELECT COUNT(*) FROM friends WHERE user_id = ?", (u["id"],), 0)
    invited = await app.db.val("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (u["id"],), 0)
    spent = await app.db.val("SELECT COALESCE(SUM(amount_irr),0) FROM payments WHERE user_id = ? AND status = 'paid'", (u["id"],), 0)
    status = []
    if u["banned"]:
        status.append(f"🚫 مسدود{' — ' + esc(u['ban_reason']) if u['ban_reason'] else ''}")
    if repo.is_suspended(u):
        status.append(f"⏳ تعلیق تا {jdate(u['suspended_until'], 'full')}")
    if u["bot_blocked"]:
        status.append("🔕 ربات را بلاک کرده")
    state = {"idle": "آزاد", "searching": "در حال جستجو", "chat": "در گفتگو"}.get(u["state"], u["state"])
    lines = [
        f"👤 **{uname(u)}**", "━━━━━━━━━━━━━━",
        f"🆔 {u['id']}", f"{repo.gender_text(u['gender'])}", f"🎂 سن: {fa(u['age']) if u['age'] else '—'}",
        f"📍 {esc(u['province']) or '—'}، {esc(u['city']) or '—'}",
        f"🪙 سکه: {fa(u['coins'])}",
        "👑 ویژه: " + (f"تا {jdate(u['premium_until'], 'short')}" if repo.is_premium(u) else "ندارد"),
        f"📌 وضعیت: {state}",
        f"💬 چت‌ها: {fa(chats)} • پیام‌ها: {fa(u['msgs_sent'])} • دوستان: {fa(friends)}",
        f"🚨 گزارش علیه او: {fa(reports_in)} • گزارش‌های او: {fa(reports_out)}",
        f"🎁 دعوت‌شده‌ها: {fa(invited)}", f"💰 مجموع پرداختی: {fa(spent // 10)} تومان",
        f"📅 عضویت: {jdate(u['joined_at'], 'short')} • آخرین بازدید: {ago(u['last_seen'])}",
    ]
    if u["referrer_id"]:
        lines.append(f"🔗 دعوت‌کننده: {u['referrer_id']}")
    if status:
        lines.append("━━━━━━━━━━━━━━")
        lines += status
    return "\n".join(lines)


async def admin_only(app: App, event: Message | CallbackQuery, uid: int, perm: str) -> bool:
    if await app.can(uid, perm):
        return True
    if isinstance(event, CallbackQuery):
        await toast(event, "مجوز ندارید", True)
    else:
        await app.send(uid, "⛔️ مجوز این کار را ندارید.")
    return False
