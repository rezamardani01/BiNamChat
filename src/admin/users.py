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
"""مدیریت کاربران: جستجو، کارت کاربر، سکه، ویژه، مسدودسازی، تعلیق و پیام."""
from __future__ import annotations

from baleropy import F, Router
from baleropy.types import CallbackQuery, Message

from .. import matching, repo
from ..core import App
from ..filters import Step
from ..ui import DANGER, PRIMARY, SUCCESS, b, chunk, pager, show, toast
from ..util import duration, esc, fa, jdate, now, parse_int
from .common import PER_PAGE, admin_only, back, user_card, user_line

router = Router(name="admin_users")

LISTS = {
    "new": ("🆕 تازه‌ترین‌ها", "SELECT * FROM users ORDER BY joined_at DESC", ()),
    "online": ("🟢 آنلاین (۵ دقیقه)", "SELECT * FROM users WHERE last_seen > ? ORDER BY last_seen DESC", ("T300",)),
    "premium": ("👑 کاربران ویژه", "SELECT * FROM users WHERE premium_until > ? ORDER BY premium_until DESC", ("NOW",)),
    "banned": ("🚫 مسدودها", "SELECT * FROM users WHERE banned = 1 ORDER BY last_seen DESC", ()),
    "susp": ("⏳ تعلیق‌شده‌ها", "SELECT * FROM users WHERE suspended_until > ? ORDER BY suspended_until DESC", ("NOW",)),
    "rich": ("🪙 بیشترین سکه", "SELECT * FROM users ORDER BY coins DESC", ()),
    "active": ("🔥 پرچت‌ترین‌ها", "SELECT * FROM users ORDER BY chats_count DESC", ()),
    "reported": ("🚨 بیشترین گزارش",
                 "SELECT u.* FROM users u JOIN (SELECT reported_id, COUNT(*) c FROM reports GROUP BY reported_id) r "
                 "ON r.reported_id = u.id ORDER BY r.c DESC", ()),
}
COUNT_SQL = {
    "online": "SELECT COUNT(*) FROM users WHERE last_seen > ?",
    "premium": "SELECT COUNT(*) FROM users WHERE premium_until > ?",
    "banned": "SELECT COUNT(*) FROM users WHERE banned = 1",
    "susp": "SELECT COUNT(*) FROM users WHERE suspended_until > ?",
    "reported": "SELECT COUNT(DISTINCT reported_id) FROM reports",
}


def _params(raw: tuple) -> tuple:
    return tuple(now() - 300 if p == "T300" else now() if p == "NOW" else p for p in raw)


@router.callback_query(F.data == "a:u")
async def cb_menu(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "")
    total = await app.db.val("SELECT COUNT(*) FROM users", default=0)
    buttons = [b(title, f"a:u:l:{key}:0") for key, (title, *_rest) in LISTS.items()]
    rows = [[b("🔎 جستجوی کاربر", "a:u:s", PRIMARY)]] + chunk(buttons, 2) + [back()]
    await show(app, event, f"👥 **مدیریت کاربران**\n━━━━━━━━━━━━━━\nکل کاربران: {fa(total)}\n"
                           "برای جستجو شناسه عددی، @یوزرنیم، بخشی از نام یا لینک کاربر را بفرست.", rows)


@router.callback_query(F.data == "a:u:s")
async def cb_search(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "a_usearch")
    await show(app, event, "🔎 شناسه عددی، @یوزرنیم، نام یا کد لینک را بفرست (یا یک پیام فوروارد‌شده):",
               [[b("❌ انصراف", "a:u", DANGER)]])


@router.message(Step("a_usearch"))
async def in_search(message: Message, app: App, user: dict) -> None:
    if not await admin_only(app, message, user["id"], "users"):
        return
    found = None
    results: list[dict] = []
    if message.forward_from:
        found = await repo.get_user(app, message.forward_from.id)
    elif message.text:
        query = message.text.strip()
        found = await repo.find_user(app, query)
        if not found:
            results = await app.db.all("SELECT * FROM users WHERE name LIKE ? ORDER BY last_seen DESC LIMIT 12",
                                       (f"%{query.lstrip('@')}%",))
    if found:
        await repo.set_step(app, user["id"], "")
        return await send_user(app, user["id"], found)
    if len(results) == 1:
        await repo.set_step(app, user["id"], "")
        return await send_user(app, user["id"], results[0])
    if results:
        await repo.set_step(app, user["id"], "")
        return await app.send(user["id"], f"🔎 {fa(len(results))} نتیجه:",
                              chunk([b(user_line(u), f"a:u:v:{u['id']}") for u in results], 1) + [back("a:u")])
    await app.send(user["id"], "😕 کاربری پیدا نشد. دوباره امتحان کن.", [[b("❌ انصراف", "a:u", DANGER)]])


@router.callback_query(F.data.startswith("a:u:l:"))
async def cb_list(event: CallbackQuery, app: App) -> None:
    await toast(event)
    _, _, _, key, page_s = (event.data or "").split(":")
    if key not in LISTS:
        return
    page = int(page_s)
    title, sql, params = LISTS[key]
    total = await app.db.val(COUNT_SQL.get(key, "SELECT COUNT(*) FROM users"),
                             _params(params) if key in COUNT_SQL else (), 0)
    items = await app.db.all(f"{sql} LIMIT ? OFFSET ?", (*_params(params), PER_PAGE, page * PER_PAGE))
    rows = chunk([b(user_line(u), f"a:u:v:{u['id']}") for u in items], 1)
    nav = pager(f"a:u:l:{key}:", page, total, PER_PAGE)
    if nav:
        rows.append(nav)
    rows.append(back("a:u"))
    await show(app, event, f"{title} ({fa(total)})\n━━━━━━━━━━━━━━" if items else f"{title}\n\nموردی نیست.", rows)


# ---------------------------------------------------------------- کارت کاربر
async def user_rows(app: App, admin_id: int, u: dict) -> list[list]:
    perms = await app.perms_of(admin_id)
    uid = u["id"]
    rows: list[list] = []
    line = []
    if "coins" in perms:
        line.append(b("🪙 سکه", f"a:u:c:{uid}", PRIMARY))
    if "premium" in perms:
        line.append(b("👑 ویژه", f"a:u:pr:{uid}", PRIMARY))
    if line:
        rows.append(line)
    if "ban" in perms and uid != app.owner_id:
        rows.append([b("✅ رفع مسدودی" if u["banned"] else "🚫 مسدود کردن", f"a:u:b:{uid}", SUCCESS if u["banned"] else DANGER),
                     b("🔓 رفع تعلیق" if repo.is_suspended(u) else "⏳ تعلیق", f"a:u:us:{uid}" if repo.is_suspended(u) else f"a:u:sp:{uid}")])
    rows.append([b("✉️ ارسال پیام", f"a:u:m:{uid}"), b("📜 تراکنش‌ها", f"a:u:w:{uid}")])
    extra = [b("🚨 گزارش‌ها", f"a:u:rp:{uid}")]
    if u["state"] == "chat":
        extra.append(b("⛔️ قطع گفتگو", f"a:u:x:{uid}", DANGER))
    rows.append(extra)
    rows.append([b("🔄 بروزرسانی", f"a:u:v:{uid}"), b("🔙 کاربران", "a:u")])
    return rows


async def send_user(app: App, admin_id: int, u: dict, event: CallbackQuery | None = None) -> None:
    text, rows = await user_card(app, u), await user_rows(app, admin_id, u)
    if event is not None:
        await show(app, event, text, rows)
    else:
        await app.send(admin_id, text, rows)


async def _target(app: App, event: CallbackQuery, idx: int = 3) -> dict | None:
    parts = (event.data or "").split(":")
    if len(parts) <= idx or not parts[idx].lstrip("-").isdigit():
        return None
    target = await repo.get_user(app, int(parts[idx]))
    if not target:
        await toast(event, "کاربر پیدا نشد", True)
    return target


@router.callback_query(F.data.startswith("a:u:v:"))
async def cb_view(event: CallbackQuery, app: App, user: dict) -> None:
    target = await _target(app, event)
    if target:
        await toast(event)
        await repo.set_step(app, user["id"], "")
        await send_user(app, user["id"], target, event)


# ---------------------------------------------------------------- سکه
@router.callback_query(F.data.startswith("a:u:c:"))
async def cb_coin_menu(event: CallbackQuery, app: App, user: dict) -> None:
    target = await _target(app, event)
    if not target or not await admin_only(app, event, user["id"], "coins"):
        return
    await toast(event)
    uid = target["id"]
    plus = [b(f"+{fa(n)}", f"a:u:ca:{uid}:{n}", SUCCESS) for n in (5, 10, 50, 100, 500)]
    minus = [b(f"-{fa(n)}", f"a:u:ca:{uid}:-{n}", DANGER) for n in (5, 10, 50, 100)]
    await show(app, event, f"🪙 **سکه {esc(target['name'], 20)}**\nموجودی فعلی: {fa(target['coins'])}\n\nمقدار را انتخاب کن:",
               [plus, minus, [b("✍️ مقدار دلخواه", f"a:u:cc:{uid}")], [b("🔙 کاربر", f"a:u:v:{uid}")]])


async def apply_coins(app: App, admin_id: int, uid: int, delta: int, note: str = "") -> int | None:
    new = await repo.add_coins(app, uid, delta, "admin", admin_id=admin_id, note=note or "تغییر توسط مدیریت")
    if new is None:
        return None
    await app.audit(admin_id, "coins", uid, f"{delta:+d} → {new}")
    verb = "🎁 اضافه شد" if delta > 0 else "کسر شد"
    await app.send(uid, f"🪙 {fa(abs(delta))} سکه توسط مدیریت به حساب شما {verb}.\nموجودی: {fa(new)}")
    return new


@router.callback_query(F.data.startswith("a:u:ca:"))
async def cb_coin_apply(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    target = await repo.get_user(app, int(parts[3])) if parts[3].isdigit() else None
    delta = parse_int(parts[4]) if len(parts) > 4 else None
    if not target or delta is None or not await admin_only(app, event, user["id"], "coins"):
        return await toast(event)
    new = await apply_coins(app, user["id"], target["id"], delta)
    await toast(event, f"موجودی جدید: {fa(new)}" if new is not None else "موجودی کافی نیست", new is None)
    target = await repo.get_user(app, target["id"]) or target
    await send_user(app, user["id"], target, event)


@router.callback_query(F.data.startswith("a:u:cc:"))
async def cb_coin_custom(event: CallbackQuery, app: App, user: dict) -> None:
    target = await _target(app, event)
    if not target or not await admin_only(app, event, user["id"], "coins"):
        return
    await toast(event)
    await repo.set_step(app, user["id"], f"a_coin:{target['id']}")
    await show(app, event, "✍️ مقدار را بفرست (مثلاً 25 برای افزودن یا -10 برای کسر):", [[b("❌ انصراف", f"a:u:v:{target['id']}")]])


@router.message(Step("a_coin"), F.text)
async def in_coin(message: Message, app: App, user: dict, step_arg: str) -> None:
    if not await admin_only(app, message, user["id"], "coins") or not step_arg.isdigit():
        return
    delta = parse_int(message.text)
    if not delta:
        return await app.send(user["id"], "یک عدد غیرصفر بفرست.")
    new = await apply_coins(app, user["id"], int(step_arg), delta)
    await repo.set_step(app, user["id"], "")
    target = await repo.get_user(app, int(step_arg))
    if new is None or not target:
        return await app.send(user["id"], "❌ انجام نشد (موجودی کافی نیست یا کاربر وجود ندارد).")
    await send_user(app, user["id"], target)


# ---------------------------------------------------------------- ویژه
@router.callback_query(F.data.startswith("a:u:pr:"))
async def cb_premium_menu(event: CallbackQuery, app: App, user: dict) -> None:
    target = await _target(app, event)
    if not target or not await admin_only(app, event, user["id"], "premium"):
        return
    await toast(event)
    uid = target["id"]
    plus = [b(f"+{d} روز", f"a:u:pa:{uid}:{d}", SUCCESS) for d in (7, 30, 90, 365)]
    minus = [b("-۷ روز", f"a:u:pa:{uid}:-7", DANGER), b("لغو کامل", f"a:u:pa:{uid}:-99999", DANGER)]
    state = f"تا {jdate(target['premium_until'], 'full')}" if repo.is_premium(target) else "ندارد"
    await show(app, event, f"👑 **حساب ویژه {esc(target['name'], 20)}**\nوضعیت: {state}", [plus, minus, [b("🔙 کاربر", f"a:u:v:{uid}")]])


@router.callback_query(F.data.startswith("a:u:pa:"))
async def cb_premium_apply(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    target = await repo.get_user(app, int(parts[3])) if parts[3].isdigit() else None
    days = parse_int(parts[4]) if len(parts) > 4 else None
    if not target or not days or not await admin_only(app, event, user["id"], "premium"):
        return await toast(event)
    until = await repo.grant_premium(app, target["id"], days)
    await app.audit(user["id"], "premium", target["id"], f"{days:+d}d → {until}")
    await toast(event, "انجام شد")
    if days > 0:
        await app.send(target["id"], f"👑 {fa(days)} روز حساب ویژه توسط مدیریت برای شما فعال شد (تا {jdate(until, 'short')}).")
    target = await repo.get_user(app, target["id"]) or target
    await send_user(app, user["id"], target, event)


# ---------------------------------------------------------------- مسدودسازی
@router.callback_query(F.data.startswith("a:u:b:"))
async def cb_ban(event: CallbackQuery, app: App, user: dict) -> None:
    target = await _target(app, event)
    if not target or not await admin_only(app, event, user["id"], "ban"):
        return
    if target["id"] == app.owner_id or await app.is_admin(target["id"]):
        return await toast(event, "مدیران را نمی‌توان مسدود کرد", True)
    if target["banned"]:
        await repo.update_user(app, target["id"], banned=0, ban_reason=None)
        await app.audit(user["id"], "unban", target["id"])
        await app.send(target["id"], "✅ مسدودی حساب شما برداشته شد.")
        await toast(event, "رفع مسدودی شد")
        return await send_user(app, user["id"], await repo.get_user(app, target["id"]) or target, event)
    await toast(event)
    await repo.set_step(app, user["id"], f"a_ban:{target['id']}")
    await show(app, event, "🚫 دلیل مسدودسازی را بنویس (یا - برای بدون دلیل):", [[b("❌ انصراف", f"a:u:v:{target['id']}")]])


async def do_ban(app: App, admin_id: int, uid: int, reason: str | None) -> None:
    await repo.update_user(app, uid, banned=1, ban_reason=reason)
    active = await matching.active_chat(app, uid)
    if active:
        await matching.end_chat(app, active["id"], None, "admin")
    await matching.dequeue(app, uid)
    await app.audit(admin_id, "ban", uid, reason or "")
    await app.send(uid, "🚫 حساب شما توسط مدیریت مسدود شد." + (f"\nدلیل: {reason}" if reason else ""))


@router.message(Step("a_ban"), F.text)
async def in_ban(message: Message, app: App, user: dict, step_arg: str) -> None:
    if not await admin_only(app, message, user["id"], "ban") or not step_arg.isdigit():
        return
    reason = (message.text or "").strip()
    reason = None if reason == "-" else reason[:200]
    await do_ban(app, user["id"], int(step_arg), reason)
    await repo.set_step(app, user["id"], "")
    target = await repo.get_user(app, int(step_arg))
    if target:
        await send_user(app, user["id"], target)


@router.callback_query(F.data.startswith("a:u:sp:"))
async def cb_suspend_menu(event: CallbackQuery, app: App, user: dict) -> None:
    target = await _target(app, event)
    if not target or not await admin_only(app, event, user["id"], "ban"):
        return
    await toast(event)
    uid = target["id"]
    opts = [(1, "۱ ساعت"), (6, "۶ ساعت"), (24, "۱ روز"), (72, "۳ روز"), (168, "۷ روز"), (720, "۳۰ روز")]
    await show(app, event, "⏳ مدت تعلیق را انتخاب کن:",
               chunk([b(label, f"a:u:sa:{uid}:{h}", DANGER) for h, label in opts], 3) + [[b("🔙 کاربر", f"a:u:v:{uid}")]])


@router.callback_query(F.data.startswith("a:u:sa:"))
async def cb_suspend(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    target = await repo.get_user(app, int(parts[3])) if parts[3].isdigit() else None
    hours = parse_int(parts[4]) if len(parts) > 4 else None
    if not target or not hours or not await admin_only(app, event, user["id"], "ban"):
        return await toast(event)
    if target["id"] == app.owner_id or await app.is_admin(target["id"]):
        return await toast(event, "مدیران را نمی‌توان تعلیق کرد", True)
    until = now() + hours * 3600
    await repo.update_user(app, target["id"], suspended_until=until)
    active = await matching.active_chat(app, target["id"])
    if active:
        await matching.end_chat(app, active["id"], None, "admin")
    await matching.dequeue(app, target["id"])
    await app.audit(user["id"], "suspend", target["id"], f"{hours}h")
    await app.send(target["id"], f"⏳ حساب شما تا {jdate(until, 'full')} ({duration(hours * 3600)}) تعلیق شد.")
    await toast(event, "تعلیق شد")
    await send_user(app, user["id"], await repo.get_user(app, target["id"]) or target, event)


@router.callback_query(F.data.startswith("a:u:us:"))
async def cb_unsuspend(event: CallbackQuery, app: App, user: dict) -> None:
    target = await _target(app, event)
    if not target or not await admin_only(app, event, user["id"], "ban"):
        return
    await repo.update_user(app, target["id"], suspended_until=0)
    await app.audit(user["id"], "unsuspend", target["id"])
    await app.send(target["id"], "✅ تعلیق حساب شما برداشته شد.")
    await toast(event, "تعلیق برداشته شد")
    await send_user(app, user["id"], await repo.get_user(app, target["id"]) or target, event)


# ---------------------------------------------------------------- پیام، قطع گفتگو، تاریخچه
@router.callback_query(F.data.startswith("a:u:m:"))
async def cb_message(event: CallbackQuery, app: App, user: dict) -> None:
    target = await _target(app, event)
    if not target:
        return
    await toast(event)
    await repo.set_step(app, user["id"], f"a_msg:{target['id']}")
    await show(app, event, f"✉️ پیام (متن یا رسانه) برای {esc(target['name'], 20)} را بفرست:",
               [[b("❌ انصراف", f"a:u:v:{target['id']}")]])


@router.message(Step("a_msg"))
async def in_message(message: Message, app: App, user: dict, step_arg: str) -> None:
    if not await app.is_admin(user["id"]) or not step_arg.isdigit():
        return
    uid = int(step_arg)
    head = await app.send(uid, "📨 **پیام از طرف مدیریت**")
    ok = await app.copy(uid, message.chat.id, message.message_id, reply_to=head) if head else None
    await repo.set_step(app, user["id"], "")
    await app.audit(user["id"], "message", uid)
    await app.send(user["id"], "✅ ارسال شد." if ok else "⚠️ ارسال نشد (کاربر ربات را بلاک کرده؟)",
                   [[b("🔙 کاربر", f"a:u:v:{uid}")]])


@router.callback_query(F.data.startswith("a:u:x:"))
async def cb_disconnect(event: CallbackQuery, app: App, user: dict) -> None:
    target = await _target(app, event)
    if not target:
        return
    chat = await matching.active_chat(app, target["id"])
    if chat:
        await matching.end_chat(app, chat["id"], None, "admin")
        await app.audit(user["id"], "end_chat", target["id"], str(chat["id"]))
    await toast(event, "گفتگو پایان یافت" if chat else "گفتگوی فعالی نیست")
    await send_user(app, user["id"], await repo.get_user(app, target["id"]) or target, event)


@router.callback_query(F.data.startswith("a:u:w:"))
async def cb_wallet(event: CallbackQuery, app: App) -> None:
    target = await _target(app, event)
    if not target:
        return
    await toast(event)
    txs = await app.db.all("SELECT * FROM wallet_tx WHERE user_id = ? ORDER BY id DESC LIMIT 15", (target["id"],))
    body = "\n".join(f"{'➕' if t['delta'] > 0 else '➖'} {fa(abs(t['delta']))} → {fa(t['balance'])} • {t['kind']} • {jdate(t['created_at'], 'full')}"
                     for t in txs) or "تراکنشی نیست."
    await show(app, event, f"📜 **تراکنش‌های {esc(target['name'], 20)}**\n━━━━━━━━━━━━━━\n{body}",
               [[b("🔙 کاربر", f"a:u:v:{target['id']}")]])


@router.callback_query(F.data.startswith("a:u:rp:"))
async def cb_reports(event: CallbackQuery, app: App) -> None:
    target = await _target(app, event)
    if not target:
        return
    await toast(event)
    items = await app.db.all("SELECT * FROM reports WHERE reported_id = ? ORDER BY id DESC LIMIT 10", (target["id"],))
    rows = [[b(f"#{r['id']} • {r['status']} • {jdate(r['created_at'], 'day')}", f"a:rp:v:{r['id']}")] for r in items]
    rows.append([b("🔙 کاربر", f"a:u:v:{target['id']}")])
    await show(app, event, f"🚨 گزارش‌های علیه {esc(target['name'], 20)}: {fa(len(items))}", rows)
