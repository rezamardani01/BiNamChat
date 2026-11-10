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
"""لینک ناشناس، ارسال پیام ناشناس، پاسخ‌ها و ارسال به مخاطب خاص."""
from __future__ import annotations

import re

from baleropy import Button, F, Router
from baleropy.types import CallbackQuery, Message

from .. import repo
from ..core import App
from ..filters import Step
from ..texts import MEDIA_NAMES
from ..ui import DANGER, PRIMARY, SUCCESS, b, show, toast
from ..util import esc, fa, now

router = Router(name="links")

MEDIA_FIELDS = ("photo", "video", "voice", "audio", "document", "animation", "sticker")
ANON_PER_HOUR = 40
LINK_RE = re.compile(r"^[A-Za-z0-9_]{5,32}$")


def link_key(user: dict) -> str:
    return user["link"] or user["code"]


def kind_of(message: Message) -> str:
    for field in MEDIA_FIELDS:
        if getattr(message, field, None):
            return field
    return message.content_type


# ---------------------------------------------------------------- صفحه لینک من
async def link_panel(app: App, user: dict) -> tuple[str, list[list]]:
    url = app.start_link(link_key(user))
    received = await app.db.val("SELECT COUNT(*) FROM anon_messages WHERE to_id = ?", (user["id"],), 0)
    state = "فعال" if user["anon_on"] else "غیرفعال"
    text = ("🔗 **لینک پیام ناشناس تو**\n━━━━━━━━━━━━━━\n"
            f"{url}\n\n"
            f"📥 پیام‌های دریافتی: {fa(received)}\n"
            f"{'🟢' if user['anon_on'] else '🔴'} وضعیت دریافت: {state}\n\n"
            "این لینک رو توی پیج و استوری یا برای دوستات بذار تا ناشناس بهت پیام بدن.")
    rows = [
        [Button.copy_text("📋 کپی لینک", url, style=PRIMARY)],
        [b("🔴 خاموش کردن" if user["anon_on"] else "🟢 روشن کردن", "l:toggle", DANGER if user["anon_on"] else SUCCESS)],
        [b("✏️ لینک دلخواه", "l:custom"), b("🔄 لینک جدید", "l:reset")],
        [b("🏠 منوی اصلی", "m:home")],
    ]
    return text, rows


@router.callback_query(F.data == "l:home")
async def cb_home(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if not app.settings.on("anon_links"):
        return await show(app, event, "⏸ لینک ناشناس فعلاً غیرفعال است.", [[b("🏠 منو", "m:home")]])
    await repo.set_step(app, user["id"], "")
    text, rows = await link_panel(app, user)
    await show(app, event, text, rows)


@router.callback_query(F.data == "l:toggle")
async def cb_toggle(event: CallbackQuery, app: App, user: dict) -> None:
    user["anon_on"] = 0 if user["anon_on"] else 1
    await repo.update_user(app, user["id"], anon_on=user["anon_on"])
    await toast(event, "دریافت پیام ناشناس " + ("روشن شد" if user["anon_on"] else "خاموش شد"))
    text, rows = await link_panel(app, user)
    await show(app, event, text, rows)


@router.callback_query(F.data == "l:custom")
async def cb_custom(event: CallbackQuery, app: App, user: dict) -> None:
    if app.settings.on("custom_link_premium") and not repo.is_premium(user):
        return await show(app, event, "💎 لینک دلخواه مخصوص کاربران **ویژه** است.",
                          [[b("👑 تهیه حساب ویژه", "w:prem", SUCCESS)], [b("🔙 بازگشت", "l:home")]])
    await toast(event)
    await repo.set_step(app, user["id"], "link_set")
    await show(app, event, "✏️ شناسه دلخواهت رو بفرست.\n۵ تا ۳۲ حرف انگلیسی، عدد یا _ ، مثل: ali_2025",
               [[b("❌ انصراف", "l:home")]])


@router.message(Step("link_set"), F.text)
async def in_custom(message: Message, app: App, user: dict) -> None:
    value = (message.text or "").strip().lower()
    if not LINK_RE.match(value) or value.startswith("ref_"):
        return await app.send(user["id"], "❌ شناسه نامعتبر است. فقط ۵ تا ۳۲ حرف انگلیسی/عدد/_ مجاز است.",
                              [[b("❌ انصراف", "l:home")]])
    taken = await app.db.one("SELECT 1 FROM users WHERE (link = ? OR code = ?) AND id != ?", (value, value, user["id"]))
    if taken:
        return await app.send(user["id"], "😕 این شناسه قبلاً گرفته شده، یکی دیگه امتحان کن.", [[b("❌ انصراف", "l:home")]])
    await repo.update_user(app, user["id"], link=value, step="", step_data="")
    user["link"] = value
    text, rows = await link_panel(app, user)
    await app.send(user["id"], "✅ لینک دلخواه ثبت شد.\n\n" + text, rows)


@router.callback_query(F.data == "l:reset")
async def cb_reset(event: CallbackQuery, app: App) -> None:
    await toast(event)
    await show(app, event, "⚠️ با ساخت لینک جدید، لینک قبلی دیگه کار نمی‌کنه. مطمئنی؟",
               [[b("✅ بله، لینک جدید", "l:resetok", DANGER), b("↩️ انصراف", "l:home")]])


@router.callback_query(F.data == "l:resetok")
async def cb_reset_ok(event: CallbackQuery, app: App, user: dict) -> None:
    code = await repo.new_code(app)
    await repo.update_user(app, user["id"], code=code, link=None)
    user.update(code=code, link=None)
    await toast(event, "لینک جدید ساخته شد")
    text, rows = await link_panel(app, user)
    await show(app, event, text, rows)


# ---------------------------------------------------------------- شروع ارسال
async def begin_send(app: App, user: dict, target: dict, *, via: str = "link") -> bool:
    """پس از اعتبارسنجی، کاربر را در گام ارسال پیام ناشناس قرار می‌دهد."""
    uid = user["id"]
    if target["id"] == uid:
        await app.send(uid, "😄 نمی‌تونی به خودت پیام ناشناس بدی!", [[b("🏠 منو", "m:home")]])
        return False
    if user["state"] != "idle":
        await app.send(uid, "اول جستجو/گفتگوی فعلی رو تموم کن.", [[b("🏠 منو", "m:home")]])
        return False
    if await repo.has_blocked(app, target["id"], uid):
        await app.send(uid, "🚫 این کاربر شما را مسدود کرده و پیامی دریافت نمی‌کند.", [[b("🏠 منو", "m:home")]])
        return False
    if not target["anon_on"] or target["banned"] or target["bot_blocked"]:
        await app.send(uid, "😕 این کاربر فعلاً پیام ناشناس دریافت نمی‌کند.", [[b("🏠 منو", "m:home")]])
        return False
    await repo.set_step(app, uid, f"anon:{target['id']}")
    await app.send(uid, f"🕶 در حال ارسال **پیام ناشناس** به {esc(target['name'], 30)} هستی.\n\n"
                        "🤫 هر چی تو دلته بنویس یا بفرست (متن، عکس، ویس، فایل...). هویتت فاش نمی‌شه.",
                   [[b("✅ تمام شد", "m:home", SUCCESS), b("❌ انصراف", "x:cancel", DANGER)]])
    return True


async def open_anonymous(app: App, message: Message, user: dict, key: str) -> bool:
    """دیپ‌لینک /start <key>. True یعنی رسیدگی شد."""
    if not app.settings.on("anon_links"):
        await app.send(user["id"], "⏸ لینک ناشناس فعلاً غیرفعال است.")
        return False
    target = await app.db.one("SELECT * FROM users WHERE link = ? OR code = ?", (key.lower(), key))
    if not target:
        await app.send(user["id"], "❌ این لینک معتبر نیست یا حذف شده.")
        return False
    return await begin_send(app, user, target)


# ---------------------------------------------------------------- ارسال و تحویل
def _controls(anon_id: int) -> list[list]:
    return [[b("↩️ پاسخ ناشناس", f"ar:{anon_id}", PRIMARY)],
            [b("🚫 بلاک فرستنده", f"ab:{anon_id}"), b("🚨 گزارش", f"arp:{anon_id}", DANGER)]]


async def deliver(app: App, sender: dict, target: dict, message: Message, *, reply_to_anon: int | None = None) -> int | None:
    """پیام را برای گیرنده می‌فرستد و رکورد آن را می‌سازد؛ شناسه رکورد یا None."""
    kind = kind_of(message)
    body = message.text if kind == "text" else message.caption
    anon_id = await app.db.execute(
        "INSERT INTO anon_messages(from_id, to_id, kind, preview, reply_to, created_at) VALUES(?,?,?,?,?,?)",
        (sender["id"], target["id"], kind, (body or "")[:120], reply_to_anon, now()))
    header = "💬 **پاسخ ناشناس**" if reply_to_anon else "📩 **پیام ناشناس جدید**"
    controls = _controls(anon_id)
    if kind == "text":
        mid = await app.send(target["id"], f"{header}\n━━━━━━━━━━━━━━\n{message.text}", controls)
    else:
        head = await app.send(target["id"], f"{header} • {MEDIA_NAMES.get(kind, 'رسانه')}\n━━━━━━━━━━━━━━", controls)
        mid = await app.copy(target["id"], message.chat.id, message.message_id, reply_to=head) if head else None
        mid = mid or head
    if not mid:
        await app.db.execute("DELETE FROM anon_messages WHERE id = ?", (anon_id,))
        return None
    await app.db.execute("UPDATE anon_messages SET dst_mid = ? WHERE id = ?", (mid, anon_id))
    return anon_id


@router.message(Step("anon"))
async def in_anon(message: Message, app: App, user: dict, step_arg: str) -> None:
    uid = user["id"]
    if not step_arg.isdigit():
        return await repo.set_step(app, uid, "")
    kind = kind_of(message)
    if kind in ("unknown", "invoice", "successful_payment", "new_chat_members", "left_chat_member"):
        return
    target = await repo.get_user(app, int(step_arg))
    if not target or not target["anon_on"] or await repo.has_blocked(app, target["id"], uid):
        await repo.set_step(app, uid, "")
        return await app.send(uid, "😕 ارسال به این کاربر ممکن نیست.", [[b("🏠 منو", "m:home")]])
    recent = await app.db.val("SELECT COUNT(*) FROM anon_messages WHERE from_id = ? AND created_at > ?",
                              (uid, now() - 3600), 0)
    if recent >= ANON_PER_HOUR:
        return await app.send(uid, "⏳ در یک ساعت گذشته خیلی پیام فرستادی؛ کمی بعد دوباره تلاش کن.")
    anon_id = await deliver(app, user, target, message)
    if anon_id is None:
        return await app.send(uid, "⚠️ پیام تحویل داده نشد. شاید کاربر ربات را بلاک کرده باشد.")
    await app.send(uid, f"✅ پیام ناشناست برای {esc(target['name'], 30)} ارسال شد.\n"
                        "می‌تونی پیام بعدی رو هم بفرستی.",
                   [[b("🏠 پایان و بازگشت به منو", "m:home")]])


# ---------------------------------------------------------------- کنترل‌های گیرنده
async def _msg_for_receiver(app: App, event: CallbackQuery, user: dict) -> dict | None:
    try:
        anon_id = int((event.data or "").split(":")[1])
    except (IndexError, ValueError):
        return None
    row = await app.db.one("SELECT * FROM anon_messages WHERE id = ? AND to_id = ?", (anon_id, user["id"]))
    return row


@router.callback_query(F.data.startswith("ar:"))
async def cb_reply(event: CallbackQuery, app: App, user: dict) -> None:
    row = await _msg_for_receiver(app, event, user)
    if not row:
        return await toast(event, "پیام پیدا نشد", True)
    if user["state"] != "idle":
        return await toast(event, "اول گفتگوی فعلی را تمام کن", True)
    await toast(event)
    await repo.set_step(app, user["id"], f"areply:{row['id']}")
    await app.send(user["id"], "↩️ پاسخت رو بنویس یا بفرست. ناشناس بودن تو هم حفظ می‌شه.",
                   [[b("❌ انصراف", "x:cancel", DANGER)]])


@router.message(Step("areply"))
async def in_reply(message: Message, app: App, user: dict, step_arg: str) -> None:
    uid = user["id"]
    row = await app.db.one("SELECT * FROM anon_messages WHERE id = ? AND to_id = ?",
                           (int(step_arg) if step_arg.isdigit() else 0, uid))
    if not row:
        await repo.set_step(app, uid, "")
        return await app.send(uid, "پیام اصلی پیدا نشد.")
    kind = kind_of(message)
    if kind in ("unknown", "invoice", "successful_payment", "new_chat_members", "left_chat_member"):
        return
    target = await repo.get_user(app, row["from_id"])
    if not target or await repo.has_blocked(app, target["id"], uid) or target["banned"]:
        await repo.set_step(app, uid, "")
        return await app.send(uid, "😕 ارسال پاسخ ممکن نیست.", [[b("🏠 منو", "m:home")]])
    new_id = await deliver(app, user, target, message, reply_to_anon=row["id"])
    await repo.set_step(app, uid, "")
    if new_id is None:
        return await app.send(uid, "⚠️ پاسخ تحویل داده نشد.")
    await app.send(uid, "✅ پاسخت ارسال شد.", [[b("🏠 منو", "m:home")]])


@router.callback_query(F.data.startswith("ab:"))
async def cb_block(event: CallbackQuery, app: App, user: dict) -> None:
    row = await _msg_for_receiver(app, event, user)
    if not row:
        return await toast(event, "پیام پیدا نشد", True)
    await repo.block(app, user["id"], row["from_id"])
    await toast(event, "🚫 فرستنده بلاک شد؛ دیگه پیامی ازش نمی‌گیری.", True)


@router.callback_query(F.data.startswith("arp:"))
async def cb_report(event: CallbackQuery, app: App, user: dict) -> None:
    row = await _msg_for_receiver(app, event, user)
    if not row:
        return await toast(event, "پیام پیدا نشد", True)
    exists = await app.db.one("SELECT 1 FROM reports WHERE source = 'anon' AND chat_id = ? AND reporter_id = ?",
                              (row["id"], user["id"]))
    if exists:
        return await toast(event, "قبلاً گزارش داده‌ای", True)
    rid = await app.db.execute(
        "INSERT INTO reports(chat_id, source, reporter_id, reported_id, reason, created_at) VALUES(?,?,?,?,?,?)",
        (row["id"], "anon", user["id"], row["from_id"], f"پیام ناشناس: {row['preview'] or row['kind']}", now()))
    await repo.block(app, user["id"], row["from_id"])
    app.spawn(app.event(f"🚨 گزارش #{rid} (پیام ناشناس)\n👤 گزارش‌دهنده: {user['id']}\n⚠️ گزارش‌شده: {row['from_id']}", "reports"))
    await toast(event, "🚨 گزارش ثبت شد و فرستنده بلاک شد", True)
    for admin_id in await app.admin_ids("reports"):
        await app.send(admin_id, f"🚨 گزارش جدید #{rid} (پیام ناشناس)", [[b("🔍 بررسی گزارش", f"a:rp:v:{rid}", PRIMARY)]])


# ---------------------------------------------------------------- مخاطب خاص
@router.callback_query(F.data == "k:home")
async def cb_contact(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if not app.settings.on("specific_contact"):
        return await show(app, event, "⏸ این بخش فعلاً غیرفعال است.", [[b("🏠 منو", "m:home")]])
    if user["state"] != "idle":
        return await toast(event, "اول گفتگوی فعلی را تمام کن", True)
    await repo.set_step(app, user["id"], "contact")
    await show(app, event,
               "💌 **ارسال پیام ناشناس به مخاطب خاص**\n━━━━━━━━━━━━━━\n"
               "مخاطبت رو با یکی از این روش‌ها معرفی کن:\n\n"
               "📨 یک پیام از اون رو همین‌جا فوروارد کن\n"
               "🔢 شناسه عددی کاربر رو بفرست\n"
               "🔎 یوزرنیم رو با یا بدون @ بفرست\n"
               "🔗 لینک ناشناسش رو بفرست\n\n"
               "ℹ️ مخاطب باید عضو ربات باشه و دریافت پیام ناشناس رو خاموش نکرده باشه.",
               [[b("❌ انصراف", "m:home", DANGER)]])


@router.message(Step("contact"))
async def in_contact(message: Message, app: App, user: dict) -> None:
    uid = user["id"]
    target = None
    if message.forward_from:
        target = await repo.get_user(app, message.forward_from.id)
    elif message.text:
        query = message.text.strip()
        m = re.search(r"start=([A-Za-z0-9_]+)", query)
        target = await repo.find_user(app, m.group(1) if m else query)
    else:
        return await app.send(uid, "یه شناسه، یوزرنیم یا پیام فوروارد‌شده بفرست.", [[b("❌ انصراف", "m:home")]])
    if not target:
        return await app.send(uid, "🔍 چنین کاربری توی ربات پیدا نشد. مطمئن شو عضو ربات هست.",
                              [[b("❌ انصراف", "m:home")]])
    await begin_send(app, user, target, via="contact")
