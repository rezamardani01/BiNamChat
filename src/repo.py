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
"""دسترسی به داده‌های کاربران، کیف پول، بلاک‌ها و دوستان."""
from __future__ import annotations

import json
import sqlite3
from typing import Any

from .core import App
from .util import esc, now, rand_code

USER_FIELDS = {
    "name", "username", "link", "coins", "step", "step_data", "gender", "age", "province", "city",
    "bio", "photo", "onboard", "terms", "premium_until", "banned", "ban_reason", "suspended_until",
    "anon_on", "seen_notify", "state", "search_type", "same_age", "same_city", "referrer_id",
    "referral_paid", "bot_blocked", "menu_mid", "last_seen", "chats_count", "msgs_sent", "warns",
}


async def get_user(app: App, uid: int) -> dict | None:
    return await app.db.one("SELECT * FROM users WHERE id = ?", (uid,))


async def update_user(app: App, uid: int, **fields: Any) -> None:
    if not fields:
        return
    bad = set(fields) - USER_FIELDS
    if bad:
        raise KeyError(f"unknown user fields: {bad}")
    cols = ", ".join(f"{k} = ?" for k in fields)
    await app.db.execute(f"UPDATE users SET {cols} WHERE id = ?", (*fields.values(), uid))


async def set_step(app: App, uid: int, step: str = "", data: dict | None = None) -> None:
    await update_user(app, uid, step=step, step_data=json.dumps(data, ensure_ascii=False) if data else "")


def is_premium(user: dict | None) -> bool:
    return bool(user) and int(user["premium_until"] or 0) > now()


def is_suspended(user: dict) -> bool:
    return int(user["suspended_until"] or 0) > now()


async def new_code(app: App) -> str:
    while True:
        code = rand_code(8)
        if not await app.db.one("SELECT 1 FROM users WHERE code = ? OR link = ?", (code, code)):
            return code


async def ensure_user(app: App, tg_user: Any, referrer: int | None = None) -> tuple[dict, bool]:
    """کاربر را می‌خواند یا می‌سازد. (کاربر، تازه‌ساخته‌شده؟)"""
    user = await get_user(app, tg_user.id)
    name = esc(tg_user.full_name or str(tg_user.id), 40) or str(tg_user.id)
    username = tg_user.username or None
    if user:
        patch: dict[str, Any] = {}
        if now() - int(user["last_seen"] or 0) > 30:
            patch["last_seen"] = now()
        if username != user["username"]:
            patch["username"] = username
        if user["bot_blocked"]:
            patch["bot_blocked"] = 0
        await update_user(app, tg_user.id, **patch)
        user.update(patch)
        return user, False

    if referrer == tg_user.id or referrer is not None and not await get_user(app, referrer):
        referrer = None
    ts = now()
    for _ in range(5):
        try:
            await app.db.execute(
                "INSERT INTO users(id, name, username, code, joined_at, last_seen, referrer_id) "
                "VALUES(?,?,?,?,?,?,?)",
                (tg_user.id, name, username, await new_code(app), ts, ts, referrer),
            )
            break
        except sqlite3.IntegrityError:
            existing = await get_user(app, tg_user.id)
            if existing:
                return existing, False
    initial = app.settings.int("initial_coins")
    if initial > 0:
        await add_coins(app, tg_user.id, initial, "welcome", note="هدیه ثبت‌نام")
    user = await get_user(app, tg_user.id)
    assert user is not None
    return user, True


async def add_coins(app: App, uid: int, delta: int, kind: str, *, ref: str | None = None,
                    admin_id: int | None = None, note: str | None = None,
                    allow_negative: bool = False) -> int | None:
    """تغییر اتمیک موجودی؛ موجودی جدید یا None اگر موجودی کافی نباشد."""
    async with app.db.tx() as tx:
        bal = await tx.val("SELECT coins FROM users WHERE id = ?", (uid,))
        if bal is None:
            return None
        new = int(bal) + int(delta)
        if new < 0 and not allow_negative:
            return None
        await tx.execute("UPDATE users SET coins = ? WHERE id = ?", (new, uid))
        await tx.execute(
            "INSERT INTO wallet_tx(user_id, delta, balance, kind, ref, admin_id, note, created_at) "
            "VALUES(?,?,?,?,?,?,?,?)",
            (uid, delta, new, kind, ref, admin_id, (note or "")[:200], now()),
        )
        return new


async def grant_premium(app: App, uid: int, days: int) -> int:
    """روز به اشتراک اضافه می‌کند (منفی = کم‌کردن). زمان پایان جدید را برمی‌گرداند."""
    async with app.db.tx() as tx:
        cur = int(await tx.val("SELECT premium_until FROM users WHERE id = ?", (uid,), 0))
        base = max(cur, now()) if days > 0 else cur
        until = max(0, base + days * 86400)
        if days < 0 and until < now():
            until = 0
        await tx.execute("UPDATE users SET premium_until = ? WHERE id = ?", (until, uid))
        return until


async def is_blocked_pair(app: App, a: int, b: int) -> bool:
    return await app.db.one(
        "SELECT 1 FROM blocks WHERE (user_id = ? AND blocked_id = ?) OR (user_id = ? AND blocked_id = ?)",
        (a, b, b, a),
    ) is not None


async def has_blocked(app: App, owner: int, other: int) -> bool:
    return await app.db.one("SELECT 1 FROM blocks WHERE user_id = ? AND blocked_id = ?", (owner, other)) is not None


async def block(app: App, owner: int, other: int) -> None:
    await app.db.execute("INSERT OR IGNORE INTO blocks(user_id, blocked_id, created_at) VALUES(?,?,?)",
                         (owner, other, now()))


async def unblock(app: App, owner: int, other: int) -> None:
    await app.db.execute("DELETE FROM blocks WHERE user_id = ? AND blocked_id = ?", (owner, other))


async def are_friends(app: App, a: int, b: int) -> bool:
    return await app.db.one("SELECT 1 FROM friends WHERE user_id = ? AND friend_id = ?", (a, b)) is not None


async def find_user(app: App, query: str) -> dict | None:
    """جستجو با شناسه عددی، @username، لینک یا کد."""
    q = query.strip().lstrip("@")
    if not q:
        return None
    if q.lstrip("-").isdigit():
        found = await get_user(app, int(q))
        if found:
            return found
    return await app.db.one(
        "SELECT * FROM users WHERE lower(username) = lower(?) OR link = ? OR code = ? LIMIT 1", (q, q, q)
    )


def display(user: dict | None, with_id: bool = False) -> str:
    if not user:
        return "—"
    name = esc(user["name"], 30) or str(user["id"])
    return f"{name} ({user['id']})" if with_id else name


GENDER_LABEL = {"male": "👨 پسر", "female": "👩 دختر"}
GENDER_WORD = {"male": "پسر", "female": "دختر"}


def gender_text(value: str | None) -> str:
    return GENDER_LABEL.get(value or "", "—")
