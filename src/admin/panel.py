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
"""صفحه اصلی پنل، داشبورد آمار، مانیتور زنده، لاگ‌ها و پشتیبان‌گیری."""
from __future__ import annotations

import asyncio
import re
import tempfile
from pathlib import Path

from baleropy import F, Router
from baleropy.filters import Command
from baleropy.types import CallbackQuery, FSInputFile, Message

from .. import matching, repo
from ..core import App
from ..filters import Step
from ..ui import DANGER, PRIMARY, SUCCESS, b, pager, show, toast
from ..util import bar, day_start, duration, esc, fa, jdate, now, spark
from .common import PER_PAGE, back

router = Router(name="admin_panel")


# ---------------------------------------------------------------- خانه
async def home_view(app: App, uid: int) -> tuple[str, list[list]]:
    perms = await app.perms_of(uid)
    users = await app.db.val("SELECT COUNT(*) FROM users", default=0)
    online = await app.db.val("SELECT COUNT(*) FROM users WHERE last_seen > ?", (now() - 300,), 0)
    chats = await app.db.val("SELECT COUNT(*) FROM chats WHERE status = 'active'", default=0)
    queue = await app.db.val("SELECT COUNT(*) FROM queue", default=0)
    reports = await app.db.val("SELECT COUNT(*) FROM reports WHERE status = 'open'", default=0)
    tickets = await app.db.val("SELECT COUNT(*) FROM tickets WHERE status = 'open'", default=0)
    maint = app.settings.on("maintenance")
    text = ("🛠 **پنل مدیریت بینام**\n━━━━━━━━━━━━━━\n"
            f"👥 کاربران: {fa(users)}\n🟢 آنلاین: {fa(online)}\n"
            f"💬 چت فعال: {fa(chats)}\n🔎 در صف: {fa(queue)}\n"
            f"🚨 گزارش باز: {fa(reports)}\n🎧 تیکت باز: {fa(tickets)}\n"
            f"⏱ آپتایم: {duration(now() - app.started_at)}"
            + ("\n\n🛠 **حالت تعمیر فعال است**" if maint else ""))
    rows: list[list] = []

    def add(perm: str, *buttons) -> None:
        if perm in perms:
            rows.append(list(buttons))

    add("stats", b("📊 آمار و داشبورد", "a:st", PRIMARY), b("📡 مانیتور زنده", "a:lv"))
    add("users", b("👥 کاربران", "a:u", PRIMARY))
    if "reports" in perms:
        rows.append([b(f"🚨 گزارش‌ها ({fa(reports)})" if reports else "🚨 گزارش‌ها", "a:rp:l:0", DANGER if reports else None),
                     b(f"🎧 پشتیبانی ({fa(tickets)})" if tickets else "🎧 پشتیبانی", "a:tk:l:0")] if "support" in perms
                    else [b(f"🚨 گزارش‌ها ({fa(reports)})", "a:rp:l:0")])
    elif "support" in perms:
        rows.append([b(f"🎧 پشتیبانی ({fa(tickets)})", "a:tk:l:0")])
    add("broadcast", b("📢 ارسال همگانی", "a:bc", PRIMARY), b("📣 قفل کانال", "a:ch"))
    add("gifts", b("🎁 کدهای هدیه", "a:gf:l:0"), *( [b("💰 امور مالی", "a:fn")] if "finance" in perms else []))
    if "gifts" not in perms and "finance" in perms:
        rows.append([b("💰 امور مالی", "a:fn")])
    add("settings", b("⚙️ تنظیمات ربات", "a:se", PRIMARY),
        b("🟢 پایان تعمیر" if maint else "🛠 حالت تعمیر", "a:mt", SUCCESS if maint else DANGER))
    add("logs", b("🗂 لاگ‌ها", "a:lg"))
    if uid == app.owner_id:
        rows.append([b("🛡 مدیران", "a:ad"), b("💾 پشتیبان‌گیری", "a:bk")])
    rows.append([b("🔄 بروزرسانی", "a:home"), b("🏠 منوی کاربر", "m:home")])
    return text, rows


@router.message(Command("panel"))
async def cmd_panel(message: Message, app: App, user: dict, is_admin: bool) -> None:
    if not is_admin:
        return
    await repo.set_step(app, user["id"], "")
    text, rows = await home_view(app, user["id"])
    await app.send(user["id"], text, rows)


@router.callback_query(F.data == "a:home")
async def cb_home(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "")
    text, rows = await home_view(app, user["id"])
    await show(app, event, text, rows)


@router.callback_query(F.data == "a:mt")
async def cb_maintenance(event: CallbackQuery, app: App, user: dict) -> None:
    on = await app.settings.toggle("maintenance")
    await app.audit(user["id"], "maintenance", None, "on" if on else "off")
    await toast(event, "حالت تعمیر " + ("فعال شد" if on else "غیرفعال شد"))
    text, rows = await home_view(app, user["id"])
    await show(app, event, text, rows)


# ---------------------------------------------------------------- داشبورد
async def stats_text(app: App) -> str:
    db = app.db
    t0 = day_start()
    total = await db.val("SELECT COUNT(*) FROM users", default=0)
    new_today = await db.val("SELECT COUNT(*) FROM users WHERE joined_at >= ?", (t0,), 0)
    new_7 = await db.val("SELECT COUNT(*) FROM users WHERE joined_at >= ?", (t0 - 6 * 86400,), 0)
    act_24 = await db.val("SELECT COUNT(*) FROM users WHERE last_seen > ?", (now() - 86400,), 0)
    online = await db.val("SELECT COUNT(*) FROM users WHERE last_seen > ?", (now() - 300,), 0)
    prem = await db.val("SELECT COUNT(*) FROM users WHERE premium_until > ?", (now(),), 0)
    banned = await db.val("SELECT COUNT(*) FROM users WHERE banned = 1", default=0)
    gone = await db.val("SELECT COUNT(*) FROM users WHERE bot_blocked = 1", default=0)
    males = await db.val("SELECT COUNT(*) FROM users WHERE gender = 'male'", default=0)
    females = await db.val("SELECT COUNT(*) FROM users WHERE gender = 'female'", default=0)
    chats_now = await db.val("SELECT COUNT(*) FROM chats WHERE status = 'active'", default=0)
    queue = await db.val("SELECT COUNT(*) FROM queue", default=0)
    chats_today = await db.val("SELECT COUNT(*) FROM chats WHERE started_at >= ?", (t0,), 0)
    chats_all = await db.val("SELECT COUNT(*) FROM chats", default=0)
    msgs_today = await db.val("SELECT COALESCE(SUM(a_msgs + b_msgs),0) FROM chats WHERE started_at >= ?", (t0,), 0)
    avg = await db.val("SELECT AVG(ended_at - started_at) FROM chats WHERE status = 'ended' AND started_at >= ?",
                       (t0 - 6 * 86400,), 0)
    anon_today = await db.val("SELECT COUNT(*) FROM anon_messages WHERE created_at >= ?", (t0,), 0)
    anon_all = await db.val("SELECT COUNT(*) FROM anon_messages", default=0)
    coins = await db.val("SELECT COALESCE(SUM(coins),0) FROM users", default=0)
    rev_today = await db.val("SELECT COALESCE(SUM(amount_irr),0) FROM payments WHERE status='paid' AND paid_at >= ?", (t0,), 0)
    rev_30 = await db.val("SELECT COALESCE(SUM(amount_irr),0) FROM payments WHERE status='paid' AND paid_at >= ?",
                          (t0 - 29 * 86400,), 0)
    rev_all = await db.val("SELECT COALESCE(SUM(amount_irr),0) FROM payments WHERE status='paid'", default=0)
    days = []
    for i in range(6, -1, -1):
        s = t0 - i * 86400
        days.append(await db.val("SELECT COUNT(*) FROM users WHERE joined_at >= ? AND joined_at < ?", (s, s + 86400), 0))
    provinces = await db.all("SELECT province, COUNT(*) c FROM users WHERE province IS NOT NULL GROUP BY province ORDER BY c DESC LIMIT 5")
    sexed = max(males + females, 1)
    top = "\n".join(f"  {i + 1}. {esc(r['province'])}: {fa(r['c'])}" for i, r in enumerate(provinces)) or "  —"
    return (
        "📊 **داشبورد آمار**\n━━━━━━━━━━━━━━\n"
        f"👥 کل کاربران: {fa(total)}\n"
        f"🆕 امروز: {fa(new_today)} • ۷ روز اخیر: {fa(new_7)}\n"
        f"📈 {spark(days)}  (ثبت‌نام ۷ روز اخیر)\n"
        f"🟢 آنلاین ۵ دقیقه: {fa(online)} • فعال ۲۴ ساعت: {fa(act_24)}\n"
        f"👑 ویژه: {fa(prem)}\n🚫 مسدود: {fa(banned)}\n🔕 بلاک‌کننده ربات: {fa(gone)}\n\n"
        f"⚧ پسر {bar(males, sexed)} دختر\n"
        f"   {fa(males)} ({fa(round(males * 100 / sexed))}٪) — {fa(females)} ({fa(round(females * 100 / sexed))}٪)\n\n"
        "💬 **چت**\n"
        f"• فعال: {fa(chats_now)} • در صف: {fa(queue)}\n"
        f"• امروز: {fa(chats_today)} • کل: {fa(chats_all)}\n"
        f"• پیام امروز: {fa(msgs_today)} • میانگین مدت: {duration(int(avg or 0))}\n"
        f"• پیام ناشناس امروز: {fa(anon_today)} • کل: {fa(anon_all)}\n\n"
        "💰 **اقتصاد**\n"
        f"• سکه در گردش: {fa(coins)}\n"
        f"• فروش امروز: {fa(rev_today // 10)} تومان\n"
        f"• ۳۰ روز اخیر: {fa(rev_30 // 10)} تومان\n"
        f"• کل: {fa(rev_all // 10)} تومان\n\n"
        f"🗺 **برترین استان‌ها**\n{top}"
    )


@router.callback_query(F.data == "a:st")
async def cb_stats(event: CallbackQuery, app: App) -> None:
    await toast(event)
    await show(app, event, await stats_text(app), [[b("🔄 بروزرسانی", "a:st", PRIMARY)], back()])


# ---------------------------------------------------------------- مانیتور زنده
@router.callback_query(F.data.startswith("a:lv"))
async def cb_live(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    if len(parts) >= 4 and parts[2] == "e" and parts[3].isdigit():
        if not await app.can(user["id"], "users"):
            return await toast(event, "مجوز ندارید", True)
        chat = await matching.end_chat(app, int(parts[3]), None, "admin")
        await app.audit(user["id"], "end_chat", parts[3])
        await toast(event, "گفتگو پایان یافت" if chat else "گفتگو فعال نیست")
    else:
        await toast(event)
    page = int(parts[3]) if len(parts) >= 4 and parts[2] == "p" and parts[3].isdigit() else 0
    total = await app.db.val("SELECT COUNT(*) FROM chats WHERE status = 'active'", default=0)
    queue = await app.db.all("SELECT search_type, COUNT(*) c FROM queue GROUP BY search_type")
    qtxt = " • ".join(f"{ {'random': 'شانسی', 'male': 'پسر', 'female': 'دختر'}.get(r['search_type'], r['search_type']) }: {fa(r['c'])}"
                      for r in queue) or "خالی"
    chats = await app.db.all("SELECT * FROM chats WHERE status = 'active' ORDER BY last_activity DESC LIMIT ? OFFSET ?",
                             (PER_PAGE, page * PER_PAGE))
    lines = [f"📡 **مانیتور زنده**\n━━━━━━━━━━━━━━\n💬 گفتگوی فعال: {fa(total)}\n🔎 صف: {qtxt}\n"]
    rows = []
    for c in chats:
        lines.append(f"#{c['id']} • {c['a']} ↔ {c['b']} • {duration(now() - c['started_at'])} • {fa(c['a_msgs'] + c['b_msgs'])} پیام")
        rows.append([b(f"⛔️ پایان #{c['id']}", f"a:lv:e:{c['id']}")])
    nav = pager("a:lv:p:", page, total, PER_PAGE)
    if nav:
        rows.append(nav)
    rows.append([b("🔄 بروزرسانی", f"a:lv:p:{page}", PRIMARY)])
    rows.append(back())
    lines.append("\n🔒 محتوای گفتگوها برای مدیران قابل مشاهده نیست.")
    await show(app, event, "\n".join(lines), rows)


# ---------------------------------------------------------------- لاگ‌ها
LOG_CATS = [("users", "👥 کاربران جدید"), ("payments", "💰 خریدها و کد هدیه"), ("chats", "💬 اتصال و قطع چت"),
            ("reports", "🚨 گزارش‌ها و تعلیق"), ("admin", "🛠 عملیات مدیران")]


@router.callback_query(F.data == "a:lg")
async def cb_logs(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "")
    ch = app.settings.get("log_channel").strip()
    await show(app, event, "🗂 **لاگ‌ها**\n━━━━━━━━━━━━━━\n"
                           f"📡 کانال لاگ: {ch or 'تنظیم نشده'}\n\nکدام لاگ را ببینیم؟",
               [[b("🧾 عملیات مدیران", "a:lg:a:0"), b("⚠️ خطاهای سیستم", "a:lg:e:0")],
                [b("📡 کانال لاگ و رویدادها", "a:lg:cfg", PRIMARY)], back()])


async def log_cfg_view(app: App) -> tuple[str, list[list]]:
    ch = app.settings.get("log_channel").strip()
    text = ("📡 **کانال لاگ رویدادها**\n━━━━━━━━━━━━━━\n"
            f"{'🟢' if ch else '🔴'} کانال: {ch or 'تنظیم نشده'}\n\n"
            "هر رویدادی که دسته‌اش روشن باشد (خرید، اتصال و قطع چت، گزارش، کاربر جدید، عملیات مدیران) "
            "در همین کانال ثبت می‌شود. ربات باید در کانال ادمین باشد.\n\nدسته‌های لاگ:")
    rows = [[b("📡 تنظیم / تغییر کانال", "a:lg:set", PRIMARY)]]
    if ch:
        rows.append([b("🧪 پیام تست", "a:lg:test"), b("🗑 حذف کانال", "a:lg:off", DANGER)])
    for key, label in LOG_CATS:
        on = app.settings.on(f"log_{key}")
        rows.append([b(f"{'✅' if on else '▫️'} {label}", f"a:lg:lt:{key}", SUCCESS if on else None)])
    rows.append(back("a:lg"))
    return text, rows


@router.callback_query(F.data == "a:lg:cfg")
async def cb_log_cfg(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "")
    await show(app, event, *await log_cfg_view(app))


@router.callback_query(F.data.startswith("a:lg:lt:"))
async def cb_log_toggle(event: CallbackQuery, app: App, user: dict) -> None:
    key = (event.data or "").split(":")[3]
    if key in {k for k, _ in LOG_CATS}:
        await app.settings.toggle(f"log_{key}")
    await toast(event)
    await show(app, event, *await log_cfg_view(app))


@router.callback_query(F.data == "a:lg:set")
async def cb_log_set(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "a_logch")
    await show(app, event, "📡 یکی از این‌ها را بفرست:\n\n• یک پیام فوروارد‌شده از کانال/گروه\n• شناسه عددی (مثل -100123...)\n"
                           "• @یوزرنیم کانال\n\n⚠️ ابتدا ربات را در آن کانال ادمین کن.",
               [[b("❌ انصراف", "a:lg:cfg", DANGER)]])


@router.callback_query(F.data == "a:lg:off")
async def cb_log_off(event: CallbackQuery, app: App, user: dict) -> None:
    await app.settings.set("log_channel", "")
    await app.audit(user["id"], "log_channel", None, "removed")
    await toast(event, "حذف شد")
    await show(app, event, *await log_cfg_view(app))


@router.callback_query(F.data == "a:lg:test")
async def cb_log_test(event: CallbackQuery, app: App) -> None:
    await app.event("🧪 پیام تست کانال لاگ\nاگر این پیام را می‌بینی، همه‌چیز درست است.", "admin")
    await toast(event, "پیام تست ارسال شد (اگر دسته «عملیات مدیران» روشن باشد)", True)


@router.message(Step("a_logch"))
async def in_log_channel(message: Message, app: App, user: dict) -> None:
    if not await app.can(user["id"], "logs"):
        return
    target: int | str | None = None
    if message.forward_from_chat:
        target = message.forward_from_chat.id
    elif message.text:
        text = message.text.strip()
        if re.fullmatch(r"-?\d{5,20}", text):
            target = int(text)
        else:
            m = re.search(r"(?:ble\.ir/|@)([A-Za-z0-9_]{3,})", text)
            target = f"@{m.group(1)}" if m else None
    if target is None:
        return await app.send(user["id"], "❌ شناسه نامعتبر است.", [[b("❌ انصراف", "a:lg:cfg")]])
    try:
        sent = await app.bot.send_message(target, "✅ این چت به‌عنوان کانال لاگ ربات بینام تنظیم شد.")
    except Exception as exc:  # noqa: BLE001
        return await app.send(user["id"], f"❌ ارسال به این چت ممکن نشد: {esc(str(exc), 120)}\nمطمئن شو ربات ادمین است.",
                              [[b("❌ انصراف", "a:lg:cfg")]])
    await app.settings.set("log_channel", str(sent.chat.id))
    await repo.set_step(app, user["id"], "")
    await app.audit(user["id"], "log_channel", sent.chat.id)
    text, rows = await log_cfg_view(app)
    await app.send(user["id"], "✅ کانال لاگ ثبت شد.\n\n" + text, rows)




@router.callback_query(F.data.startswith("a:lg:"))
async def cb_log_pages(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    if len(parts) < 4:
        return await toast(event)
    kind, page = parts[2], int(parts[3]) if parts[3].isdigit() else 0
    if kind == "c":  # پاک‌سازی خطاها
        await app.db.execute("DELETE FROM errors")
        await app.audit(user["id"], "clear_errors")
        await toast(event, "پاک شد")
        kind, page = "e", 0
    await toast(event)
    if kind == "a":
        total = await app.db.val("SELECT COUNT(*) FROM audit", default=0)
        items = await app.db.all("SELECT * FROM audit ORDER BY id DESC LIMIT ? OFFSET ?", (10, page * 10))
        body = "\n".join(f"• {jdate(i['created_at'], 'full')} — {i['admin_id']} — {i['action']}"
                         f"{' → ' + i['target'] if i['target'] else ''}{' (' + esc(i['details'], 60) + ')' if i['details'] else ''}"
                         for i in items) or "خالی"
        title = "🧾 **عملیات مدیران**"
        extra = []
    else:
        total = await app.db.val("SELECT COUNT(*) FROM errors", default=0)
        items = await app.db.all("SELECT * FROM errors ORDER BY id DESC LIMIT ? OFFSET ?", (8, page * 8))
        body = "\n\n".join(f"{jdate(i['created_at'], 'full')} • {i['source']}\n{esc(i['message'], 160)}" for i in items) or "✅ خالی"
        title = "⚠️ **خطاهای سیستم**"
        extra = [[b("🗑 پاک‌سازی", "a:lg:c:0", DANGER)]] if total else []
    rows = extra
    nav = pager(f"a:lg:{kind}:", page, total, 10 if kind == "a" else 8)
    if nav:
        rows.append(nav)
    rows.append(back("a:lg"))
    await show(app, event, f"{title} ({fa(total)})\n━━━━━━━━━━━━━━\n{body}", rows)


# ---------------------------------------------------------------- پشتیبان‌گیری (مالک)
@router.callback_query(F.data == "a:bk")
async def cb_backup_menu(event: CallbackQuery, app: App) -> None:
    await toast(event)
    await show(app, event, "💾 **پشتیبان‌گیری**\n━━━━━━━━━━━━━━\nفایل دیتابیس یا خروجی کاربران را دریافت کن.",
               [[b("🗄 دریافت دیتابیس (SQLite)", "a:bk:db", PRIMARY)], [b("📄 خروجی کاربران (CSV)", "a:bk:csv")], back()])


@router.callback_query(F.data.in_({"a:bk:db", "a:bk:csv"}))
async def cb_backup(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event, "در حال آماده‌سازی...")
    stamp = jdate(now(), "short").replace("/", "-")
    with tempfile.TemporaryDirectory() as tmp:
        if event.data == "a:bk:db":
            path = Path(tmp) / f"binam-{stamp}.db"
            await app.db.backup_to(path)
            caption = "🗄 پشتیبان دیتابیس بینام"
        else:
            path = Path(tmp) / f"users-{stamp}.csv"
            rows = await app.db.all("SELECT id, name, username, gender, age, province, city, coins, premium_until, joined_at, last_seen FROM users")
            import csv
            with open(path, "w", newline="", encoding="utf-8-sig") as fh:
                writer = csv.writer(fh)
                writer.writerow(["id", "name", "username", "gender", "age", "province", "city", "coins", "premium_until", "joined_at", "last_seen"])
                for r in rows:
                    writer.writerow(list(r.values()))
            caption = f"📄 خروجی {len(rows)} کاربر"
        await app.bot.send_document(user["id"], FSInputFile(path), caption)
    await app.audit(user["id"], "backup", event.data)
    await asyncio.sleep(0)
