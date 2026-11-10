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
"""دوستان: درخواست دوستی، لیست، پیام مستقیم و درخواست چت."""
from __future__ import annotations

from baleropy import F, Router
from baleropy.types import CallbackQuery, Message

from .. import matching, repo
from ..core import App
from ..filters import Step
from ..ui import DANGER, PRIMARY, SUCCESS, b, chunk, pager, show, toast
from ..util import esc, fa, now
from .links import kind_of
from .onboarding import ensure_onboarded
from .profile import send_profile_card

router = Router(name="friends")
PER_PAGE = 8
CHAT_REQUEST_TTL = 15 * 60


async def send_friend_request(app: App, user: dict, other_id: int) -> tuple[bool, str]:
    uid = user["id"]
    other = await repo.get_user(app, other_id)
    if not other or other_id == uid:
        return False, "کاربر پیدا نشد"
    if await repo.are_friends(app, uid, other_id):
        return False, "از قبل دوست هستید"
    if await repo.is_blocked_pair(app, uid, other_id):
        return False, "ارسال درخواست ممکن نیست"
    if await app.db.one("SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND kind = 'friend' AND status = 'pending'",
                        (uid, other_id)):
        return False, "درخواست قبلاً ارسال شده"
    rid = await app.db.execute(
        "INSERT INTO friend_requests(from_id, to_id, kind, status, created_at, expires_at) VALUES(?,?,?,?,?,?)",
        (uid, other_id, "friend", "pending", now(), now() + 7 * 86400))
    sent = await app.send(other_id,
                          f"➕ **درخواست دوستی**\n━━━━━━━━━━━━━━\n{esc(user['name'], 30)} می‌خواد باهات دوست بشه.\n"
                          "(با پذیرفتن، پروفایل هم رو می‌بینید و می‌تونید پیام بدید)",
                          [[b("✅ قبول", f"fr:ok:{rid}", SUCCESS), b("❌ رد", f"fr:no:{rid}", DANGER)]])
    if not sent:
        return False, "ارسال درخواست ممکن نشد"
    return True, "✅ درخواست دوستی ارسال شد"


@router.callback_query(F.data.startswith("fr:"))
async def cb_friend_answer(event: CallbackQuery, app: App, user: dict) -> None:
    _, action, rid = (event.data or "").split(":")[:3]
    req = await app.db.one("SELECT * FROM friend_requests WHERE id = ? AND to_id = ? AND kind = 'friend'",
                           (int(rid), user["id"]))
    if not req or req["status"] != "pending":
        return await toast(event, "این درخواست دیگه معتبر نیست", True)
    await app.delete(user["id"], event.message.message_id if event.message else None)
    if action == "no":
        await app.db.execute("UPDATE friend_requests SET status = 'rejected' WHERE id = ?", (req["id"],))
        return await toast(event, "رد شد")
    await app.db.execute("UPDATE friend_requests SET status = 'accepted' WHERE id = ?", (req["id"],))
    ts = now()
    await app.db.execute("INSERT OR IGNORE INTO friends(user_id, friend_id, created_at) VALUES(?,?,?)",
                         (req["from_id"], req["to_id"], ts))
    await app.db.execute("INSERT OR IGNORE INTO friends(user_id, friend_id, created_at) VALUES(?,?,?)",
                         (req["to_id"], req["from_id"], ts))
    await toast(event, "🎉 دوست شدید")
    sender = await repo.get_user(app, req["from_id"])
    await app.send(user["id"], f"🎉 حالا با {esc(sender['name'], 30) if sender else ''} دوستید!",
                   [[b("👥 دوستان من", "f:home", PRIMARY)]])
    await app.send(req["from_id"], f"🎉 {esc(user['name'], 30)} درخواست دوستیت رو قبول کرد!",
                   [[b("👥 دوستان من", "f:home", PRIMARY)]])


# ---------------------------------------------------------------- لیست
async def friends_page(app: App, uid: int, page: int) -> tuple[str, list[list]]:
    total = await app.db.val("SELECT COUNT(*) FROM friends WHERE user_id = ?", (uid,), 0)
    rows_db = await app.db.all(
        "SELECT u.id, u.name, u.gender, u.state FROM friends f JOIN users u ON u.id = f.friend_id "
        "WHERE f.user_id = ? ORDER BY f.created_at DESC LIMIT ? OFFSET ?", (uid, PER_PAGE, page * PER_PAGE))
    if not total:
        return ("👥 **دوستان**\n━━━━━━━━━━━━━━\nهنوز دوستی نداری.\nبعد از هر چت ناشناس می‌تونی "
                "«درخواست دوستی» بدی."), [[b("🎲 چت ناشناس", "s:home", PRIMARY)], [b("🏠 منو", "m:home")]]
    buttons = [b(("🟢 " if r["state"] == "chat" else "") + {"male": "👨", "female": "👩"}.get(r["gender"], "👤")
                 + " " + (esc(r["name"], 18) or str(r["id"])), f"f:v:{r['id']}") for r in rows_db]
    rows = chunk(buttons, 2)
    nav = pager("f:l:", page, total, PER_PAGE)
    if nav:
        rows.append(nav)
    rows.append([b("🏠 منو", "m:home")])
    return f"👥 **دوستان** ({fa(total)} نفر)\n━━━━━━━━━━━━━━\nیکی رو انتخاب کن:", rows


@router.callback_query(F.data == "f:home")
async def cb_home(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if not await ensure_onboarded(app, event, user):
        return
    await repo.set_step(app, user["id"], "")
    text, rows = await friends_page(app, user["id"], 0)
    await show(app, event, text, rows)


@router.callback_query(F.data.startswith("f:l:"))
async def cb_list(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    page = int((event.data or "f:l:0").split(":")[2])
    text, rows = await friends_page(app, user["id"], max(0, page))
    await show(app, event, text, rows)


async def _friend(app: App, user: dict, event: CallbackQuery, fid: str) -> dict | None:
    if not fid.isdigit() or not await repo.are_friends(app, user["id"], int(fid)):
        await toast(event, "این کاربر دیگه در لیست دوستانت نیست", True)
        return None
    return await repo.get_user(app, int(fid))


@router.callback_query(F.data.startswith("f:v:"))
async def cb_view(event: CallbackQuery, app: App, user: dict) -> None:
    friend = await _friend(app, user, event, (event.data or "").split(":")[2])
    if not friend:
        return
    await toast(event)
    await app.delete(user["id"], event.message.message_id if event.message else None)
    await send_profile_card(app, user["id"], friend, [
        [b("💬 ارسال پیام", f"f:m:{friend['id']}", PRIMARY), b("🗣 درخواست چت", f"f:c:{friend['id']}", SUCCESS)],
        [b("🗑 حذف دوست", f"f:rm:{friend['id']}", DANGER), b("🔙 لیست", "f:home")],
    ])


@router.callback_query(F.data.startswith("f:rm:"))
async def cb_remove(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    friend = await _friend(app, user, event, parts[2])
    if not friend:
        return
    if len(parts) > 3 and parts[3] == "ok":
        await app.db.execute("DELETE FROM friends WHERE (user_id = ? AND friend_id = ?) OR (user_id = ? AND friend_id = ?)",
                             (user["id"], friend["id"], friend["id"], user["id"]))
        await toast(event, "از دوستان حذف شد")
        text, rows = await friends_page(app, user["id"], 0)
        await app.delete(user["id"], event.message.message_id if event.message else None)
        return await app.send(user["id"], text, rows)
    await toast(event)
    await app.send(user["id"], f"حذف {esc(friend['name'], 30)} از دوستان؟",
                   [[b("✅ بله", f"f:rm:{friend['id']}:ok", DANGER), b("↩️ نه", "x:del")]])


# ---------------------------------------------------------------- پیام مستقیم
@router.callback_query(F.data.startswith("f:m:"))
async def cb_msg(event: CallbackQuery, app: App, user: dict) -> None:
    friend = await _friend(app, user, event, (event.data or "").split(":")[2])
    if not friend:
        return
    if user["state"] != "idle":
        return await toast(event, "اول گفتگوی فعلی را تمام کن", True)
    await toast(event)
    await repo.set_step(app, user["id"], f"fmsg:{friend['id']}")
    await app.send(user["id"], f"💬 پیامت برای {esc(friend['name'], 30)} رو بنویس یا بفرست:",
                   [[b("❌ انصراف", "x:cancel", DANGER)]])


@router.message(Step("fmsg"))
async def in_msg(message: Message, app: App, user: dict, step_arg: str) -> None:
    uid = user["id"]
    if not step_arg.isdigit() or not await repo.are_friends(app, uid, int(step_arg)):
        await repo.set_step(app, uid, "")
        return await app.send(uid, "این کاربر دوست تو نیست.", [[b("🏠 منو", "m:home")]])
    kind = kind_of(message)
    if kind in ("unknown", "invoice", "successful_payment", "new_chat_members", "left_chat_member"):
        return
    fid = int(step_arg)
    if await repo.has_blocked(app, fid, uid):
        await repo.set_step(app, uid, "")
        return await app.send(uid, "ارسال ممکن نیست.")
    head = f"💌 **پیام از دوستت {esc(user['name'], 30)}**"
    rows = [[b("↩️ پاسخ", f"f:m:{uid}", PRIMARY)]]
    if kind == "text":
        mid = await app.send(fid, f"{head}\n━━━━━━━━━━━━━━\n{message.text}", rows)
    else:
        header = await app.send(fid, head, rows)
        mid = (await app.copy(fid, message.chat.id, message.message_id, reply_to=header)) if header else None
    await repo.set_step(app, uid, "")
    await app.send(uid, "✅ ارسال شد." if mid else "⚠️ ارسال نشد.", [[b("👥 دوستان", "f:home"), b("🏠 منو", "m:home")]])


# ---------------------------------------------------------------- درخواست چت
@router.callback_query(F.data.startswith("f:c:"))
async def cb_chat_request(event: CallbackQuery, app: App, user: dict) -> None:
    friend = await _friend(app, user, event, (event.data or "").split(":")[2])
    if not friend:
        return
    if user["state"] != "idle" or friend["state"] != "idle":
        return await toast(event, "یکی از شما الان درگیر جستجو یا گفتگوست", True)
    pending = await app.db.one(
        "SELECT 1 FROM friend_requests WHERE from_id = ? AND to_id = ? AND kind = 'chat' AND status = 'pending' AND expires_at > ?",
        (user["id"], friend["id"], now()))
    if pending:
        return await toast(event, "درخواست قبلی هنوز فعال است", True)
    rid = await app.db.execute(
        "INSERT INTO friend_requests(from_id, to_id, kind, status, created_at, expires_at) VALUES(?,?,?,?,?,?)",
        (user["id"], friend["id"], "chat", "pending", now(), now() + CHAT_REQUEST_TTL))
    sent = await app.send(friend["id"], f"🗣 **درخواست چت**\n━━━━━━━━━━━━━━\n{esc(user['name'], 30)} می‌خواد باهات چت کنه.",
                          [[b("✅ بپذیر", f"fc:ok:{rid}", SUCCESS), b("❌ رد", f"fc:no:{rid}", DANGER)]])
    await toast(event, "درخواست چت ارسال شد" if sent else "ارسال نشد", not sent)


@router.callback_query(F.data.startswith("fc:"))
async def cb_chat_answer(event: CallbackQuery, app: App, user: dict) -> None:
    _, action, rid = (event.data or "").split(":")[:3]
    req = await app.db.one("SELECT * FROM friend_requests WHERE id = ? AND to_id = ? AND kind = 'chat'",
                           (int(rid), user["id"]))
    if not req or req["status"] != "pending" or req["expires_at"] < now():
        return await toast(event, "این درخواست منقضی شده", True)
    await app.delete(user["id"], event.message.message_id if event.message else None)
    if action == "no":
        await app.db.execute("UPDATE friend_requests SET status = 'rejected' WHERE id = ?", (req["id"],))
        await app.send(req["from_id"], "😕 دوستت درخواست چت رو نپذیرفت.")
        return await toast(event, "رد شد")
    if await repo.is_blocked_pair(app, req["from_id"], user["id"]):
        return await toast(event, "ممکن نیست", True)
    chat = await matching.create_direct_chat(app, req["from_id"], user["id"], "friend")
    if not chat:
        return await toast(event, "یکی از شما الان در گفتگو یا جستجوست", True)
    await app.db.execute("UPDATE friend_requests SET status = 'accepted' WHERE id = ?", (req["id"],))
    await toast(event, "گفتگو شروع شد")
    await matching.announce(app, chat)
