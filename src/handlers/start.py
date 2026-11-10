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
"""شروع، منوی اصلی، دیپ‌لینک‌ها و بررسی عضویت."""
from __future__ import annotations

from baleropy import F, Router
from baleropy.filters import Command, CommandObject, CommandStart
from baleropy.types import CallbackQuery, Message

from .. import matching, repo
from ..core import App
from ..middlewares import user_mw
from ..texts import DEFAULT_WELCOME
from ..ui import DANGER, PRIMARY, SUCCESS, b, show, toast, url
from ..util import esc, fa, jdate

router = Router(name="start")


def status_line(user: dict) -> str:
    parts = [f"🪙 {fa(user['coins'])} سکه"]
    if repo.is_premium(user):
        parts.append(f"👑 ویژه تا {jdate(user['premium_until'], 'short')}")
    return "\n".join(parts)


async def home_text(app: App, user: dict) -> str:
    text = app.settings.get("welcome").strip() or DEFAULT_WELCOME
    ann = app.settings.get("announcement").strip()
    if ann:
        text += f"\n\n📣 **اطلاعیه**\n{ann}"
    return f"{text}\n\n━━━━━━━━━━━━━━\n{status_line(user)}"


def home_rows(app: App, user: dict, is_admin: bool) -> list[list]:
    rows = [
        [b("🎲 چت ناشناس", "s:home", SUCCESS)],
        [b("🔗 لینک ناشناس من", "l:home", PRIMARY), b("💌 به مخاطب خاص", "k:home", PRIMARY)],
        [b("👤 پروفایل من", "p:home"), b("🛍 فروشگاه", "w:home")],
        [b("👥 دوستان", "f:home"), b("🎁 دعوت دوستان", "w:ref")],
        [b("⚙️ تنظیمات", "st:home"), b("📚 راهنما", "h:home")],
    ]
    if app.settings.on("support_enabled"):
        rows.append([b("🎧 پشتیبانی", "sp:home")])
    channel = app.settings.get("official_channel").strip()
    if channel.startswith("http"):
        rows.append([url("📣 کانال رسمی", channel)])
    if is_admin:
        rows.append([b("🛠 پنل مدیریت", "a:home", DANGER)])
    return rows


async def send_home(app: App, event: Message | CallbackQuery, user: dict, *, intro: str = "",
                    fresh: bool = False) -> None:
    """منوی اصلی را نشان می‌دهد (در حال چت بودن را هم مدیریت می‌کند)."""
    uid = user["id"]
    if user["state"] == "chat":
        rows = matching.chat_controls()
        text = "💬 الان وسط یه گفتگو هستی؛ هر پیامی بفرستی برای مخاطبت می‌رسه."
        if isinstance(event, CallbackQuery):
            await toast(event, "اول گفتگوی فعلی را تمام کن")
        await app.send(uid, text, rows)
        return
    is_admin = await app.is_admin(uid)
    text = intro + await home_text(app, user)
    rows = home_rows(app, user, is_admin)
    banner = app.settings.get("banner").strip()
    if isinstance(event, Message) or fresh:
        if banner:
            if await app.send_photo(uid, banner, text, rows):
                return
        await app.send(uid, text, rows)
    else:
        await show(app, event, text, rows)


# ---------------------------------------------------------------- دستورها
@router.message(CommandStart())
async def cmd_start(message: Message, command: CommandObject, app: App, user: dict) -> None:
    uid = user["id"]
    arg = (command.args or "").strip()
    if user["state"] == "searching":
        await matching.dequeue(app, uid)
        user["state"] = "idle"
    if user["step"]:
        await repo.set_step(app, uid, "")
    if arg and not arg.startswith("ref_"):
        from .links import open_anonymous
        if await open_anonymous(app, message, user, arg):
            return
    await send_home(app, message, user)


@router.message(Command("menu"))
async def cmd_menu(message: Message, app: App, user: dict) -> None:
    if user["step"]:
        await repo.set_step(app, user["id"], "")
    await send_home(app, message, user)


@router.message(Command("cancel"))
async def cmd_cancel(message: Message, app: App, user: dict) -> None:
    if user["state"] == "searching":
        await matching.dequeue(app, user["id"])
    await repo.set_step(app, user["id"], "")
    await app.send(user["id"], "✅ لغو شد.", [[b("🏠 منوی اصلی", "m:home")]])


@router.callback_query(F.data == "m:home")
async def cb_home(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if user["step"]:
        await repo.set_step(app, user["id"], "")
    await send_home(app, event, user)


@router.callback_query(F.data == "noop")
async def cb_noop(event: CallbackQuery) -> None:
    await toast(event)


@router.callback_query(F.data == "fj:check")
async def cb_join_check(event: CallbackQuery, app: App, user: dict, is_admin: bool) -> None:
    missing = await user_mw.missing_channels(app, user["id"], force=True)
    if missing:
        names = "، ".join(esc(c["title"] or "کانال") for c in missing)
        return await toast(event, f"هنوز عضو این کانال‌ها نیستی: {names}"[:190], True)
    await toast(event, "✅ عضویتت تأیید شد")
    await app.delete(user["id"], event.message.message_id if event.message else None)
    from .onboarding import proceed_after_signup
    await proceed_after_signup(app, event, await repo.get_user(app, user["id"]) or user)


@router.callback_query(F.data.startswith("x:cancel"))
async def cb_cancel(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event, "لغو شد")
    await repo.set_step(app, user["id"], "")
    await send_home(app, event, user)
