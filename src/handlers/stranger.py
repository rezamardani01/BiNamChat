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
"""چت ناشناس: جستجو، رله پیام، کنترل‌های چت، گزارش و بلاک."""
from __future__ import annotations

import logging

from baleropy import F, Router
from baleropy.types import CallbackQuery, Message, ReplyKeyboardRemove

from .. import matching, repo
from ..core import App
from ..filters import InChat
from ..matching import KB_END, KB_NEXT, KB_PROFILE, KB_TEXTS
from ..texts import MEDIA_NAMES
from ..ui import DANGER, PRIMARY, SUCCESS, b, show, toast
from ..util import fa, has_contact_info, now
from .onboarding import ensure_onboarded

log = logging.getLogger("binam.stranger")
router = Router(name="stranger")

REASONS = {
    "harassment": "😠 توهین یا مزاحمت",
    "inappropriate": "🔞 محتوای نامناسب",
    "deception": "🎭 فریب یا جعل هویت",
    "spam": "📨 تبلیغ یا هرزنامه",
    "other": "❔ مورد دیگر",
}
MEDIA_FIELDS = ("photo", "video", "voice", "audio", "document", "animation", "sticker")


# ---------------------------------------------------------------- صفحه جستجو
def filter_rows(app: App, user: dict) -> list[list]:
    cg, ca, cc = (app.settings.int(k) for k in ("cost_gender", "cost_age", "cost_city"))
    free = repo.is_premium(user) and app.settings.on("premium_free_search")

    def tag(c: int) -> str:
        return "" if free or not c else f" ({fa(c)} سکه)"

    return [
        [b("🎲 جستجوی شانسی", "s:go:random", SUCCESS)],
        [b("👩 دختر" + tag(cg), "s:go:female", PRIMARY), b("👨 پسر" + tag(cg), "s:go:male", PRIMARY)],
        [b(f"{'✅' if user['same_age'] else '▫️'} هم‌سن" + tag(ca), "s:tg:age"),
         b(f"{'✅' if user['same_city'] else '▫️'} همشهری" + tag(cc), "s:tg:city")],
        [b("🏠 منوی اصلی", "m:home")],
    ]


def filter_text(user: dict) -> str:
    return ("🎲 **چت ناشناس**\n━━━━━━━━━━━━━━\n"
            "با یه آدم جدید ناشناس صحبت کن!\n\n"
            "👇 فیلترهای دلخواهت رو روشن کن و نوع جستجو رو انتخاب کن\n"
            f"🪙 موجودی: {fa(user['coins'])} سکه")


@router.callback_query(F.data == "s:home")
async def cb_search_home(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if not app.settings.on("stranger_chat"):
        return await show(app, event, "⏸ چت ناشناس فعلاً توسط مدیریت غیرفعال شده است.", [[b("🏠 منو", "m:home")]])
    if not await ensure_onboarded(app, event, user):
        return
    user = await matching.heal(app, user)
    if user["state"] == "chat":
        return await app.send(user["id"], "💬 الان وسط یه گفتگو هستی.", matching.chat_controls())
    if user["state"] == "searching":
        return await show(app, event, "🔎 در حال جستجو هستیم...", [[b("❌ لغو جستجو", "s:cancel", DANGER)]])
    await show(app, event, filter_text(user), filter_rows(app, user))


@router.callback_query(F.data.startswith("s:tg:"))
async def cb_toggle(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if user["state"] != "idle":
        return
    field = "same_age" if event.data.endswith("age") else "same_city"
    user[field] = 0 if user[field] else 1
    await repo.update_user(app, user["id"], **{field: user[field]})
    await show(app, event, filter_text(user), filter_rows(app, user))


@router.callback_query(F.data.startswith("s:go:"))
async def cb_go(event: CallbackQuery, app: App, user: dict) -> None:
    stype = event.data.split(":")[2]
    if stype not in ("random", "male", "female"):
        return await toast(event)
    if not app.settings.on("stranger_chat"):
        return await toast(event, "چت ناشناس غیرفعال است", True)
    if not await ensure_onboarded(app, event, user):
        return await toast(event)
    fresh = await matching.heal(app, user)
    if fresh["state"] != "idle":
        return await toast(event, "الان درگیر یک جستجو/گفتگو هستی", True)
    cost = matching.search_cost(app, fresh, stype, fresh["same_age"], fresh["same_city"])
    if fresh["coins"] < cost:
        await toast(event, "موجودی سکه کافی نیست", True)
        return await show(app, event,
                          f"🪙 این جستجو {fa(cost)} سکه هزینه دارد و موجودی‌ات {fa(fresh['coins'])} است.\n"
                          "سکه بگیر یا فیلتر ساده‌تری انتخاب کن.",
                          [[b("🛍 فروشگاه", "w:home", PRIMARY)], [b("🔙 بازگشت", "s:home")]])
    await toast(event)
    fresh["search_type"] = stype
    await repo.update_user(app, fresh["id"], search_type=stype)
    text = f"🔎 در حال پیدا کردن مخاطب ({matching.describe_search(stype, fresh['same_age'], fresh['same_city'])})..."
    if cost:
        text += f"\n🪙 هزینه: {fa(cost)} سکه (بعد از اتصال کسر می‌شود)"
    mid = await show(app, event, text, [[b("❌ لغو جستجو", "s:cancel", DANGER)]])
    await matching.enqueue(app, fresh, mid)
    await matching.search_and_announce(app, fresh["id"])


@router.callback_query(F.data == "s:cancel")
async def cb_cancel_search(event: CallbackQuery, app: App, user: dict) -> None:
    row = await matching.dequeue(app, user["id"])
    await toast(event, "جستجو لغو شد" if row else None)
    fresh = await repo.get_user(app, user["id"]) or user
    if fresh["state"] == "chat":
        return
    await show(app, event, filter_text(fresh), filter_rows(app, fresh))


# ---------------------------------------------------------------- کنترل‌های چت
async def _my_chat(app: App, user: dict) -> dict | None:
    return await matching.active_chat(app, user["id"])


async def _partner(app: App, chat: dict, uid: int) -> dict | None:
    return await repo.get_user(app, matching.other_of(chat, uid))


@router.callback_query(F.data == "c:prof")
async def cb_profile(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await show_partner_profile(app, user)


async def show_partner_profile(app: App, user: dict) -> None:
    chat = await _my_chat(app, user)
    if not chat:
        return await app.send(user["id"], "الان در گفتگو نیستی.", [[b("🏠 منو", "m:home")]])
    partner = await _partner(app, chat, user["id"])
    if partner:
        from .profile import send_profile_card
        await send_profile_card(app, user["id"], partner, rows=[[b("🗑 بستن", "x:del")]], anonymous=chat["kind"] == "random")


@router.callback_query(F.data == "c:end")
async def cb_end_ask(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if not await _my_chat(app, user):
        return
    await app.send(user["id"], "⚠️ مطمئنی می‌خوای گفتگو رو تموم کنی؟",
                   [[b("✅ بله، پایان", "c:endok", DANGER), b("↩️ ادامه چت", "x:del")]])


@router.callback_query(F.data == "c:endok")
async def cb_end(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await app.delete(user["id"], event.message.message_id if event.message else None)
    chat = await _my_chat(app, user)
    if chat:
        await matching.end_chat(app, chat["id"], user["id"], "user")


@router.callback_query(F.data == "c:blk")
async def cb_block_ask(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if await _my_chat(app, user):
        await app.send(user["id"], "🚫 با بلاک‌کردن، گفتگو تموم می‌شه و دیگه هیچ‌وقت بهم وصل نمی‌شید. مطمئنی؟",
                       [[b("✅ بله، بلاک", "c:blkok", DANGER), b("↩️ انصراف", "x:del")]])


@router.callback_query(F.data == "c:blkok")
async def cb_block(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event, "بلاک شد")
    await app.delete(user["id"], event.message.message_id if event.message else None)
    chat = await _my_chat(app, user)
    if chat:
        await repo.block(app, user["id"], matching.other_of(chat, user["id"]))
        await matching.end_chat(app, chat["id"], user["id"], "user")


@router.callback_query(F.data == "c:rep")
async def cb_report_ask(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    chat = await _my_chat(app, user)
    if chat:
        await app.send(user["id"], "🚨 دلیل گزارش چیه؟", _reason_rows(f"c:rr:{chat['id']}:"))


def _reason_rows(prefix: str) -> list[list]:
    rows = [[b(label, prefix + key, DANGER if key == "harassment" else None)] for key, label in REASONS.items()]
    rows.append([b("↩️ انصراف", "x:del")])
    return rows


async def file_report(app: App, reporter: dict, chat_id: int, reason: str) -> int | None:
    chat = await app.db.one("SELECT * FROM chats WHERE id = ?", (chat_id,))
    if not chat or reporter["id"] not in (chat["a"], chat["b"]):
        return None
    if await app.db.one("SELECT 1 FROM reports WHERE chat_id = ? AND reporter_id = ?", (chat_id, reporter["id"])):
        return -1
    reported = matching.other_of(chat, reporter["id"])
    rid = await app.db.execute(
        "INSERT INTO reports(chat_id, source, reporter_id, reported_id, reason, created_at) VALUES(?,?,?,?,?,?)",
        (chat_id, chat["kind"], reporter["id"], reported, reason, now()))
    await repo.block(app, reporter["id"], reported)
    limit = app.settings.int("auto_suspend_reports")
    if limit:
        count = await app.db.val("SELECT COUNT(DISTINCT reporter_id) FROM reports WHERE reported_id = ? AND created_at > ?",
                                 (reported, now() - 7 * 86400), 0)
        if count >= limit:
            until = now() + app.settings.int("suspend_hours") * 3600
            await repo.update_user(app, reported, suspended_until=until)
            active = await matching.active_chat(app, reported)
            if active:
                await matching.end_chat(app, active["id"], None, "admin")
            await app.send(reported, "⚠️ به‌دلیل گزارش‌های متعدد از طرف کاربران، حساب شما به‌طور موقت تعلیق شد.")
            await app.event(f"⛔️ تعلیق خودکار\n⚠️ کاربر: {reported}\n🚨 تعداد گزارش‌دهنده: {count}", "reports")
    app.spawn(app.event(f"🚨 گزارش #{rid}\n👤 گزارش‌دهنده: {reporter['id']}\n⚠️ گزارش‌شده: {reported}\n"
                        f"📝 دلیل: {REASONS.get(reason, reason)}", "reports"))
    for admin_id in await app.admin_ids("reports"):
        await app.send(admin_id, f"🚨 گزارش جدید #{rid}\nدلیل: {REASONS.get(reason, reason)}",
                       [[b("🔍 بررسی گزارش", f"a:rp:v:{rid}", PRIMARY)]])
    return rid


@router.callback_query(F.data.startswith("c:rr:") | F.data.startswith("e:rr:"))
async def cb_report(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    if len(parts) != 4 or not parts[2].isdigit() or parts[3] not in REASONS:
        return await toast(event)
    rid = await file_report(app, user, int(parts[2]), parts[3])
    await app.delete(user["id"], event.message.message_id if event.message else None)
    if rid is None:
        return await toast(event, "گفتگو پیدا نشد", True)
    if rid == -1:
        return await toast(event, "قبلاً برای این گفتگو گزارش داده‌ای", True)
    await toast(event, "گزارشت ثبت شد")
    await app.send(user["id"], "✅ گزارشت برای مدیریت ثبت شد و کاربر برای تو بلاک شد. ممنون که کمک می‌کنی!")
    chat = await app.db.one("SELECT * FROM chats WHERE id = ?", (int(parts[2]),))
    if chat and chat["status"] == "active":
        await matching.end_chat(app, chat["id"], user["id"], "user")


# ---------------------------------------------------------------- کارت پایان چت
async def _ended_chat(app: App, event: CallbackQuery, user: dict) -> dict | None:
    parts = (event.data or "").split(":")
    if len(parts) < 3 or not parts[2].isdigit():
        return None
    chat = await app.db.one("SELECT * FROM chats WHERE id = ?", (int(parts[2]),))
    if not chat or user["id"] not in (chat["a"], chat["b"]):
        return None
    return chat


@router.callback_query(F.data.startswith("e:rep:"))
async def cb_ended_report(event: CallbackQuery, app: App, user: dict) -> None:
    chat = await _ended_chat(app, event, user)
    await toast(event)
    if chat:
        await app.send(user["id"], "🚨 دلیل گزارش چیه؟", _reason_rows(f"e:rr:{chat['id']}:"))


@router.callback_query(F.data.startswith("e:blk:"))
async def cb_ended_block(event: CallbackQuery, app: App, user: dict) -> None:
    chat = await _ended_chat(app, event, user)
    if not chat:
        return await toast(event)
    await repo.block(app, user["id"], matching.other_of(chat, user["id"]))
    await toast(event, "🚫 مخاطب بلاک شد", True)


@router.callback_query(F.data.startswith("e:fr:"))
async def cb_ended_friend(event: CallbackQuery, app: App, user: dict) -> None:
    chat = await _ended_chat(app, event, user)
    if not chat:
        return await toast(event)
    other = matching.other_of(chat, user["id"])
    from .friends import send_friend_request
    ok, msg = await send_friend_request(app, user, other)
    await toast(event, msg, not ok)


# ---------------------------------------------------------------- کیبورد پاسخ
@router.message(InChat(), F.text == KB_END)
async def kb_end(message: Message, app: App, user: dict) -> None:
    await app.send(user["id"], "⚠️ مطمئنی می‌خوای گفتگو رو تموم کنی؟",
                   [[b("✅ بله، پایان", "c:endok", DANGER), b("↩️ ادامه چت", "x:del")]])


@router.message(InChat(), F.text == KB_NEXT)
async def kb_next(message: Message, app: App, user: dict) -> None:
    chat = await _my_chat(app, user)
    if not chat:
        return
    kind = chat["kind"]
    await matching.end_chat(app, chat["id"], user["id"], "user", notify=False)
    await app.send(chat["a"] if chat["b"] == user["id"] else chat["b"], "🔚 مخاطب گفتگو را پایان داد.",
                   ReplyKeyboardRemove())
    other = matching.other_of(chat, user["id"])
    friends = await repo.are_friends(app, other, user["id"])
    await app.send(other, "حالا می‌خوای چی کار کنی؟", matching.ended_controls(chat["id"], friends, kind))
    await app.send(user["id"], "🔄 گفتگو بسته شد. بریم سراغ نفر بعدی؟", ReplyKeyboardRemove())
    fresh = await repo.get_user(app, user["id"]) or user
    if kind == "random" and app.settings.on("stranger_chat"):
        cost = matching.search_cost(app, fresh, fresh["search_type"], fresh["same_age"], fresh["same_city"])
        if fresh["coins"] >= cost:
            mid = await app.send(user["id"], f"🔎 در حال جستجو ({matching.describe_search(fresh['search_type'], fresh['same_age'], fresh['same_city'])})...",
                                 [[b("❌ لغو جستجو", "s:cancel", DANGER)]])
            await matching.enqueue(app, fresh, mid)
            await matching.search_and_announce(app, fresh["id"])
            return
    await app.send(user["id"], "👇 برای ادامه از منو استفاده کن", [[b("🎲 چت جدید", "s:home", PRIMARY), b("🏠 منو", "m:home")]])


@router.message(InChat(), F.text == KB_PROFILE)
async def kb_profile(message: Message, app: App, user: dict) -> None:
    await show_partner_profile(app, user)


@router.message(F.text.in_(KB_TEXTS))
async def kb_stale(message: Message, app: App, user: dict) -> None:
    await app.send(user["id"], "🙂 الان در گفتگو نیستی", ReplyKeyboardRemove())
    from .start import send_home
    await send_home(app, message, user)


@router.callback_query(F.data == "x:del")
async def cb_del(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if event.message:
        await app.delete(user["id"], event.message.message_id)


# ---------------------------------------------------------------- رله پیام‌ها
def _kind_of(message: Message) -> str:
    for field in MEDIA_FIELDS:
        if getattr(message, field, None):
            return field
    return message.content_type


@router.message(InChat())
async def relay(message: Message, app: App, user: dict) -> None:
    uid = user["id"]
    chat = await _my_chat(app, user)
    if not chat:
        await repo.update_user(app, uid, state="idle")
        return
    kind = _kind_of(message)
    if kind in ("contact", "location"):
        return await app.send(uid, "🔒 برای حفظ حریم خصوصی، ارسال مخاطب و موقعیت مکانی در چت مجاز نیست.")
    if kind in ("unknown", "invoice", "successful_payment", "new_chat_members", "left_chat_member", "web_app_data"):
        return
    if kind != "text" and chat["kind"] == "random" and app.settings.on("premium_media") and not repo.is_premium(user):
        return await app.send(uid, f"{MEDIA_NAMES.get(kind, 'رسانه')} فقط برای کاربران **ویژه** مجاز است.",
                              [[b("👑 تهیه حساب ویژه", "w:prem", PRIMARY)]])
    body = message.text if kind == "text" else message.caption
    if chat["kind"] == "random" and app.settings.on("filter_contacts") and has_contact_info(body):
        return await app.send(uid, "🚫 ارسال شماره تماس، لینک و آیدی در چت ناشناس ممنوع است. پیامت ارسال نشد.")

    other = matching.other_of(chat, uid)
    reply_to = None
    if message.reply_to_message:
        reply_to = await app.db.val(
            "SELECT peer_mid FROM msgmap WHERE chat_id = ? AND user_id = ? AND mid = ?",
            (chat["id"], uid, message.reply_to_message.message_id))
    if kind == "text":
        peer_mid = await app.send(other, message.text or "", reply_to=reply_to)
    else:
        peer_mid = await app.copy(other, message.chat.id, message.message_id, reply_to=reply_to)
    if not peer_mid:
        partner = await repo.get_user(app, other)
        if partner and partner["bot_blocked"]:
            await matching.end_chat(app, chat["id"], None, "gone")
        else:
            await app.send(uid, "⚠️ ارسال پیام ناموفق بود، دوباره امتحان کن.")
        return
    await app.db.execute("INSERT OR REPLACE INTO msgmap(chat_id, user_id, mid, peer_mid) VALUES(?,?,?,?)",
                         (chat["id"], uid, message.message_id, peer_mid))
    await app.db.execute("INSERT OR REPLACE INTO msgmap(chat_id, user_id, mid, peer_mid) VALUES(?,?,?,?)",
                         (chat["id"], other, peer_mid, message.message_id))
    await app.db.execute(
        "UPDATE chats SET last_activity = ?, a_msgs = a_msgs + (a = ?), b_msgs = b_msgs + (b = ?) WHERE id = ?",
        (now(), uid, uid, chat["id"]))
    await app.db.execute("UPDATE users SET msgs_sent = msgs_sent + 1 WHERE id = ?", (uid,))


@router.edited_message(InChat(), F.text)
async def relay_edit(message: Message, app: App, user: dict) -> None:
    chat = await _my_chat(app, user)
    if not chat:
        return
    peer = await app.db.val("SELECT peer_mid FROM msgmap WHERE chat_id = ? AND user_id = ? AND mid = ?",
                            (chat["id"], user["id"], message.message_id))
    if peer:
        await app.edit(matching.other_of(chat, user["id"]), int(peer), message.text or "")
