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
"""گزارش‌های کاربران و تیکت‌های پشتیبانی."""
from __future__ import annotations

from baleropy import F, Router
from baleropy.types import CallbackQuery, Message

from .. import matching, repo
from ..core import App
from ..filters import Step
from ..ui import DANGER, PRIMARY, SUCCESS, b, chunk, pager, show, toast
from ..util import esc, fa, jdate, now
from .common import PER_PAGE, admin_only, back, uname
from .users import do_ban

router = Router(name="admin_reports")

REASON_TEXT = {"harassment": "😠 توهین یا مزاحمت", "inappropriate": "🔞 محتوای نامناسب", "deception": "🎭 فریب یا جعل هویت",
               "spam": "📨 تبلیغ یا هرزنامه", "other": "❔ مورد دیگر"}
ACTIONS = {"dismiss": "❎ رد گزارش", "warn": "⚠️ اخطار", "susp": "⏳ تعلیق خودکار", "ban": "🚫 مسدودسازی"}


# ---------------------------------------------------------------- گزارش‌ها
@router.callback_query(F.data.startswith("a:rp:l:"))
async def cb_list(event: CallbackQuery, app: App) -> None:
    await toast(event)
    page = int((event.data or "a:rp:l:0").split(":")[3])
    total = await app.db.val("SELECT COUNT(*) FROM reports WHERE status = 'open'", default=0)
    items = await app.db.all("SELECT * FROM reports WHERE status = 'open' ORDER BY id DESC LIMIT ? OFFSET ?",
                             (PER_PAGE, page * PER_PAGE))
    rows = chunk([b(f"{'💬' if r['source'] == 'random' else '📩'} #{r['id']} • کاربر {r['reported_id']} • {jdate(r['created_at'], 'day')}",
                    f"a:rp:v:{r['id']}") for r in items], 1)
    nav = pager("a:rp:l:", page, total, PER_PAGE)
    if nav:
        rows.append(nav)
    done = await app.db.val("SELECT COUNT(*) FROM reports WHERE status != 'open'", default=0)
    rows.append([b(f"📁 بررسی‌شده‌ها ({fa(done)})", "a:rp:d:0")])
    rows.append(back())
    await show(app, event, f"🚨 **گزارش‌های باز** ({fa(total)})\n━━━━━━━━━━━━━━" + ("" if items else "\n✅ گزارش بازی نیست."), rows)


@router.callback_query(F.data.startswith("a:rp:d:"))
async def cb_done(event: CallbackQuery, app: App) -> None:
    await toast(event)
    page = int((event.data or "a:rp:d:0").split(":")[3])
    total = await app.db.val("SELECT COUNT(*) FROM reports WHERE status != 'open'", default=0)
    items = await app.db.all("SELECT * FROM reports WHERE status != 'open' ORDER BY handled_at DESC LIMIT ? OFFSET ?",
                             (PER_PAGE, page * PER_PAGE))
    rows = chunk([b(f"#{r['id']} • {ACTIONS.get(r['action'], r['action'])} • {r['reported_id']}", f"a:rp:v:{r['id']}") for r in items], 1)
    nav = pager("a:rp:d:", page, total, PER_PAGE)
    if nav:
        rows.append(nav)
    rows.append(back("a:rp:l:0"))
    await show(app, event, f"📁 **گزارش‌های بررسی‌شده** ({fa(total)})", rows)


@router.callback_query(F.data.startswith("a:rp:v:"))
async def cb_view(event: CallbackQuery, app: App) -> None:
    rid = (event.data or "").split(":")[3]
    r = await app.db.one("SELECT * FROM reports WHERE id = ?", (int(rid),)) if rid.isdigit() else None
    if not r:
        return await toast(event, "گزارش پیدا نشد", True)
    await toast(event)
    reported = await repo.get_user(app, r["reported_id"])
    reporter = await repo.get_user(app, r["reporter_id"])
    against = await app.db.val("SELECT COUNT(DISTINCT reporter_id) FROM reports WHERE reported_id = ?", (r["reported_id"],), 0)
    src = {"anon": "پیام ناشناس", "friend": "چت دوستان"}.get(r["source"], "چت تصادفی")
    text = (f"🚨 **گزارش #{r['id']}** ({'باز' if r['status'] == 'open' else 'بررسی‌شده'})\n━━━━━━━━━━━━━━\n"
            f"📂 منبع: {src}\n📝 دلیل: {REASON_TEXT.get(r['reason'], esc(r['reason']))}\n📅 {jdate(r['created_at'], 'full')}\n\n"
            f"👤 گزارش‌دهنده: {uname(reporter)} ({r['reporter_id']})\n"
            f"⚠️ گزارش‌شده: {uname(reported)} ({r['reported_id']})\n"
            f"🔢 تعداد گزارش‌دهندگان متفاوت علیه او: {fa(against)}")
    if r["status"] != "open":
        text += f"\n\n✅ اقدام: {ACTIONS.get(r['action'], r['action'])} توسط {r['handled_by']}"
    rows: list[list] = []
    if r["status"] == "open":
        rows.append([b(ACTIONS["warn"], f"a:rp:a:{r['id']}:warn"), b(ACTIONS["susp"], f"a:rp:a:{r['id']}:susp", DANGER)])
        rows.append([b(ACTIONS["ban"], f"a:rp:a:{r['id']}:ban", DANGER), b(ACTIONS["dismiss"], f"a:rp:a:{r['id']}:dismiss")])
    rows.append([b("👤 کارت گزارش‌شده", f"a:u:v:{r['reported_id']}", PRIMARY)])
    rows.append(back("a:rp:l:0"))
    await show(app, event, text, rows)


@router.callback_query(F.data.startswith("a:rp:a:"))
async def cb_action(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    rid, action = parts[3], parts[4]
    r = await app.db.one("SELECT * FROM reports WHERE id = ? AND status = 'open'", (int(rid),)) if rid.isdigit() else None
    if not r or action not in ACTIONS:
        return await toast(event, "این گزارش قبلاً بررسی شده", True)
    perm = "reports" if action in ("dismiss", "warn") else "ban"
    if not await admin_only(app, event, user["id"], perm):
        return
    target = r["reported_id"]
    if action != "dismiss" and (target == app.owner_id or await app.is_admin(target)):
        return await toast(event, "روی مدیران قابل اجرا نیست", True)
    if action == "warn":
        t = await repo.get_user(app, target)
        await repo.update_user(app, target, warns=(t["warns"] if t else 0) + 1)
        await app.send(target, "⚠️ **اخطار از مدیریت**\nرفتار شما مورد گزارش قرار گرفته است. در صورت تکرار حساب شما مسدود می‌شود.")
    elif action == "susp":
        hours = app.settings.int("suspend_hours")
        await repo.update_user(app, target, suspended_until=now() + hours * 3600)
        active = await matching.active_chat(app, target)
        if active:
            await matching.end_chat(app, active["id"], None, "admin")
        await matching.dequeue(app, target)
        await app.send(target, f"⏳ حساب شما به‌دلیل گزارش تخلف برای {fa(hours)} ساعت تعلیق شد.")
    elif action == "ban":
        await do_ban(app, user["id"], target, f"گزارش #{r['id']}")
    await app.db.execute("UPDATE reports SET status = 'done', action = ?, handled_by = ?, handled_at = ? WHERE id = ?",
                         (action, user["id"], now(), r["id"]))
    await app.audit(user["id"], f"report_{action}", target, f"#{r['id']}")
    await app.send(r["reporter_id"], f"✅ گزارش #{r['id']} شما بررسی شد و اقدام لازم انجام شد. سپاس از همکاری‌ت!")
    await toast(event, "انجام شد")
    event.data = "a:rp:l:0"
    await cb_list(event, app)


# ---------------------------------------------------------------- تیکت‌ها
@router.callback_query(F.data.startswith("a:tk:l:"))
async def tk_list(event: CallbackQuery, app: App) -> None:
    await toast(event)
    page = int((event.data or "a:tk:l:0").split(":")[3])
    total = await app.db.val("SELECT COUNT(*) FROM tickets WHERE status = 'open'", default=0)
    items = await app.db.all("SELECT * FROM tickets WHERE status = 'open' ORDER BY id DESC LIMIT ? OFFSET ?",
                             (PER_PAGE, page * PER_PAGE))
    rows = chunk([b(f"#{t['id']} • {t['user_id']} • {esc(t['text'], 24)}", f"a:tk:v:{t['id']}") for t in items], 1)
    nav = pager("a:tk:l:", page, total, PER_PAGE)
    if nav:
        rows.append(nav)
    rows.append([b("📁 پاسخ‌داده‌شده‌ها", "a:tk:d:0")])
    rows.append(back())
    await show(app, event, f"🎧 **تیکت‌های باز** ({fa(total)})" + ("" if items else "\n✅ تیکت بازی نیست."), rows)


@router.callback_query(F.data.startswith("a:tk:d:"))
async def tk_done(event: CallbackQuery, app: App) -> None:
    await toast(event)
    page = int((event.data or "a:tk:d:0").split(":")[3])
    total = await app.db.val("SELECT COUNT(*) FROM tickets WHERE status != 'open'", default=0)
    items = await app.db.all("SELECT * FROM tickets WHERE status != 'open' ORDER BY id DESC LIMIT ? OFFSET ?",
                             (PER_PAGE, page * PER_PAGE))
    rows = chunk([b(f"#{t['id']} • {t['user_id']} • {esc(t['text'], 24)}", f"a:tk:v:{t['id']}") for t in items], 1)
    nav = pager("a:tk:d:", page, total, PER_PAGE)
    if nav:
        rows.append(nav)
    rows.append(back("a:tk:l:0"))
    await show(app, event, f"📁 **تیکت‌های بسته** ({fa(total)})", rows)


@router.callback_query(F.data.startswith("a:tk:v:"))
async def tk_view(event: CallbackQuery, app: App) -> None:
    tid = (event.data or "").split(":")[3]
    t = await app.db.one("SELECT * FROM tickets WHERE id = ?", (int(tid),)) if tid.isdigit() else None
    if not t:
        return await toast(event, "تیکت پیدا نشد", True)
    await toast(event)
    u = await repo.get_user(app, t["user_id"])
    text = (f"🎧 **تیکت #{t['id']}**\n━━━━━━━━━━━━━━\n👤 {uname(u)} ({t['user_id']})\n📅 {jdate(t['created_at'], 'full')}\n\n{t['text']}")
    if t["answer"]:
        text += f"\n\n━━━━━━━━━━━━━━\n✅ پاسخ ({t['answered_by']}):\n{t['answer']}"
    rows = []
    if t["status"] == "open":
        rows.append([b("↩️ پاسخ", f"a:tk:r:{t['id']}", SUCCESS), b("🗄 بستن بدون پاسخ", f"a:tk:c:{t['id']}")])
    rows.append([b("👤 کاربر", f"a:u:v:{t['user_id']}", PRIMARY)])
    rows.append(back("a:tk:l:0"))
    await show(app, event, text, rows)


@router.callback_query(F.data.startswith("a:tk:c:"))
async def tk_close(event: CallbackQuery, app: App, user: dict) -> None:
    tid = (event.data or "").split(":")[3]
    if tid.isdigit():
        await app.db.execute("UPDATE tickets SET status = 'closed', answered_by = ?, answered_at = ? WHERE id = ? AND status = 'open'",
                             (user["id"], now(), int(tid)))
    await toast(event, "بسته شد")
    event.data = "a:tk:l:0"
    await tk_list(event, app)


@router.callback_query(F.data.startswith("a:tk:r:"))
async def tk_reply(event: CallbackQuery, app: App, user: dict) -> None:
    tid = (event.data or "").split(":")[3]
    t = await app.db.one("SELECT * FROM tickets WHERE id = ? AND status = 'open'", (int(tid),)) if tid.isdigit() else None
    if not t:
        return await toast(event, "این تیکت قبلاً پاسخ داده شده", True)
    await toast(event)
    await repo.set_step(app, user["id"], f"a_tkr:{t['id']}")
    await app.send(user["id"], f"↩️ پاسخ تیکت #{t['id']} را بنویس:", [[b("❌ انصراف", f"a:tk:v:{t['id']}")]])


@router.message(Step("a_tkr"), F.text)
async def tk_in_reply(message: Message, app: App, user: dict, step_arg: str) -> None:
    if not await admin_only(app, message, user["id"], "support") or not step_arg.isdigit():
        return
    t = await app.db.one("SELECT * FROM tickets WHERE id = ? AND status = 'open'", (int(step_arg),))
    await repo.set_step(app, user["id"], "")
    if not t:
        return await app.send(user["id"], "این تیکت دیگر باز نیست.")
    answer = (message.text or "").strip()[:3000]
    await app.db.execute("UPDATE tickets SET status = 'answered', answer = ?, answered_by = ?, answered_at = ? WHERE id = ?",
                         (answer, user["id"], now(), t["id"]))
    await app.audit(user["id"], "ticket_reply", t["user_id"], f"#{t['id']}")
    sent = await app.send(t["user_id"], f"🎧 **پاسخ پشتیبانی** (تیکت #{t['id']})\n━━━━━━━━━━━━━━\n{answer}",
                          [[b("✉️ پیام جدید", "sp:new"), b("🏠 منو", "m:home")]])
    await app.send(user["id"], "✅ پاسخ ارسال شد." if sent else "⚠️ ثبت شد ولی کاربر ربات را بلاک کرده است.",
                   [[b("🎧 تیکت‌ها", "a:tk:l:0")]])
