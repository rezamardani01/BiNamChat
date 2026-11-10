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
"""موتور اتصال چت ناشناس: صف، تطبیق، پایان چت و پاک‌سازی‌های دوره‌ای."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from baleropy import Button
from baleropy.types import ReplyKeyboardRemove

from . import repo
from .core import App
from .ui import DANGER, PRIMARY, SUCCESS, b
from .util import age_group, duration, fa, now

log = logging.getLogger("binam.match")

KB_END = "🔚 پایان چت"
KB_NEXT = "⏭ نفر بعدی"
KB_PROFILE = "👤 پروفایل مخاطب"
KB_TEXTS = {KB_END, KB_NEXT, KB_PROFILE}


def chat_keyboard() -> list[list[Any]]:
    return [[Button.text(KB_PROFILE), Button.text(KB_NEXT)], [Button.text(KB_END)]]


def search_cost(app: App, user: dict, stype: str, same_age: int, same_city: int) -> int:
    if repo.is_premium(user) and app.settings.on("premium_free_search"):
        return 0
    cost = 0
    if stype in ("male", "female"):
        cost += app.settings.int("cost_gender")
    if same_age:
        cost += app.settings.int("cost_age")
    if same_city:
        cost += app.settings.int("cost_city")
    return cost


def describe_search(stype: str, same_age: int, same_city: int) -> str:
    kind = {"random": "شانسی", "male": "پسر", "female": "دختر"}.get(stype, "شانسی")
    extra = []
    if same_age:
        extra.append("هم‌سن")
    if same_city:
        extra.append("همشهری")
    return kind + (" • " + " و ".join(extra) if extra else "")


async def heal(app: App, user: dict) -> dict:
    """وضعیت ناسازگار کاربر (گیر کردن در جستجو/چت) را ترمیم می‌کند."""
    fresh = await app.db.one("SELECT * FROM users WHERE id = ?", (user["id"],)) or user
    uid = fresh["id"]
    if fresh["state"] == "chat" and not await active_chat(app, uid):
        await app.db.execute("UPDATE users SET state = 'idle' WHERE id = ?", (uid,))
        fresh["state"] = "idle"
    elif fresh["state"] == "searching" and not await app.db.one("SELECT 1 FROM queue WHERE user_id = ?", (uid,)):
        await app.db.execute("UPDATE users SET state = 'idle' WHERE id = ?", (uid,))
        fresh["state"] = "idle"
    elif fresh["state"] == "idle" and await active_chat(app, uid):
        await app.db.execute("UPDATE users SET state = 'chat' WHERE id = ?", (uid,))
        fresh["state"] = "chat"
    return fresh


# ---------------------------------------------------------------- صف
async def enqueue(app: App, user: dict, msg_id: int | None) -> None:
    prio = 1 if repo.is_premium(user) and app.settings.on("premium_priority") else 0
    async with app.db.tx() as tx:
        await tx.execute(
            "INSERT OR REPLACE INTO queue(user_id, queued_at, search_type, same_age, same_city, priority, msg_id) "
            "VALUES(?,?,?,?,?,?,?)",
            (user["id"], now(), user["search_type"], user["same_age"], user["same_city"], prio, msg_id),
        )
        await tx.execute("UPDATE users SET state = 'searching' WHERE id = ?", (user["id"],))


async def dequeue(app: App, uid: int, new_state: str = "idle") -> dict | None:
    async with app.db.tx() as tx:
        row = await tx.one("SELECT * FROM queue WHERE user_id = ?", (uid,))
        await tx.execute("DELETE FROM queue WHERE user_id = ?", (uid,))
        await tx.execute("UPDATE users SET state = ? WHERE id = ? AND state = 'searching'", (new_state, uid))
    return row


def _compatible(me: dict, other: dict, blocked: set[int], rejected: set[int]) -> bool:
    if other["user_id"] in blocked or other["user_id"] in rejected:
        return False
    if other["banned"] or int(other["suspended_until"] or 0) > now():
        return False
    # جنسیت درخواستی دوطرفه
    if me["search_type"] != "random" and me["search_type"] != other["gender"]:
        return False
    if other["search_type"] != "random" and other["search_type"] != me["gender"]:
        return False
    g_me, g_ot = age_group(me["age"]), age_group(other["age"])
    if (me["same_age"] or other["same_age"]) and g_me != g_ot:
        return False
    if me["same_city"] or other["same_city"]:
        if not (me["province"] and me["city"] and me["province"] == other["province"] and me["city"] == other["city"]):
            return False
    return True


_Q_SQL = (
    "SELECT q.user_id, q.queued_at, q.search_type, q.same_age, q.same_city, q.priority, q.msg_id, "
    "u.gender, u.age, u.province, u.city, u.premium_until, u.banned, u.suspended_until "
    "FROM queue q JOIN users u ON u.id = q.user_id"
)


async def try_match(app: App, uid: int) -> dict | None:
    """برای کاربر داخل صف شریک پیدا می‌کند و گفتگو می‌سازد (اعلان جدا انجام می‌شود)."""
    poor: list[int] = []
    result: dict | None = None
    async with app.match_lock:
        me = await app.db.one(_Q_SQL + " WHERE q.user_id = ?", (uid,))
        if not me:
            return None
        blocked = {r["x"] for r in await app.db.all(
            "SELECT blocked_id AS x FROM blocks WHERE user_id = ? UNION SELECT user_id FROM blocks WHERE blocked_id = ?",
            (uid, uid))}
        limit = now() - app.settings.int("rematch_cooldown") * 60
        rejected = {r["x"] for r in await app.db.all(
            "SELECT other_id AS x FROM rejections WHERE user_id = ? AND created_at > ? "
            "UNION SELECT user_id FROM rejections WHERE other_id = ? AND created_at > ?",
            (uid, limit, uid, limit))}
        cands = await app.db.all(_Q_SQL + " WHERE q.user_id != ? ORDER BY q.priority DESC, q.queued_at LIMIT 400", (uid,))
        for cand in cands:
            if not _compatible(me, cand, blocked, rejected) or not _compatible(cand, me, set(), set()):
                continue
            status, chat = await _pair(app, me, cand)
            if status == "ok":
                result = chat
                break
            if status == "me_poor":
                poor.append(uid)
                break
            if status == "cand_poor":
                poor.append(cand["user_id"])
            if status == "gone":
                continue
    for p in poor:
        await dequeue(app, p)
        await app.send(p, "🪙 موجودی سکه‌ات برای این جستجو کافی نیست.\n"
                          "از «فروشگاه» سکه بگیر یا نوع جستجو را عوض کن.",
                       [[b("🛍 فروشگاه", "w:home", PRIMARY)], [b("🏠 منو", "m:home")]])
    return result


async def _charge(tx: Any, uid: int, amount: int, ref: str) -> bool:
    if amount <= 0:
        return True
    bal = int(await tx.val("SELECT coins FROM users WHERE id = ?", (uid,), 0))
    if bal < amount:
        return False
    await tx.execute("UPDATE users SET coins = ? WHERE id = ?", (bal - amount, uid))
    await tx.execute(
        "INSERT INTO wallet_tx(user_id, delta, balance, kind, ref, note, created_at) VALUES(?,?,?,?,?,?,?)",
        (uid, -amount, bal - amount, "search", ref, "هزینه جستجو", now()),
    )
    return True


async def _pair(app: App, a: dict, b_: dict) -> tuple[str, dict | None]:
    async with app.db.tx() as tx:
        ra = await tx.one("SELECT * FROM queue WHERE user_id = ?", (a["user_id"],))
        rb = await tx.one("SELECT * FROM queue WHERE user_id = ?", (b_["user_id"],))
        if not ra or not rb:
            return "gone", None
        ua = await tx.one("SELECT * FROM users WHERE id = ?", (a["user_id"],))
        ub = await tx.one("SELECT * FROM users WHERE id = ?", (b_["user_id"],))
        if not ua or not ub or ua["state"] != "searching" or ub["state"] != "searching":
            return "gone", None
        cost_a = search_cost(app, ua, ra["search_type"], ra["same_age"], ra["same_city"])
        cost_b = search_cost(app, ub, rb["search_type"], rb["same_age"], rb["same_city"])
        if ua["coins"] < cost_a:
            return "me_poor", None
        if ub["coins"] < cost_b:
            return "cand_poor", None
        ts = now()
        cid = await tx.execute(
            "INSERT INTO chats(a, b, kind, status, started_at, last_activity) VALUES(?,?,?,?,?,?)",
            (ua["id"], ub["id"], "random", "active", ts, ts),
        )
        await _charge(tx, ua["id"], cost_a, f"chat:{cid}")
        await _charge(tx, ub["id"], cost_b, f"chat:{cid}")
        await tx.execute("DELETE FROM queue WHERE user_id IN (?, ?)", (ua["id"], ub["id"]))
        await tx.execute(
            "UPDATE users SET state = 'chat', step = '', step_data = '', chats_count = chats_count + 1 WHERE id IN (?, ?)",
            (ua["id"], ub["id"]),
        )
        chat = await tx.one("SELECT * FROM chats WHERE id = ?", (cid,))
        assert chat is not None
        chat["_msgs"] = {ua["id"]: ra["msg_id"], ub["id"]: rb["msg_id"]}
        chat["_cost"] = {ua["id"]: cost_a, ub["id"]: cost_b}
        return "ok", chat


async def create_direct_chat(app: App, a: int, b_: int, kind: str = "friend") -> dict | None:
    """گفتگوی مستقیم (بین دوستان) بدون صف."""
    async with app.db.tx() as tx:
        ua = await tx.one("SELECT * FROM users WHERE id = ?", (a,))
        ub = await tx.one("SELECT * FROM users WHERE id = ?", (b_,))
        if not ua or not ub or ua["state"] == "chat" or ub["state"] == "chat":
            return None
        ts = now()
        cid = await tx.execute(
            "INSERT INTO chats(a, b, kind, status, started_at, last_activity) VALUES(?,?,?,?,?,?)",
            (a, b_, kind, "active", ts, ts))
        await tx.execute("DELETE FROM queue WHERE user_id IN (?, ?)", (a, b_))
        await tx.execute("UPDATE users SET state = 'chat', step = '', step_data = '', chats_count = chats_count + 1 WHERE id IN (?, ?)", (a, b_))
        chat = await tx.one("SELECT * FROM chats WHERE id = ?", (cid,))
        assert chat is not None
        chat["_msgs"] = {}
        chat["_cost"] = {}
        return chat


def partner_line(user: dict) -> str:
    bits = [repo.GENDER_WORD.get(user["gender"] or "", "—")]
    if user["age"]:
        bits.append(f"{fa(user['age'])} ساله")
    if user["province"]:
        bits.append(f"از {user['province']}")
    return "، ".join(bits)


def chat_controls() -> list[list[Any]]:
    return [
        [b("👤 پروفایل", "c:prof", PRIMARY), b("🚨 گزارش", "c:rep", DANGER)],
        [b("🚫 بلاک", "c:blk"), b("🔚 پایان چت", "c:end", DANGER)],
    ]


async def announce(app: App, chat: dict) -> None:
    """پیام «وصل شدی» را برای هر دو طرف می‌فرستد."""
    app.spawn(app.event(
        f"🔗 اتصال چت #{chat['id']}\n👤 {chat['a']} ↔ {chat['b']}\n"
        f"📂 نوع: {'دوستان' if chat['kind'] == 'friend' else 'تصادفی'}", "chats"))
    for uid, other in ((chat["a"], chat["b"]), (chat["b"], chat["a"])):
        mid = chat.get("_msgs", {}).get(uid)
        if mid:
            await app.delete(uid, mid)
        partner = await repo.get_user(app, other)
        cost = chat.get("_cost", {}).get(uid, 0)
        kind_line = "🤝 گفتگو با دوستت شروع شد" if chat["kind"] == "friend" else "🎉 به یه ناشناس وصل شدی!"
        text = (f"{kind_line}\n"
                f"━━━━━━━━━━━━━━\n"
                f"👤 مخاطب: {partner_line(partner) if partner else '—'}\n"
                + (f"🪙 {fa(cost)} سکه کسر شد\n" if cost else "")
                + "\n💬 همین الان شروع کن و یه سلام بنویس!\n"
                + "🔒 هویتت مخفیه؛ شماره و آیدی نفرست.")
        await app.send(uid, text, chat_controls())
        await app.send(uid, "👇 کلید میانبر چت فعال شد", chat_keyboard())


async def search_and_announce(app: App, uid: int) -> bool:
    chat = await try_match(app, uid)
    if chat:
        await announce(app, chat)
        return True
    return False


# ---------------------------------------------------------------- پایان چت
async def active_chat(app: App, uid: int) -> dict | None:
    return await app.db.one(
        "SELECT * FROM chats WHERE status = 'active' AND (a = ? OR b = ?) ORDER BY id DESC LIMIT 1", (uid, uid))


def other_of(chat: dict, uid: int) -> int:
    return chat["b"] if chat["a"] == uid else chat["a"]


def ended_controls(chat_id: int, friends: bool, kind: str) -> list[list[Any]]:
    rows = []
    if not friends:
        rows.append([b("➕ درخواست دوستی", f"e:fr:{chat_id}", SUCCESS)])
    rows.append([b("🚨 گزارش", f"e:rep:{chat_id}", DANGER), b("🚫 بلاک", f"e:blk:{chat_id}")])
    rows.append([b("🔍 چت جدید", "s:home", PRIMARY), b("🏠 منو", "m:home")])
    return rows


async def end_chat(app: App, chat_id: int, by: int | None, reason: str = "user", *, notify: bool = True) -> dict | None:
    async with app.db.tx() as tx:
        chat = await tx.one("SELECT * FROM chats WHERE id = ? AND status = 'active'", (chat_id,))
        if not chat:
            return None
        ts = now()
        await tx.execute("UPDATE chats SET status = 'ended', ended_at = ?, ended_by = ? WHERE id = ?", (ts, by, chat_id))
        await tx.execute("UPDATE users SET state = 'idle' WHERE id IN (?, ?) AND state = 'chat'", (chat["a"], chat["b"]))
        if chat["kind"] == "random":
            for x, y in ((chat["a"], chat["b"]), (chat["b"], chat["a"])):
                await tx.execute("INSERT OR REPLACE INTO rejections(user_id, other_id, created_at) VALUES(?,?,?)", (x, y, ts))
        await tx.execute("DELETE FROM msgmap WHERE chat_id = ?", (chat_id,))
    chat["ended_at"] = now()
    who = "سیستم/مدیریت" if by is None else str(by)
    app.spawn(app.event(
        f"🔚 پایان چت #{chat_id}\n👤 {chat['a']} ↔ {chat['b']}\n"
        f"⏱ مدت: {duration(chat['ended_at'] - chat['started_at'])}\n"
        f"💬 پیام‌ها: {fa(chat['a_msgs'])} و {fa(chat['b_msgs'])}\n🙋 پایان‌دهنده: {who} ({reason})", "chats"))
    if notify:
        length = duration(chat["ended_at"] - chat["started_at"])
        for uid in (chat["a"], chat["b"]):
            if reason == "user":
                head = "🔚 گفتگو تموم شد." if by == uid else "🔚 مخاطب گفتگو را پایان داد."
            elif reason == "idle":
                head = "⌛️ به‌دلیل بی‌فعالیتی، گفتگو به‌طور خودکار پایان یافت."
            elif reason == "admin":
                head = "🛡 گفتگو توسط مدیریت پایان یافت."
            elif reason == "gone":
                head = "⚠️ مخاطب در دسترس نیست؛ گفتگو پایان یافت."
            else:
                head = "🔚 گفتگو پایان یافت."
            friends = await repo.are_friends(app, uid, other_of(chat, uid))
            await app.send(uid, f"{head}\n⏱ مدت: {length}", ReplyKeyboardRemove())
            await app.send(uid, "😊 چطور بود؟ می‌تونی مخاطب رو دوست خودت کنی، گزارش بدی یا یه چت جدید شروع کنی:", ended_controls(chat_id, friends, chat["kind"]))
    return chat


# ---------------------------------------------------------------- حلقه‌های پس‌زمینه
async def _expire_queue(app: App) -> None:
    timeout = app.settings.int("queue_timeout") * 60
    for row in await app.db.all("SELECT * FROM queue WHERE queued_at < ?", (now() - timeout,)):
        await dequeue(app, row["user_id"])
        await app.delete(row["user_id"], row["msg_id"])
        await app.send(
            row["user_id"],
            "😕 **کسی پیدا نشد**\n━━━━━━━━━━━━━━\n"
            f"{duration(timeout)} گشتیم ولی فعلاً هم‌صحبتی که با شرایطت جور باشه آنلاین نبود.\n\n"
            "💡 فیلتر هم‌سن/همشهری یا انتخاب دختر/پسر رو خاموش کن و جستجوی «شانسی» رو امتحان کن؛ "
            "شانس وصل شدنت خیلی بیشتر می‌شه!",
            [[b("🔄 جستجوی دوباره", "s:home", PRIMARY)], [b("🏠 منوی اصلی", "m:home")]])


async def _end_idle(app: App) -> None:
    idle = app.settings.int("chat_idle") * 60
    if not idle:
        return
    for chat in await app.db.all("SELECT id FROM chats WHERE status = 'active' AND last_activity < ?", (now() - idle,)):
        await end_chat(app, chat["id"], None, "idle")


async def _sweep_queue(app: App) -> None:
    for row in await app.db.all("SELECT user_id FROM queue ORDER BY queued_at LIMIT 60"):
        await search_and_announce(app, row["user_id"])


async def _housekeeping(app: App) -> None:
    await app.db.execute("DELETE FROM rejections WHERE created_at < ?", (now() - 86400,))
    await app.db.execute("DELETE FROM friend_requests WHERE status != 'pending' AND created_at < ?", (now() - 7 * 86400,))
    await app.db.execute("DELETE FROM msgmap WHERE chat_id IN (SELECT id FROM chats WHERE status != 'active')")


async def cleanup_loop(app: App) -> None:
    """انقضای صف، چت‌های بی‌فعالیت، تلاش دوباره برای اتصال و پاک‌سازی رکوردهای قدیمی."""
    tick = 0
    while True:
        await asyncio.sleep(10)
        tick += 1
        jobs = [_expire_queue, _end_idle]
        if tick % 2 == 0:
            jobs.append(_sweep_queue)
        if tick % 360 == 0:
            jobs.append(_housekeeping)
        for job in jobs:
            try:
                await job(app)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                await app.error(f"cleanup:{job.__name__}", repr(exc))


async def recover_state(app: App) -> None:
    """پس از ری‌استارت وضعیت‌های ناسازگار را ترمیم می‌کند."""
    await app.db.execute(
        "UPDATE users SET state = 'idle' WHERE state = 'searching' AND id NOT IN (SELECT user_id FROM queue)")
    await app.db.execute(
        "UPDATE users SET state = 'idle' WHERE state = 'chat' AND id NOT IN "
        "(SELECT a FROM chats WHERE status = 'active' UNION SELECT b FROM chats WHERE status = 'active')")
    await app.db.execute("DELETE FROM queue WHERE user_id IN (SELECT id FROM users WHERE state != 'searching')")
