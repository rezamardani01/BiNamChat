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
"""ارسال/فوروارد همگانی با پیشرفت زنده، لغو و تاریخچه."""
from __future__ import annotations

import asyncio
import logging

from baleropy import F, Router
from baleropy.exceptions import BaleAPIError, BaleNetworkError
from baleropy.types import CallbackQuery, Message

from .. import repo
from ..core import App, parse_step
from ..filters import Step
from ..ui import DANGER, PRIMARY, SUCCESS, b, chunk, pager, show, toast
from ..util import bar, duration, esc, fa, jdate, now
from .common import PER_PAGE, admin_only, back

log = logging.getLogger("binam.broadcast")
router = Router(name="admin_broadcast")

AUDIENCES: dict[str, tuple[str, str, tuple]] = {
    "all": ("👥 همه کاربران", "1=1", ()),
    "active": ("🔥 فعال ۷ روز اخیر", "last_seen > ?", ("D7",)),
    "premium": ("👑 کاربران ویژه", "premium_until > ?", ("NOW",)),
    "free": ("🆓 کاربران عادی", "premium_until <= ?", ("NOW",)),
    "male": ("👨 پسرها", "gender = 'male'", ()),
    "female": ("👩 دخترها", "gender = 'female'", ()),
    "new": ("🆕 تازه‌وارد ۲۴ ساعت", "joined_at > ?", ("D1",)),
    "idle": ("😴 غیرفعال ۳۰ روز", "last_seen < ?", ("D30",)),
}


def _where(key: str) -> tuple[str, tuple]:
    _, cond, raw = AUDIENCES[key]
    params = tuple(now() if p == "NOW" else now() - 7 * 86400 if p == "D7" else now() - 86400 if p == "D1"
                   else now() - 30 * 86400 if p == "D30" else p for p in raw)
    return f"banned = 0 AND bot_blocked = 0 AND ({cond})", params


async def audience_count(app: App, key: str) -> int:
    where, params = _where(key)
    return await app.db.val(f"SELECT COUNT(*) FROM users WHERE {where}", params, 0)


@router.callback_query(F.data == "a:bc")
async def cb_menu(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "")
    running = await app.db.val("SELECT COUNT(*) FROM broadcasts WHERE status = 'running'", default=0)
    text = ("📢 **ارسال همگانی**\n━━━━━━━━━━━━━━\n"
            "چه نوع ارسالی می‌خوای انجام بدی؟\n\n"
            "📨 **ارسال معمولی** — پیام شما بدون نام فرستنده برای کاربران کپی می‌شه.\n"
            "↗️ **فوروارد** — پیام همراه با منبع اصلی‌اش فوروارد می‌شه."
            + (f"\n\n⏳ ارسال در حال اجرا: {fa(running)}" if running else ""))
    await show(app, event, text, [
        [b("📨 ارسال معمولی", "a:bc:m:copy", PRIMARY), b("↗️ فوروارد", "a:bc:m:forward", PRIMARY)],
        [b("📜 تاریخچه ارسال‌ها", "a:bc:h:0")], back()])


@router.callback_query(F.data.startswith("a:bc:m:"))
async def cb_mode_pick(event: CallbackQuery, app: App) -> None:
    mode = (event.data or "").split(":")[3]
    if mode not in ("copy", "forward"):
        return await toast(event)
    await toast(event)
    buttons = [b(f"{title} ({fa(await audience_count(app, key))})", f"a:bc:au:{mode}:{key}")
               for key, (title, *_r) in AUDIENCES.items()]
    label = "📨 ارسال معمولی" if mode == "copy" else "↗️ فوروارد"
    await show(app, event, f"{label}\n━━━━━━━━━━━━━━\nپیام برای چه کسانی ارسال بشه؟\n"
                           "(کاربران مسدود یا بلاک‌کننده ربات حذف می‌شوند)",
               chunk(buttons, 2) + [back("a:bc")])


@router.callback_query(F.data.startswith("a:bc:au:"))
async def cb_audience(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    mode, key = parts[3], parts[4] if len(parts) > 4 else ""
    if key not in AUDIENCES or mode not in ("copy", "forward"):
        return await toast(event)
    await toast(event)
    await repo.set_step(app, user["id"], "a_bc", {"aud": key, "mode": mode})
    kind = "ارسال معمولی" if mode == "copy" else "فوروارد"
    await show(app, event, f"{kind} • {AUDIENCES[key][0]} ({fa(await audience_count(app, key))} نفر)\n\n"
                           "حالا پیامی که می‌خوای ارسال بشه رو بفرست (متن، عکس، ویدیو، فایل، ...):",
               [[b("❌ انصراف", "a:bc", DANGER)]])


@router.message(Step("a_bc"))
async def in_message(message: Message, app: App, user: dict) -> None:
    if not await admin_only(app, message, user["id"], "broadcast"):
        return
    data = parse_step(user["step_data"])
    if "aud" not in data:
        return
    data.update(chat=message.chat.id, mid=message.message_id,
                preview=(message.text or message.caption or f"[{message.content_type}]")[:200])
    await repo.set_step(app, user["id"], "a_bc", data)
    await app.copy(user["id"], message.chat.id, message.message_id)
    await app.send(user["id"], _confirm_text(data, await audience_count(app, data["aud"])), _confirm_rows(data))


def _confirm_text(data: dict, count: int) -> str:
    return (f"👆 پیش‌نمایش پیام\n━━━━━━━━━━━━━━\n🎯 مخاطب: {AUDIENCES[data['aud']][0]}\n👥 تعداد: {fa(count)}\n"
            f"📨 روش: {'کپی (بدون نام فرستنده)' if data['mode'] == 'copy' else 'فوروارد'}\n\nتأیید می‌کنی؟")


def _confirm_rows(data: dict) -> list[list]:
    return [[b("🚀 شروع ارسال", "a:bc:go", SUCCESS)],
            [b("❌ لغو", "a:bc", DANGER)]]


@router.callback_query(F.data == "a:bc:go")
async def cb_go(event: CallbackQuery, app: App, user: dict) -> None:
    data = parse_step(user["step_data"])
    if "chat" not in data or not await admin_only(app, event, user["id"], "broadcast"):
        return await toast(event, "ابتدا پیام را بفرست", True)
    await repo.set_step(app, user["id"], "")
    total = await audience_count(app, data["aud"])
    if not total:
        return await toast(event, "مخاطبی وجود ندارد", True)
    bid = await app.db.execute(
        "INSERT INTO broadcasts(admin_id, audience, mode, preview, src_chat, src_mid, total, status, created_at) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (user["id"], data["aud"], data["mode"], data["preview"], data["chat"], data["mid"], total, "running", now()))
    await app.audit(user["id"], "broadcast", bid, f"{data['aud']} × {total}")
    await toast(event, "🚀 ارسال شروع شد")
    progress = await app.send(user["id"], "⏳ آماده‌سازی...", [[b("⛔️ توقف", f"a:bc:x:{bid}", DANGER)]])
    app.spawn(run_broadcast(app, bid, user["id"], progress))
    await app.delete(user["id"], event.message.message_id if event.message else None)


async def run_broadcast(app: App, bid: int, admin_id: int, progress_mid: int | None) -> None:
    row = await app.db.one("SELECT * FROM broadcasts WHERE id = ?", (bid,))
    if not row:
        return
    where, params = _where(row["audience"])
    ids = [r["id"] for r in await app.db.all(f"SELECT id FROM users WHERE {where} ORDER BY id", params)]
    sem = asyncio.Semaphore(8)
    sent = failed = 0
    last_edit = 0.0
    loop = asyncio.get_running_loop()

    async def one(uid: int) -> bool:
        async with sem:
            try:
                if row["mode"] == "forward":
                    await app.bot.forward_message(uid, row["src_chat"], row["src_mid"])
                    return True
                return bool(await app.copy(uid, row["src_chat"], row["src_mid"]))
            except (BaleAPIError, BaleNetworkError):
                return False

    cancelled = False
    for start in range(0, len(ids), 16):
        if bid in app.broadcast_cancel:
            cancelled = True
            break
        results = await asyncio.gather(*(one(u) for u in ids[start:start + 16]))
        sent += sum(results)
        failed += len(results) - sum(results)
        await asyncio.sleep(0.4)
        if loop.time() - last_edit > 3 and progress_mid:
            last_edit = loop.time()
            await app.db.execute("UPDATE broadcasts SET sent = ?, failed = ? WHERE id = ?", (sent, failed, bid))
            await app.edit(admin_id, progress_mid,
                           f"📢 ارسال در حال انجام...\n{bar(sent + failed, len(ids), 14)} {fa(round((sent + failed) * 100 / len(ids)))}٪\n"
                           f"✅ موفق: {fa(sent)}\n❌ ناموفق: {fa(failed)}\n👥 کل مخاطبان: {fa(len(ids))}",
                           [[b("⛔️ توقف", f"a:bc:x:{bid}", DANGER)]])
    app.broadcast_cancel.discard(bid)
    status = "cancelled" if cancelled else "done"
    await app.db.execute("UPDATE broadcasts SET sent = ?, failed = ?, status = ?, finished_at = ? WHERE id = ?",
                         (sent, failed, status, now(), bid))
    took = duration(now() - row["created_at"])
    text = (f"{'⛔️ ارسال متوقف شد' if cancelled else '✅ ارسال همگانی تمام شد'}\n━━━━━━━━━━━━━━\n"
            f"✅ موفق: {fa(sent)}\n❌ ناموفق: {fa(failed)}\n👥 مخاطب: {fa(len(ids))}\n⏱ زمان: {took}")
    if progress_mid:
        await app.edit(admin_id, progress_mid, text, [[b("🔙 ارسال همگانی", "a:bc")]])
    else:
        await app.send(admin_id, text)


@router.callback_query(F.data.startswith("a:bc:x:"))
async def cb_cancel(event: CallbackQuery, app: App) -> None:
    bid = (event.data or "").split(":")[3]
    if bid.isdigit():
        app.broadcast_cancel.add(int(bid))
    await toast(event, "درخواست توقف ثبت شد")


@router.callback_query(F.data.startswith("a:bc:h:"))
async def cb_history(event: CallbackQuery, app: App) -> None:
    await toast(event)
    page = int((event.data or "a:bc:h:0").split(":")[3])
    total = await app.db.val("SELECT COUNT(*) FROM broadcasts", default=0)
    items = await app.db.all("SELECT * FROM broadcasts ORDER BY id DESC LIMIT ? OFFSET ?", (PER_PAGE, page * PER_PAGE))
    icon = {"done": "✅", "running": "⏳", "cancelled": "⛔️", "interrupted": "⚠️"}
    rows = chunk([b(f"{icon.get(r['status'], '•')} #{r['id']} • {jdate(r['created_at'], 'day')} • {fa(r['sent'])}/{fa(r['total'])}",
                    f"a:bc:v:{r['id']}") for r in items], 1)
    nav = pager("a:bc:h:", page, total, PER_PAGE)
    if nav:
        rows.append(nav)
    rows.append(back("a:bc"))
    await show(app, event, f"📜 **تاریخچه ارسال‌ها** ({fa(total)})", rows)


@router.callback_query(F.data.startswith("a:bc:v:"))
async def cb_view(event: CallbackQuery, app: App) -> None:
    bid = (event.data or "").split(":")[3]
    r = await app.db.one("SELECT * FROM broadcasts WHERE id = ?", (int(bid),)) if bid.isdigit() else None
    if not r:
        return await toast(event, "پیدا نشد", True)
    await toast(event)
    await show(app, event, f"📢 **ارسال #{r['id']}**\n━━━━━━━━━━━━━━\n🎯 {AUDIENCES.get(r['audience'], (r['audience'],))[0]}\n"
                           f"📅 {jdate(r['created_at'], 'full')}\n✅ موفق: {fa(r['sent'])}\n❌ ناموفق: {fa(r['failed'])}\n👥 کل: {fa(r['total'])}\n"
                           f"وضعیت: {r['status']}\n\n📝 {esc(r['preview'], 200)}", [back("a:bc:h:0")])
