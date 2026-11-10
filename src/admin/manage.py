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
"""قفل کانال‌ها و مدیریت مدیران (مجوزها)."""
from __future__ import annotations

import re

from baleropy import F, Router
from baleropy.exceptions import BaleAPIError, BaleNetworkError
from baleropy.types import CallbackQuery, Message

from .. import repo
from ..core import ALL_PERMS, App, parse_step
from ..filters import Step
from ..ui import DANGER, PRIMARY, SUCCESS, b, chunk, show, toast
from ..util import bar, day_start, duration, esc, fa, jdate, now, parse_int
from .common import admin_only, back, uname

router = Router(name="admin_manage")
DEFAULT_ADMIN_PERMS = ["stats", "users", "reports", "support"]


# ---------------------------------------------------------------- کانال‌ها
STATUS_ICON = {"active": "🟢", "paused": "⏸", "done": "✅"}
STATUS_TEXT = {"active": "فعال", "paused": "متوقف", "done": "تکمیل‌شده"}


def pct(c: dict) -> int:
    return min(100, round(c["joined"] * 100 / c["target"])) if c["target"] else 0


def channel_button(c: dict) -> str:
    name = esc(c["title"], 22) or c["chat_id"]
    if c["kind"] == "sponsor":
        return f"🎯 {name} • {fa(c['joined'])}/{fa(c['target'])} • {fa(pct(c))}٪"
    return f"{'🔒' if c['status'] != 'paused' else '⏸'} {name} • عادی"


@router.callback_query(F.data == "a:ch")
async def cb_channels(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "")
    items = await app.db.all("SELECT * FROM channels ORDER BY status = 'done', added_at")
    active = sum(1 for c in items if c["status"] == "active")
    sponsors = [c for c in items if c["kind"] == "sponsor" and c["status"] == "active"]
    done = sum(1 for c in items if c["status"] == "done")
    rows = [[b(channel_button(c), f"a:ch:v:{c['chat_id']}", PRIMARY if c["kind"] == "sponsor" else None)] for c in items]
    rows.append([b("🔒 افزودن عادی", "a:ch:add:normal", SUCCESS), b("🎯 افزودن اسپانسری", "a:ch:add:sponsor", PRIMARY)])
    rows.append([b(("🟢 قفل کلی روشن" if app.settings.on("force_join") else "🔴 قفل کلی خاموش") + " (تغییر)", "a:ch:tg")])
    if items:
        rows.append([b("🔍 تست عضویت خودم", "a:ch:me")])
    rows.append(back())
    total_goal = sum(c["target"] for c in sponsors)
    total_joined = sum(c["joined"] for c in sponsors)
    lines = ["📣 **مرکز قفل کانال‌ها**", "━━━━━━━━━━━━━━",
             f"{'🟢' if app.settings.on('force_join') else '🔴'} قفل کلی: {'روشن' if app.settings.on('force_join') else 'خاموش'}",
             f"📡 کانال فعال: {fa(active)}",
             f"🎯 کمپین اسپانسری فعال: {fa(len(sponsors))}",
             f"✅ کمپین تکمیل‌شده: {fa(done)}"]
    if sponsors:
        lines += [f"👥 جذب کل کمپین‌های فعال: {fa(total_joined)} از {fa(total_goal)}"]
    lines += ["", "روی هر کانال بزن تا پنل مدیریتش باز شود.",
              "🔒 عادی: دائمی تا زمانی که خودت برداری.",
              "🎯 اسپانسری: با رسیدن به عدد هدف خودکار برداشته می‌شود."]
    if not items:
        lines += ["", "هنوز کانالی ثبت نشده."]
    await show(app, event, "\n".join(lines), rows)


async def _channel(app: App, chat_id: str) -> dict | None:
    return await app.db.one("SELECT * FROM channels WHERE chat_id = ?", (chat_id,))


async def detail_view(app: App, c: dict) -> tuple[str, list[list]]:
    sponsor = c["kind"] == "sponsor"
    name = esc(c["title"], 40) or c["chat_id"]
    members = None
    try:
        cid: int | str = int(c["chat_id"])
    except ValueError:
        cid = c["chat_id"]
    try:
        members = await app.bot.get_chat_members_count(cid)
    except (BaleAPIError, BaleNetworkError):
        pass
    lines = [f"{'🎯' if sponsor else '🔒'} **{name}**", "━━━━━━━━━━━━━━",
             f"{STATUS_ICON[c['status']]} وضعیت: {STATUS_TEXT[c['status']]}",
             f"📂 نوع: {'اسپانسری' if sponsor else 'عضویت اجباری عادی'}",
             f"🆔 شناسه: {c['chat_id']}",
             f"🔗 لینک: {c['link'] or '—'}"]
    if members is not None:
        lines.append(f"👥 اعضای کانال: {fa(members)}")
    lines.append(f"📅 شروع: {jdate(c['added_at'])} - {jdate(c['added_at'], 'time')}")
    if sponsor:
        t0 = day_start()
        seen = await app.db.val("SELECT COUNT(*) FROM sponsor_seen WHERE chat_id = ?", (c["chat_id"],), 0)
        today = await app.db.val("SELECT COUNT(*) FROM sponsor_seen WHERE chat_id = ? AND joined_at >= ?", (c["chat_id"], t0), 0)
        hour = await app.db.val("SELECT COUNT(*) FROM sponsor_seen WHERE chat_id = ? AND joined_at >= ?",
                                (c["chat_id"], now() - 3600), 0)
        end = c["finished_at"] or now()
        elapsed = max(1, end - c["added_at"])
        rate = c["joined"] * 3600 / elapsed if elapsed > 600 else None
        remaining = max(0, c["target"] - c["joined"])
        lines += ["━━━━━━━━━━━━━━", "📊 **پیشرفت لحظه‌ای**",
                  f"👥 جذب‌شده: {fa(c['joined'])} از {fa(c['target'])}",
                  f"{bar(c['joined'], c['target'], 14)} {fa(pct(c))}٪",
                  f"⏳ باقی‌مانده: {fa(remaining)} نفر",
                  f"📈 امروز: {fa(today)} نفر",
                  f"🕐 یک ساعت اخیر: {fa(hour)} نفر"]
        if rate is not None:
            lines.append(f"⚡️ سرعت میانگین: {fa(round(rate, 1))} نفر در ساعت")
            if c["status"] == "active" and remaining and rate > 0:
                lines.append(f"🏁 زمان تقریبی تکمیل: {duration(int(remaining / rate * 3600))} دیگر")
        if seen:
            converted = await app.db.val("SELECT COUNT(*) FROM sponsor_seen WHERE chat_id = ? AND joined_at IS NOT NULL", (c["chat_id"],), 0)
            lines.append(f"🎯 نرخ تبدیل: {fa(min(100, round(converted * 100 / seen)))}٪ از {fa(seen)} نفری که درخواست دیدند")
        if c["finished_at"]:
            lines.append(f"✅ تکمیل در: {jdate(c['finished_at'])} - {jdate(c['finished_at'], 'time')}")
    cid_s = c["chat_id"]
    rows: list[list] = []
    if sponsor:
        rows.append([b("➕50", f"a:ch:x:{cid_s}:t50", SUCCESS), b("➕100", f"a:ch:x:{cid_s}:t100", SUCCESS),
                     b("➕500", f"a:ch:x:{cid_s}:t500", SUCCESS)])
        rows.append([b("🎯 تغییر عدد هدف", f"a:ch:x:{cid_s}:tset", PRIMARY)])
    if c["status"] == "active":
        rows.append([b("⏸ توقف موقت", f"a:ch:x:{cid_s}:pause")])
    elif c["status"] == "paused":
        rows.append([b("▶️ ادامه", f"a:ch:x:{cid_s}:resume", SUCCESS)])
    if sponsor and c["status"] != "done":
        rows.append([b("✅ پایان دستی کمپین", f"a:ch:x:{cid_s}:finish"), b("🔄 صفر کردن شمارنده", f"a:ch:x:{cid_s}:reset")])
    if sponsor and c["status"] == "done":
        rows.append([b("♻️ شروع کمپین جدید", f"a:ch:x:{cid_s}:restart", SUCCESS)])
    rows.append([b("✏️ نام", f"a:ch:x:{cid_s}:ttl"), b("🔗 لینک", f"a:ch:x:{cid_s}:lnk"), b("🩺 دسترسی ربات", f"a:ch:x:{cid_s}:chk")])
    rows.append([b("🔁 تبدیل به عادی" if sponsor else "🔁 تبدیل به اسپانسری", f"a:ch:x:{cid_s}:{'tonormal' if sponsor else 'tosp'}")])
    rows.append([b("🗑 حذف", f"a:ch:x:{cid_s}:del", DANGER), b("🔄 بروزرسانی", f"a:ch:v:{cid_s}", PRIMARY)])
    rows.append(back("a:ch"))
    return "\n".join(lines), rows


@router.callback_query(F.data.startswith("a:ch:v:"))
async def cb_view(event: CallbackQuery, app: App) -> None:
    c = await _channel(app, (event.data or "").split(":", 3)[3])
    if not c:
        return await toast(event, "کانال پیدا نشد", True)
    await toast(event)
    await show(app, event, *await detail_view(app, c))


@router.callback_query(F.data.startswith("a:ch:x:"))
async def cb_op(event: CallbackQuery, app: App, user: dict) -> None:
    _, _, _, rest = (event.data or "").split(":", 3)
    chat_id, _, op = rest.rpartition(":")
    c = await _channel(app, chat_id)
    if not c:
        return await toast(event, "کانال پیدا نشد", True)
    uid = user["id"]
    notice = ""

    async def ask(field: str, prompt: str, data: dict | None = None) -> None:
        await repo.set_step(app, uid, f"a_chedit:{chat_id}:{field}", data)
        await show(app, event, prompt, [[b("❌ انصراف", f"a:ch:v:{chat_id}", DANGER)]])

    if op in ("t50", "t100", "t500") and c["kind"] == "sponsor":
        add = int(op[1:])
        await app.db.execute("UPDATE channels SET target = target + ?, status = CASE WHEN status = 'done' THEN 'active' ELSE status END, "
                             "finished_at = NULL WHERE chat_id = ?", (add, chat_id))
        await app.audit(uid, "sponsor_target", chat_id, f"+{add}")
        notice = f"هدف {fa(add)} نفر افزایش یافت"
    elif op == "tset":
        await toast(event)
        return await ask("target", f"🎯 عدد هدف جدید را بفرست (الان {fa(c['target'])} و جذب‌شده {fa(c['joined'])}):")
    elif op == "ttl":
        await toast(event)
        return await ask("title", "✏️ نام جدید کانال را بفرست (فقط برای نمایش به کاربر):")
    elif op == "lnk":
        await toast(event)
        return await ask("link", "🔗 لینک جدید عضویت کانال را بفرست (با http شروع شود):")
    elif op == "tosp":
        await toast(event)
        return await ask("tosp", "🎯 چند نفر باید از طریق ربات عضو این کانال بشن؟ (عدد بفرست):")
    elif op == "restart":
        await toast(event)
        return await ask("restart", "♻️ عدد هدف کمپین جدید را بفرست (شمارنده صفر می‌شود):")
    elif op == "tonormal":
        await app.db.execute("UPDATE channels SET kind = 'normal', status = 'active', target = 0, joined = 0, finished_at = NULL "
                             "WHERE chat_id = ?", (chat_id,))
        await app.db.execute("DELETE FROM sponsor_seen WHERE chat_id = ?", (chat_id,))
        notice = "به عضویت عادی تبدیل شد"
    elif op == "pause":
        await app.db.execute("UPDATE channels SET status = 'paused' WHERE chat_id = ? AND status = 'active'", (chat_id,))
        notice = "متوقف شد؛ دیگر از کاربران عضویت نمی‌خواهد"
    elif op == "resume":
        await app.db.execute("UPDATE channels SET status = 'active' WHERE chat_id = ? AND status = 'paused'", (chat_id,))
        notice = "دوباره فعال شد"
    elif op == "finish" and c["kind"] == "sponsor":
        await app.db.execute("UPDATE channels SET status = 'done', finished_at = ? WHERE chat_id = ?", (now(), chat_id))
        notice = "کمپین پایان یافت و قفل برداشته شد"
    elif op == "reset" and c["kind"] == "sponsor":
        await app.db.execute("UPDATE channels SET joined = 0, added_at = ?, status = 'active', finished_at = NULL WHERE chat_id = ?",
                             (now(), chat_id))
        await app.db.execute("DELETE FROM sponsor_seen WHERE chat_id = ?", (chat_id,))
        notice = "شمارنده صفر شد"
    elif op == "chk":
        try:
            cid: int | str = int(chat_id)
        except ValueError:
            cid = chat_id
        try:
            member = await app.bot.get_chat_member(cid, app.bot.id)
            text = "✅ ربات ادمین است" if member.is_admin else f"❌ ربات ادمین نیست (وضعیت: {member.status})"
        except (BaleAPIError, BaleNetworkError) as exc:
            text = f"❌ خطا: {esc(str(exc), 120)}"
        return await toast(event, text[:190], True)
    elif op == "del":
        await toast(event)
        return await show(app, event, f"🗑 حذف «{esc(c['title'], 40) or chat_id}»؟\nاین کار قفل و آمار این کانال را برای همیشه پاک می‌کند.",
                          [[b("✅ بله، حذف شود", f"a:ch:x:{chat_id}:delok", DANGER), b("↩️ انصراف", f"a:ch:v:{chat_id}")]])
    elif op == "delok":
        await app.db.execute("DELETE FROM channels WHERE chat_id = ?", (chat_id,))
        await app.db.execute("DELETE FROM sponsor_seen WHERE chat_id = ?", (chat_id,))
        await app.audit(uid, "channel_remove", chat_id)
        await toast(event, "حذف شد")
        return await cb_channels(event, app, user)
    else:
        return await toast(event)
    await app.audit(uid, f"channel_{op}", chat_id)
    await toast(event, notice)
    fresh = await _channel(app, chat_id)
    if fresh:
        await show(app, event, *await detail_view(app, fresh))


@router.message(Step("a_chedit"))
async def in_chedit(message: Message, app: App, user: dict, step_arg: str) -> None:
    if not await admin_only(app, message, user["id"], "channels"):
        return
    chat_id, _, field = step_arg.rpartition(":")
    c = await _channel(app, chat_id)
    if not c or not message.text:
        await repo.set_step(app, user["id"], "")
        return await app.send(user["id"], "کانال پیدا نشد.", [[b("📣 قفل کانال‌ها", "a:ch")]])
    text = message.text.strip()
    if field in ("target", "tosp", "restart"):
        number = parse_int(text)
        if number is None or not 1 <= number <= 1_000_000:
            return await app.send(user["id"], "❌ یک عدد بین ۱ تا ۱٬۰۰۰٬۰۰۰ بفرست.", [[b("❌ انصراف", f"a:ch:v:{chat_id}")]])
        if field == "target":
            status = "active" if c["status"] == "done" and number > c["joined"] else c["status"]
            await app.db.execute("UPDATE channels SET target = ?, status = ?, finished_at = NULL WHERE chat_id = ?",
                                 (number, status, chat_id))
        elif field == "tosp":
            await app.db.execute("UPDATE channels SET kind = 'sponsor', target = ?, joined = 0, status = 'active', added_at = ?, "
                                 "finished_at = NULL WHERE chat_id = ?", (number, now(), chat_id))
            await app.db.execute("DELETE FROM sponsor_seen WHERE chat_id = ?", (chat_id,))
        else:
            await app.db.execute("UPDATE channels SET target = ?, joined = 0, status = 'active', added_at = ?, finished_at = NULL "
                                 "WHERE chat_id = ?", (number, now(), chat_id))
            await app.db.execute("DELETE FROM sponsor_seen WHERE chat_id = ?", (chat_id,))
    elif field == "title":
        await app.db.execute("UPDATE channels SET title = ? WHERE chat_id = ?", (text[:100], chat_id))
    elif field == "link":
        if not text.startswith("http"):
            return await app.send(user["id"], "❌ لینک باید با http شروع شود.", [[b("❌ انصراف", f"a:ch:v:{chat_id}")]])
        await app.db.execute("UPDATE channels SET link = ? WHERE chat_id = ?", (text, chat_id))
    await app.audit(user["id"], f"channel_edit_{field}", chat_id, text[:60])
    await repo.set_step(app, user["id"], "")
    fresh = await _channel(app, chat_id)
    if fresh:
        view, rows = await detail_view(app, fresh)
        await app.send(user["id"], "✅ ذخیره شد.\n\n" + view, rows)


@router.callback_query(F.data == "a:ch:tg")
async def cb_force_toggle(event: CallbackQuery, app: App, user: dict) -> None:
    on = await app.settings.toggle("force_join")
    await app.audit(user["id"], "force_join", None, "on" if on else "off")
    await cb_channels(event, app, user)


@router.callback_query(F.data == "a:ch:me")
async def cb_check_me(event: CallbackQuery, app: App, user: dict) -> None:
    from ..middlewares import channel_status
    await toast(event)
    items = await app.db.all("SELECT * FROM channels WHERE status = 'active' ORDER BY added_at")
    lines = []
    for c in items:
        ok, info = await channel_status(app, c, user["id"])
        icon = "✅" if ok else ("❌" if ok is False else "⚠️")
        lines.append(f"{icon} {esc(c['title'], 30) or c['chat_id']}\n   وضعیت: {esc(info, 160)}")
    await show(app, event, "🔍 **نتیجه بررسی عضویت تو**\n━━━━━━━━━━━━━━\n" + ("\n".join(lines) or "کانال فعالی نیست."),
               [[b("🔄 بررسی دوباره", "a:ch:me")], back("a:ch")])


@router.callback_query(F.data.startswith("a:ch:add:"))
async def cb_add(event: CallbackQuery, app: App, user: dict) -> None:
    kind = (event.data or "").split(":")[3]
    if kind not in ("normal", "sponsor"):
        return await toast(event)
    await toast(event)
    await repo.set_step(app, user["id"], "a_ch", {"kind": kind})
    label = "🎯 اسپانسری" if kind == "sponsor" else "🔒 عادی"
    await show(app, event, f"➕ افزودن کانال ({label})\n\nیکی از این‌ها را بفرست:\n\n• یک پیام فوروارد‌شده از کانال\n"
                           "• شناسه عددی کانال\n• @یوزرنیم کانال\n\n⚠️ ابتدا ربات را در کانال ادمین کن.",
               [[b("❌ انصراف", "a:ch", DANGER)]])


async def _save_channel(app: App, admin_id: int, chat_id: str, title: str, link: str,
                        kind: str = "normal", target: int = 0) -> None:
    await app.db.execute(
        "INSERT INTO channels(chat_id, title, link, added_at, kind, target, joined, status) VALUES(?,?,?,?,?,?,0,'active') "
        "ON CONFLICT(chat_id) DO UPDATE SET title = excluded.title, link = excluded.link, kind = excluded.kind, "
        "target = excluded.target, joined = 0, status = 'active', finished_at = NULL",
        (chat_id, title, link, now(), kind, target))
    await app.db.execute("DELETE FROM sponsor_seen WHERE chat_id = ?", (chat_id,))
    await app.audit(admin_id, "channel_add", chat_id, f"{kind} {title} target={target}")
    await repo.set_step(app, admin_id, "")
    extra = f"\n🎯 هدف: {fa(target)} عضو؛ با رسیدن به این تعداد قفل خودکار برداشته می‌شود." if kind == "sponsor" else ""
    await app.send(admin_id, f"✅ کانال «{esc(title, 40)}» ثبت شد.{extra}", [[b("📣 قفل کانال‌ها", "a:ch")]])


async def _after_channel(app: App, admin_id: int, chat_id: str, title: str, link: str, kind: str) -> None:
    if kind == "sponsor":
        await repo.set_step(app, admin_id, "a_chtarget", {"chat": chat_id, "title": title, "link": link})
        return await app.send(admin_id, f"🎯 چند نفر باید از طریق ربات عضو «{esc(title, 40)}» بشن؟ (عدد بفرست، مثلاً 200)",
                              [[b("❌ انصراف", "a:ch")]])
    await _save_channel(app, admin_id, chat_id, title, link)


@router.message(Step("a_ch"))
async def in_channel(message: Message, app: App, user: dict) -> None:
    if not await admin_only(app, message, user["id"], "channels"):
        return
    kind = parse_step(user["step_data"]).get("kind", "normal")
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
        return await app.send(user["id"], "❌ شناسه نامعتبر است.", [[b("❌ انصراف", "a:ch")]])
    try:
        chat = await app.bot.get_chat(target)
        member = await app.bot.get_chat_member(chat.id, app.bot.id)
    except (BaleAPIError, BaleNetworkError) as exc:
        return await app.send(user["id"], f"❌ دسترسی به کانال ممکن نشد: {esc(str(exc), 120)}\nمطمئن شو ربات ادمین کانال است.",
                              [[b("❌ انصراف", "a:ch")]])
    if not member.is_admin:
        return await app.send(user["id"], "❌ ربات در این کانال ادمین نیست. اول ادمینش کن و دوباره بفرست.", [[b("❌ انصراف", "a:ch")]])
    title = chat.title or chat.username or str(chat.id)
    link = f"https://ble.ir/{chat.username}" if chat.username else ""
    if not link:
        try:
            link = str(await app.bot.export_chat_invite_link(chat.id))
        except (BaleAPIError, BaleNetworkError):
            await repo.set_step(app, user["id"], f"a_chlink:{chat.id}", {"title": title, "kind": kind})
            return await app.send(user["id"], "لینک عضویت کانال را بفرست:", [[b("❌ انصراف", "a:ch")]])
    await _after_channel(app, user["id"], str(chat.id), title, link, kind)


@router.message(Step("a_chlink"), F.text)
async def in_channel_link(message: Message, app: App, user: dict, step_arg: str) -> None:
    link = (message.text or "").strip()
    if not link.startswith("http"):
        return await app.send(user["id"], "لینک باید با http شروع شود.")
    data = parse_step(user["step_data"])
    await _after_channel(app, user["id"], step_arg, data.get("title", step_arg), link, data.get("kind", "normal"))


@router.message(Step("a_chtarget"), F.text)
async def in_channel_target(message: Message, app: App, user: dict) -> None:
    if not await admin_only(app, message, user["id"], "channels"):
        return
    number = parse_int(message.text)
    if number is None or not 1 <= number <= 1_000_000:
        return await app.send(user["id"], "❌ یک عدد بین ۱ تا ۱٬۰۰۰٬۰۰۰ بفرست.", [[b("❌ انصراف", "a:ch")]])
    data = parse_step(user["step_data"])
    await _save_channel(app, user["id"], data["chat"], data["title"], data["link"], "sponsor", number)


# ---------------------------------------------------------------- مدیران (فقط مالک)
@router.callback_query(F.data == "a:ad")
async def cb_admins(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "")
    items = await app.db.all("SELECT * FROM admins ORDER BY added_at")
    rows = []
    for a in items:
        u = await repo.get_user(app, a["user_id"])
        rows.append([b(f"🛡 {uname(u) if u else a['user_id']}", f"a:ad:v:{a['user_id']}")])
    rows.append([b("➕ افزودن مدیر", "a:ad:add", SUCCESS)])
    rows.append(back())
    await show(app, event, f"🛡 **مدیران** ({fa(len(items))})\n━━━━━━━━━━━━━━\n"
                           f"مالک ربات: {app.owner_id}\nمالک همه مجوزها را دارد و قابل حذف نیست.", rows)


@router.callback_query(F.data == "a:ad:add")
async def cb_admin_add(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "a_adm")
    await show(app, event, "➕ شناسه عددی، @یوزرنیم یا یک پیام فوروارد‌شده از کاربر مورد نظر را بفرست (باید قبلاً ربات را استارت کرده باشد):",
               [[b("❌ انصراف", "a:ad", DANGER)]])


@router.message(Step("a_adm"))
async def in_admin(message: Message, app: App, user: dict) -> None:
    if user["id"] != app.owner_id:
        return
    target = None
    if message.forward_from:
        target = await repo.get_user(app, message.forward_from.id)
    elif message.text:
        target = await repo.find_user(app, message.text)
    if not target:
        return await app.send(user["id"], "😕 کاربر پیدا نشد؛ باید ربات را استارت کرده باشد.", [[b("❌ انصراف", "a:ad")]])
    if target["id"] == app.owner_id:
        return await app.send(user["id"], "مالک از قبل همه مجوزها را دارد.")
    await app.db.execute("INSERT OR IGNORE INTO admins(user_id, perms, added_by, added_at) VALUES(?,?,?,?)",
                         (target["id"], ",".join(DEFAULT_ADMIN_PERMS), user["id"], now()))
    await app.audit(user["id"], "admin_add", target["id"])
    await repo.set_step(app, user["id"], "")
    await app.send(target["id"], "🛡 شما به‌عنوان مدیر ربات انتخاب شدید. برای ورود به پنل /panel را بفرستید.")
    await app.send(user["id"], f"✅ {uname(target)} به مدیران اضافه شد. مجوزها را تنظیم کن:",
                   [[b("⚙️ تنظیم مجوزها", f"a:ad:v:{target['id']}", PRIMARY)]])


async def perm_view(app: App, uid: int) -> tuple[str, list[list]] | None:
    row = await app.db.one("SELECT * FROM admins WHERE user_id = ?", (uid,))
    if not row:
        return None
    perms = set(row["perms"].split(","))
    u = await repo.get_user(app, uid)
    rows = chunk([b(("✅ " if p in perms else "▫️ ") + label, f"a:ad:t:{uid}:{p}", SUCCESS if p in perms else None)
                  for p, label in ALL_PERMS.items()], 1)
    rows.append([b("🗑 حذف از مدیران", f"a:ad:d:{uid}", DANGER)])
    rows.append(back("a:ad"))
    return f"🛡 **{uname(u)}** ({uid})\n━━━━━━━━━━━━━━\nمجوزها را روشن/خاموش کن:", rows


@router.callback_query(F.data.startswith("a:ad:v:"))
async def cb_admin_view(event: CallbackQuery, app: App) -> None:
    uid = (event.data or "").split(":")[3]
    view = await perm_view(app, int(uid)) if uid.isdigit() else None
    if not view:
        return await toast(event, "پیدا نشد", True)
    await toast(event)
    await show(app, event, *view)


@router.callback_query(F.data.startswith("a:ad:t:"))
async def cb_admin_toggle(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    uid, perm = parts[3], parts[4]
    row = await app.db.one("SELECT * FROM admins WHERE user_id = ?", (int(uid),)) if uid.isdigit() else None
    if not row or perm not in ALL_PERMS:
        return await toast(event)
    perms = set(p for p in row["perms"].split(",") if p)
    perms ^= {perm}
    await app.db.execute("UPDATE admins SET perms = ? WHERE user_id = ?", (",".join(sorted(perms)), int(uid)))
    await app.audit(user["id"], "admin_perm", uid, f"{perm}={'on' if perm in perms else 'off'}")
    await toast(event)
    view = await perm_view(app, int(uid))
    if view:
        await show(app, event, *view)


@router.callback_query(F.data.startswith("a:ad:d:"))
async def cb_admin_delete(event: CallbackQuery, app: App, user: dict) -> None:
    uid = (event.data or "").split(":")[3]
    if uid.isdigit():
        await app.db.execute("DELETE FROM admins WHERE user_id = ?", (int(uid),))
        await app.audit(user["id"], "admin_remove", uid)
        await app.send(int(uid), "ℹ️ دسترسی مدیریتی شما برداشته شد.")
    await toast(event, "حذف شد")
    await cb_admins(event, app, user)
