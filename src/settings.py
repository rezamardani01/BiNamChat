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
"""تنظیمات پویا (در دیتابیس ذخیره می‌شود و از پنل مدیریت قابل تغییر است)."""
from __future__ import annotations

from dataclasses import dataclass

from .db import Database


@dataclass(frozen=True)
class Def:
    key: str
    kind: str  # bool | int | text
    default: str
    label: str
    group: str
    hint: str = ""
    min: int = 0
    max: int = 10**9


DEFS: list[Def] = [
    # --- عمومی ---
    Def("registration", "bool", "1", "ثبت‌نام کاربران جدید", "general"),
    Def("maintenance", "bool", "0", "حالت تعمیر و نگهداری", "general", "فقط مدیران می‌توانند از ربات استفاده کنند"),
    Def("force_join", "bool", "1", "عضویت اجباری در کانال‌ها", "general"),
    Def("support_enabled", "bool", "1", "پشتیبانی درون‌ربات", "general"),
    Def("anon_links", "bool", "1", "لینک پیام ناشناس", "general"),
    Def("specific_contact", "bool", "1", "ارسال به مخاطب خاص", "general"),
    # --- چت ناشناس ---
    Def("stranger_chat", "bool", "1", "چت ناشناس تصادفی", "chat"),
    Def("filter_contacts", "bool", "1", "جلوگیری از ارسال شماره/لینک/آیدی در چت", "chat"),
    Def("premium_media", "bool", "1", "ارسال رسانه فقط برای کاربر ویژه", "chat"),
    Def("premium_priority", "bool", "1", "اولویت صف برای کاربر ویژه", "chat"),
    Def("premium_free_search", "bool", "1", "جستجوی رایگان برای کاربر ویژه", "chat"),
    Def("queue_timeout", "int", "5", "مهلت جستجو (دقیقه)", "chat", "پس از این مدت جستجو لغو می‌شود", 1, 120),
    Def("chat_idle", "int", "60", "پایان خودکار چت بی‌فعالیت (دقیقه)", "chat", "۰ = غیرفعال", 0, 1440),
    Def("rematch_cooldown", "int", "10", "فاصله اتصال دوباره دو نفر (دقیقه)", "chat", "بعد از پایان چت، همان دو نفر تا این مدت به هم وصل نمی‌شوند", 0, 1440),
    Def("min_age", "int", "13", "حداقل سن", "chat", "", 10, 30),
    Def("auto_suspend_reports", "int", "3", "تعلیق خودکار پس از N گزارش", "chat", "۰ = غیرفعال", 0, 50),
    Def("suspend_hours", "int", "24", "مدت تعلیق خودکار (ساعت)", "chat", "", 1, 720),
    # --- اقتصاد ---
    Def("initial_coins", "int", "5", "سکه هدیه ثبت‌نام", "economy"),
    Def("referral", "bool", "1", "سیستم دعوت دوستان", "economy"),
    Def("referral_reward", "int", "3", "پاداش دعوت (سکه)", "economy"),
    Def("cost_gender", "int", "1", "هزینه جستجوی دختر/پسر", "economy"),
    Def("cost_age", "int", "0", "هزینه فیلتر هم‌سن", "economy"),
    Def("cost_city", "int", "0", "هزینه فیلتر همشهری", "economy"),
    Def("cost_edit", "int", "2", "هزینه ویرایش پروفایل", "economy"),
    Def("cost_gender_edit", "int", "5", "هزینه تغییر جنسیت", "economy"),
    Def("cost_photo", "int", "3", "هزینه تغییر عکس پروفایل", "economy"),
    Def("premium_free_edit", "bool", "1", "ویرایش رایگان پروفایل برای کاربر ویژه", "economy"),
    Def("custom_link_premium", "bool", "0", "لینک دلخواه فقط برای کاربر ویژه", "economy"),
    # --- پرداخت ---
    Def("coin_purchase", "bool", "1", "فروش سکه", "pay"),
    Def("premium_purchase", "bool", "1", "فروش حساب ویژه", "pay"),
    Def("coin_price", "int", "500", "قیمت هر سکه (تومان)", "pay", "", 1, 10**7),
    Def("coin_min", "int", "10", "حداقل خرید سکه", "pay", "", 1, 10**6),
    Def("coin_max", "int", "1000", "حداکثر خرید سکه", "pay", "", 1, 10**6),
    Def("premium_30", "int", "35000", "قیمت ویژه ۳۰ روزه (تومان)", "pay", "", 1, 10**8),
    Def("premium_90", "int", "90000", "قیمت ویژه ۹۰ روزه (تومان)", "pay", "", 1, 10**8),
    Def("premium_365", "int", "300000", "قیمت ویژه ۳۶۵ روزه (تومان)", "pay", "", 1, 10**8),
    Def("provider_token", "text", "", "توکن درگاه پرداخت بله", "pay", "توکن ولت بله از @botfather"),
    # --- متن‌ها ---
    Def("require_rules", "bool", "1", "درخواست تأیید قوانین از کاربر جدید", "texts", "اگر خاموش باشد مرحله قوانین نمایش داده نمی‌شود"),
    Def("welcome", "text", "", "پیام خوش‌آمد", "texts", "خالی = متن پیش‌فرض"),
    Def("rules", "text", "", "قوانین", "texts", "خالی = قوانین پیش‌فرض"),
    Def("announcement", "text", "", "اطلاعیه صفحه اصلی", "texts"),
    Def("help_extra", "text", "", "متن اضافه راهنما", "texts"),
    Def("receipt_note", "text", "", "یادداشت پایین رسید پرداخت", "texts", "مثلاً: در صورت مشکل با پشتیبانی تماس بگیرید"),
    Def("official_channel", "text", "", "لینک کانال رسمی", "texts", "https://ble.ir/..."),
    Def("support_username", "text", "", "آیدی پشتیبانی", "texts", "بدون @"),
    Def("banner", "text", "", "بنر منو (file_id عکس)", "texts"),
    Def("log_channel", "text", "", "کانال لاگ رویدادها", "logs", "شناسه عددی کانال/گروه (بهتر است از بخش لاگ‌ها تنظیم شود)"),
    Def("log_users", "bool", "1", "لاگ کاربران جدید", "logs"),
    Def("log_payments", "bool", "1", "لاگ خریدها و کد هدیه", "logs"),
    Def("log_chats", "bool", "1", "لاگ اتصال و قطع چت‌ها", "logs"),
    Def("log_reports", "bool", "1", "لاگ گزارش‌ها و تعلیق‌ها", "logs"),
    Def("log_admin", "bool", "1", "لاگ عملیات مدیران", "logs"),
]

DEF_MAP: dict[str, Def] = {d.key: d for d in DEFS}

GROUPS = {
    "general": ("⚙️", "عمومی"),
    "chat": ("💬", "چت ناشناس"),
    "economy": ("🪙", "اقتصاد و سکه"),
    "pay": ("💳", "پرداخت و قیمت‌ها"),
    "texts": ("📝", "متن‌ها و لینک‌ها"),
    "logs": ("🗂", "کانال لاگ"),
}


class Settings:
    def __init__(self, db: Database) -> None:
        self.db = db
        self._cache: dict[str, str] = {}

    async def load(self) -> None:
        rows = await self.db.all("SELECT key, value FROM settings")
        self._cache = {r["key"]: r["value"] for r in rows}

    def get(self, key: str) -> str:
        if key in self._cache:
            return self._cache[key]
        return DEF_MAP[key].default

    def on(self, key: str) -> bool:
        return self.get(key) == "1"

    def int(self, key: str) -> int:
        try:
            return int(self.get(key))
        except ValueError:
            return int(DEF_MAP[key].default or 0)

    async def set(self, key: str, value: str) -> None:
        if key not in DEF_MAP:
            raise KeyError(key)
        await self.db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        self._cache[key] = value

    async def toggle(self, key: str) -> bool:
        new = "0" if self.on(key) else "1"
        await self.set(key, new)
        return new == "1"

    def in_group(self, group: str) -> list[Def]:
        return [d for d in DEFS if d.group == group]

    def premium_plans(self) -> list[tuple[int, int]]:
        """[(روز، قیمت تومان)]"""
        return [(30, self.int("premium_30")), (90, self.int("premium_90")), (365, self.int("premium_365"))]
