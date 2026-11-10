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
"""تنظیمات کاربر، لیست بلاک، راهنما، قوانین و پشتیبانی."""
from __future__ import annotations

from baleropy import F, Router
from baleropy.types import CallbackQuery, Message

from .. import repo
from ..core import App
from ..filters import Step
from ..texts import DEFAULT_RULES, HELP
from ..ui import DANGER, PRIMARY, SUCCESS, b, chunk, pager, show, toast, url
from ..util import esc, fa, jdate, now

router = Router(name="misc")
BL_PER_PAGE = 8


# ---------------------------------------------------------------- تنظیمات
async def settings_view(app: App, user: dict) -> tuple[str, list[list]]:
    blocked = await app.db.val("SELECT COUNT(*) FROM blocks WHERE user_id = ?", (user["id"],), 0)
    text = ("⚙️ **تنظیمات من**\n━━━━━━━━━━━━━━\n"
            f"{'🟢' if user['anon_on'] else '🔴'} دریافت پیام ناشناس: {'روشن' if user['anon_on'] else 'خاموش'}\n"
            f"🚫 کاربران بلاک‌شده: {fa(blocked)}\n"
            f"🆔 شناسه عددی تو: {user['id']}")
    rows = [
        [b("🔴 خاموش کردن پیام ناشناس" if user["anon_on"] else "🟢 روشن کردن پیام ناشناس", "st:anon",
           DANGER if user["anon_on"] else SUCCESS)],
        [b(f"🚫 لیست بلاک ({fa(blocked)})", "st:bl:0")],
        [b("📜 قوانین", "h:rules"), b("📚 راهنما", "h:home")],
        [b("🏠 منوی اصلی", "m:home")],
    ]
    return text, rows


@router.callback_query(F.data == "st:home")
async def cb_settings(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    text, rows = await settings_view(app, user)
    await show(app, event, text, rows)


@router.callback_query(F.data == "st:anon")
async def cb_anon(event: CallbackQuery, app: App, user: dict) -> None:
    user["anon_on"] = 0 if user["anon_on"] else 1
    await repo.update_user(app, user["id"], anon_on=user["anon_on"])
    await toast(event, "ذخیره شد")
    text, rows = await settings_view(app, user)
    await show(app, event, text, rows)


@router.callback_query(F.data.startswith("st:bl:"))
async def cb_blocks(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    page = max(0, int((event.data or "st:bl:0").split(":")[2]))
    total = await app.db.val("SELECT COUNT(*) FROM blocks WHERE user_id = ?", (user["id"],), 0)
    items = await app.db.all("SELECT blocked_id, created_at FROM blocks WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                             (user["id"], BL_PER_PAGE, page * BL_PER_PAGE))
    if not total:
        return await show(app, event, "🚫 لیست بلاک خالی است.", [[b("🔙 بازگشت", "st:home")]])
    buttons = [b(f"🔓 رفع بلاک • ناشناس {fa(page * BL_PER_PAGE + i + 1)} • {jdate(r['created_at'], 'day')}",
                 f"st:ub:{r['blocked_id']}") for i, r in enumerate(items)]
    rows = chunk(buttons, 1)
    nav = pager("st:bl:", page, total, BL_PER_PAGE)
    if nav:
        rows.append(nav)
    rows.append([b("🔙 بازگشت", "st:home")])
    await show(app, event, f"🚫 **لیست بلاک** ({fa(total)} نفر)\nبرای حفظ ناشناس‌بودن، هویت‌ها نمایش داده نمی‌شود.", rows)


@router.callback_query(F.data.startswith("st:ub:"))
async def cb_unblock(event: CallbackQuery, app: App, user: dict) -> None:
    other = (event.data or "").split(":")[2]
    if other.isdigit():
        await repo.unblock(app, user["id"], int(other))
    await toast(event, "رفع بلاک شد")
    await cb_blocks_refresh(event, app, user)


async def cb_blocks_refresh(event: CallbackQuery, app: App, user: dict) -> None:
    event.data = "st:bl:0"
    await cb_blocks(event, app, user)


# ---------------------------------------------------------------- راهنما و قوانین
@router.callback_query(F.data == "h:home")
async def cb_help(event: CallbackQuery, app: App) -> None:
    await toast(event)
    buttons = [b(title, f"h:t:{key}") for key, (title, _) in HELP.items()]
    rows = chunk(buttons, 1) + [[b("📜 قوانین", "h:rules"), b("🎧 پشتیبانی", "sp:home")], [b("🏠 منوی اصلی", "m:home")]]
    await show(app, event, "📚 **راهنمای ربات**\n━━━━━━━━━━━━━━\nسوالت درباره چیه؟", rows)


@router.callback_query(F.data.startswith("h:t:"))
async def cb_help_topic(event: CallbackQuery, app: App) -> None:
    await toast(event)
    key = (event.data or "").split(":")[2]
    if key not in HELP:
        return
    title, body = HELP[key]
    extra = app.settings.get("help_extra").strip()
    await show(app, event, f"**{title}**\n━━━━━━━━━━━━━━\n{body}" + (f"\n\n{extra}" if extra else ""),
               [[b("🔙 راهنما", "h:home"), b("🏠 منو", "m:home")]])


@router.callback_query(F.data == "h:rules")
async def cb_rules(event: CallbackQuery, app: App) -> None:
    await toast(event)
    await show(app, event, app.settings.get("rules") or DEFAULT_RULES, [[b("🔙 بازگشت", "st:home"), b("🏠 منو", "m:home")]])


# ---------------------------------------------------------------- پشتیبانی
@router.callback_query(F.data == "sp:home")
async def cb_support(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if not app.settings.on("support_enabled"):
        return await show(app, event, "⏸ پشتیبانی فعلاً غیرفعال است.", [[b("🏠 منو", "m:home")]])
    await repo.set_step(app, user["id"], "")
    open_cnt = await app.db.val("SELECT COUNT(*) FROM tickets WHERE user_id = ? AND status = 'open'", (user["id"],), 0)
    text = ("🎧 **پشتیبانی**\n━━━━━━━━━━━━━━\nمشکل، پیشنهاد یا انتقادی داری؟ پیامت رو بفرست تا مدیریت پاسخ بده."
            + (f"\n\n📨 تیکت باز: {fa(open_cnt)}" if open_cnt else ""))
    rows = [[b("✉️ ارسال پیام به پشتیبانی", "sp:new", SUCCESS)]]
    username = app.settings.get("support_username").strip().lstrip("@")
    if username:
        rows.append([url(f"💬 پیام مستقیم به @{username}", f"https://ble.ir/{username}")])
    rows.append([b("🏠 منوی اصلی", "m:home")])
    await show(app, event, text, rows)


@router.callback_query(F.data == "sp:new")
async def cb_support_new(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "ticket")
    await show(app, event, "✍️ پیامت رو بنویس (متن). شرح کامل مشکل کمک می‌کنه سریع‌تر پاسخ بگیری:",
               [[b("❌ انصراف", "sp:home")]])


@router.message(Step("ticket"), F.text)
async def in_ticket(message: Message, app: App, user: dict) -> None:
    text = (message.text or "").strip()
    recent = await app.db.val("SELECT COUNT(*) FROM tickets WHERE user_id = ? AND created_at > ?", (user["id"], now() - 3600), 0)
    if recent >= 5:
        return await app.send(user["id"], "⏳ تعداد پیام‌های اخیرت زیاد است؛ کمی بعد دوباره امتحان کن.")
    if len(text) < 5:
        return await app.send(user["id"], "پیام خیلی کوتاه است.", [[b("❌ انصراف", "sp:home")]])
    tid = await app.db.execute("INSERT INTO tickets(user_id, text, created_at) VALUES(?,?,?)",
                               (user["id"], text[:2000], now()))
    await repo.set_step(app, user["id"], "")
    await app.send(user["id"], f"✅ پیامت ثبت شد (شماره #{fa(tid)}). به‌زودی پاسخ می‌گیری.",
                   [[b("🏠 منوی اصلی", "m:home")]])
    for admin_id in await app.admin_ids("support"):
        await app.send(admin_id, f"🎧 **تیکت جدید #{tid}**\nاز: {esc(user['name'], 30)} ({user['id']})\n━━━━━━━━━━━━━━\n{text[:1500]}",
                       [[b("↩️ پاسخ", f"a:tk:r:{tid}", PRIMARY)]])
