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
"""لایه دیتابیس SQLite (غیرهمزمان با aiosqlite)."""
from __future__ import annotations

import asyncio
import sqlite3
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator, Iterable

import aiosqlite

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL DEFAULT '',
    username TEXT,
    code TEXT UNIQUE,
    link TEXT UNIQUE,
    coins INTEGER NOT NULL DEFAULT 0,
    step TEXT NOT NULL DEFAULT '',
    step_data TEXT NOT NULL DEFAULT '',
    gender TEXT,
    age INTEGER,
    province TEXT,
    city TEXT,
    bio TEXT,
    photo TEXT,
    onboard TEXT NOT NULL DEFAULT 'gender',
    terms INTEGER NOT NULL DEFAULT 0,
    premium_until INTEGER NOT NULL DEFAULT 0,
    banned INTEGER NOT NULL DEFAULT 0,
    ban_reason TEXT,
    suspended_until INTEGER NOT NULL DEFAULT 0,
    anon_on INTEGER NOT NULL DEFAULT 1,
    seen_notify INTEGER NOT NULL DEFAULT 1,
    state TEXT NOT NULL DEFAULT 'idle',
    search_type TEXT NOT NULL DEFAULT 'random',
    same_age INTEGER NOT NULL DEFAULT 0,
    same_city INTEGER NOT NULL DEFAULT 0,
    referrer_id INTEGER,
    referral_paid INTEGER NOT NULL DEFAULT 0,
    bot_blocked INTEGER NOT NULL DEFAULT 0,
    menu_mid INTEGER,
    joined_at INTEGER NOT NULL,
    last_seen INTEGER NOT NULL DEFAULT 0,
    chats_count INTEGER NOT NULL DEFAULT 0,
    msgs_sent INTEGER NOT NULL DEFAULT 0,
    warns INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_users_joined ON users(joined_at);
CREATE INDEX IF NOT EXISTS ix_users_seen ON users(last_seen);
CREATE INDEX IF NOT EXISTS ix_users_premium ON users(premium_until);
CREATE INDEX IF NOT EXISTS ix_users_referrer ON users(referrer_id);

CREATE TABLE IF NOT EXISTS queue (
    user_id INTEGER PRIMARY KEY,
    queued_at INTEGER NOT NULL,
    search_type TEXT NOT NULL DEFAULT 'random',
    same_age INTEGER NOT NULL DEFAULT 0,
    same_city INTEGER NOT NULL DEFAULT 0,
    priority INTEGER NOT NULL DEFAULT 0,
    msg_id INTEGER
);

CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    a INTEGER NOT NULL,
    b INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'random',
    status TEXT NOT NULL DEFAULT 'active',
    started_at INTEGER NOT NULL,
    last_activity INTEGER NOT NULL,
    ended_at INTEGER,
    ended_by INTEGER,
    a_msgs INTEGER NOT NULL DEFAULT 0,
    b_msgs INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS ix_chats_a ON chats(a, status);
CREATE INDEX IF NOT EXISTS ix_chats_b ON chats(b, status);
CREATE INDEX IF NOT EXISTS ix_chats_status ON chats(status, last_activity);

CREATE TABLE IF NOT EXISTS msgmap (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    mid INTEGER NOT NULL,
    peer_mid INTEGER NOT NULL,
    PRIMARY KEY (chat_id, user_id, mid)
);

CREATE TABLE IF NOT EXISTS blocks (
    user_id INTEGER NOT NULL,
    blocked_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, blocked_id)
);
CREATE INDEX IF NOT EXISTS ix_blocks_blocked ON blocks(blocked_id);

CREATE TABLE IF NOT EXISTS rejections (
    user_id INTEGER NOT NULL,
    other_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, other_id)
);

CREATE TABLE IF NOT EXISTS friends (
    user_id INTEGER NOT NULL,
    friend_id INTEGER NOT NULL,
    created_at INTEGER NOT NULL,
    PRIMARY KEY (user_id, friend_id)
);

CREATE TABLE IF NOT EXISTS friend_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL,
    to_id INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'friend',
    status TEXT NOT NULL DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    expires_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_fr_to ON friend_requests(to_id, status);

CREATE TABLE IF NOT EXISTS anon_messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_id INTEGER NOT NULL,
    to_id INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'text',
    preview TEXT,
    dst_mid INTEGER,
    seen INTEGER NOT NULL DEFAULT 0,
    reply_to INTEGER,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_anon_to ON anon_messages(to_id, created_at);
CREATE INDEX IF NOT EXISTS ix_anon_from ON anon_messages(from_id, created_at);

CREATE TABLE IF NOT EXISTS reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER,
    source TEXT NOT NULL DEFAULT 'chat',
    reporter_id INTEGER NOT NULL,
    reported_id INTEGER NOT NULL,
    reason TEXT,
    status TEXT NOT NULL DEFAULT 'open',
    action TEXT,
    handled_by INTEGER,
    handled_at INTEGER,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_reports_status ON reports(status, created_at);
CREATE INDEX IF NOT EXISTS ix_reports_reported ON reports(reported_id);

CREATE TABLE IF NOT EXISTS wallet_tx (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    delta INTEGER NOT NULL,
    balance INTEGER NOT NULL,
    kind TEXT NOT NULL,
    ref TEXT,
    admin_id INTEGER,
    note TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_wtx_user ON wallet_tx(user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_wtx_kind ON wallet_tx(kind, created_at);

CREATE TABLE IF NOT EXISTS payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    payload TEXT NOT NULL UNIQUE,
    user_id INTEGER NOT NULL,
    kind TEXT NOT NULL,
    qty INTEGER NOT NULL,
    amount_irr INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    charge_id TEXT,
    created_at INTEGER NOT NULL,
    paid_at INTEGER
);
CREATE INDEX IF NOT EXISTS ix_pay_user ON payments(user_id, created_at);
CREATE INDEX IF NOT EXISTS ix_pay_status ON payments(status, paid_at);

CREATE TABLE IF NOT EXISTS gift_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT NOT NULL UNIQUE,
    reward_kind TEXT NOT NULL,
    reward_qty INTEGER NOT NULL,
    max_uses INTEGER NOT NULL,
    used INTEGER NOT NULL DEFAULT 0,
    expires_at INTEGER NOT NULL,
    active INTEGER NOT NULL DEFAULT 1,
    created_by INTEGER NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS gift_uses (
    gift_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    used_at INTEGER NOT NULL,
    PRIMARY KEY (gift_id, user_id)
);

CREATE TABLE IF NOT EXISTS channels (
    chat_id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    link TEXT NOT NULL DEFAULT '',
    added_at INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'normal',
    target INTEGER NOT NULL DEFAULT 0,
    joined INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'active',
    finished_at INTEGER
);

CREATE TABLE IF NOT EXISTS sponsor_seen (
    chat_id TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    first_missing_at INTEGER NOT NULL,
    joined_at INTEGER,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS admins (
    user_id INTEGER PRIMARY KEY,
    perms TEXT NOT NULL DEFAULT '',
    added_by INTEGER,
    added_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    target TEXT,
    details TEXT,
    created_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_audit_time ON audit(created_at);

CREATE TABLE IF NOT EXISTS errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS broadcasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    admin_id INTEGER NOT NULL,
    audience TEXT NOT NULL,
    mode TEXT NOT NULL DEFAULT 'copy',
    preview TEXT,
    src_chat INTEGER NOT NULL,
    src_mid INTEGER NOT NULL,
    total INTEGER NOT NULL DEFAULT 0,
    sent INTEGER NOT NULL DEFAULT 0,
    failed INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    created_at INTEGER NOT NULL,
    finished_at INTEGER
);

CREATE TABLE IF NOT EXISTS tickets (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open',
    answer TEXT,
    answered_by INTEGER,
    created_at INTEGER NOT NULL,
    answered_at INTEGER
);
CREATE INDEX IF NOT EXISTS ix_tickets_status ON tickets(status, created_at);
"""


class Tx:
    """اتصال داخل تراکنش — فقط داخل `async with db.tx()` استفاده شود."""

    def __init__(self, conn: aiosqlite.Connection) -> None:
        self._c = conn

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        cur = await self._c.execute(sql, tuple(params))
        last = cur.lastrowid or 0
        rows = cur.rowcount
        await cur.close()
        self.rowcount = rows
        return last

    rowcount: int = 0

    async def one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        cur = await self._c.execute(sql, tuple(params))
        row = await cur.fetchone()
        await cur.close()
        return dict(row) if row else None

    async def all(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        cur = await self._c.execute(sql, tuple(params))
        rows = await cur.fetchall()
        await cur.close()
        return [dict(r) for r in rows]

    async def val(self, sql: str, params: Iterable[Any] = (), default: Any = None) -> Any:
        row = await self.one(sql, params)
        if not row:
            return default
        value = next(iter(row.values()))
        return default if value is None else value


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()
        self.rowcount = 0

    async def connect(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = await aiosqlite.connect(self.path, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA busy_timeout=10000")
        await self._conn.executescript(SCHEMA)
        # مهاجرت دیتابیس‌های قدیمی: ستون‌های جدید جدول channels
        async with self._conn.execute("PRAGMA table_info(channels)") as cur:
            cols = {row[1] for row in await cur.fetchall()}
        for col, ddl in (("kind", "TEXT NOT NULL DEFAULT 'normal'"), ("target", "INTEGER NOT NULL DEFAULT 0"),
                         ("joined", "INTEGER NOT NULL DEFAULT 0"), ("status", "TEXT NOT NULL DEFAULT 'active'"),
                         ("finished_at", "INTEGER")):
            if col not in cols:
                await self._conn.execute(f"ALTER TABLE channels ADD COLUMN {col} {ddl}")
        await self._conn.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Database is not connected")
        return self._conn

    async def execute(self, sql: str, params: Iterable[Any] = ()) -> int:
        async with self._lock:
            cur = await self.conn.execute(sql, tuple(params))
            last = cur.lastrowid or 0
            self.rowcount = cur.rowcount
            await cur.close()
            return last

    async def one(self, sql: str, params: Iterable[Any] = ()) -> dict | None:
        async with self._lock:
            cur = await self.conn.execute(sql, tuple(params))
            row = await cur.fetchone()
            await cur.close()
            return dict(row) if row else None

    async def all(self, sql: str, params: Iterable[Any] = ()) -> list[dict]:
        async with self._lock:
            cur = await self.conn.execute(sql, tuple(params))
            rows = await cur.fetchall()
            await cur.close()
            return [dict(r) for r in rows]

    async def val(self, sql: str, params: Iterable[Any] = (), default: Any = None) -> Any:
        row = await self.one(sql, params)
        if not row:
            return default
        value = next(iter(row.values()))
        return default if value is None else value

    @asynccontextmanager
    async def tx(self) -> AsyncIterator[Tx]:
        async with self._lock:
            await self.conn.execute("BEGIN IMMEDIATE")
            try:
                yield Tx(self.conn)
            except BaseException:
                await self.conn.execute("ROLLBACK")
                raise
            else:
                await self.conn.execute("COMMIT")

    async def backup_to(self, dest: str | Path) -> None:
        async with self._lock:
            await self.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            target = await aiosqlite.connect(dest)
            try:
                await self.conn.backup(target)
            finally:
                await target.close()
