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
"""ابزارهای کمکی: زمان، تاریخ شمسی، اعداد فارسی، متن."""
from __future__ import annotations

import re
import secrets
import string
import time
from datetime import datetime, timedelta, timezone

TEHRAN = timezone(timedelta(hours=3, minutes=30))
_FA = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")
_EN = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def now() -> int:
    return int(time.time())


def fa(value: object) -> str:
    """عدد را با ارقام فارسی و جداکننده هزارگان برمی‌گرداند."""
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, float):
        value = int(value) if value == int(value) else round(value, 2)
    if isinstance(value, int):
        return f"{value:,}".replace(",", "٬").translate(_FA)
    return str(value).translate(_FA)


def en_digits(text: str) -> str:
    return text.translate(_EN)


def parse_int(text: str | None) -> int | None:
    if text is None:
        return None
    cleaned = en_digits(text).strip().replace(",", "").replace("٬", "")
    if re.fullmatch(r"-?\d{1,15}", cleaned):
        return int(cleaned)
    return None


def _g2j(gy: int, gm: int, gd: int) -> tuple[int, int, int]:
    g_d_m = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334]
    gy2 = gy + 1 if gm > 2 else gy
    days = 355666 + 365 * gy + (gy2 + 3) // 4 - (gy2 + 99) // 100 + (gy2 + 399) // 400 + gd + g_d_m[gm - 1]
    jy = -1595 + 33 * (days // 12053)
    days %= 12053
    jy += 4 * (days // 1461)
    days %= 1461
    if days > 365:
        jy += (days - 1) // 365
        days = (days - 1) % 365
    if days < 186:
        jm, jd = 1 + days // 31, 1 + days % 31
    else:
        jm, jd = 7 + (days - 186) // 30, 1 + (days - 186) % 30
    return jy, jm, jd


MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
          "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"]


def jdate(ts: int | float | None = None, fmt: str = "date") -> str:
    """تاریخ شمسی. fmt: date | time | full | short | day"""
    ts = now() if ts is None else ts
    dt = datetime.fromtimestamp(ts, TEHRAN)
    jy, jm, jd = _g2j(dt.year, dt.month, dt.day)
    if fmt == "time":
        return fa(dt.strftime("%H:%M"))
    if fmt == "short":
        return fa(f"{jy}/{jm:02d}/{jd:02d}")
    if fmt == "day":
        return fa(f"{jm:02d}/{jd:02d}")
    if fmt == "full":
        return fa(f"{jy}/{jm:02d}/{jd:02d} - {dt.strftime('%H:%M')}")
    return fa(f"{jd} {MONTHS[jm - 1]} {jy}")


def day_start(ts: int | None = None) -> int:
    dt = datetime.fromtimestamp(now() if ts is None else ts, TEHRAN)
    return int(dt.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())


def ago(ts: int | None) -> str:
    if not ts:
        return "—"
    diff = max(0, now() - int(ts))
    if diff < 60:
        return "لحظاتی پیش"
    if diff < 3600:
        return f"{fa(diff // 60)} دقیقه پیش"
    if diff < 86400:
        return f"{fa(diff // 3600)} ساعت پیش"
    if diff < 86400 * 60:
        return f"{fa(diff // 86400)} روز پیش"
    return jdate(ts, "short")


def duration(seconds: int) -> str:
    seconds = max(0, int(seconds))
    if seconds < 60:
        return f"{fa(seconds)} ثانیه"
    if seconds < 3600:
        return f"{fa(seconds // 60)} دقیقه"
    if seconds < 86400:
        h, m = divmod(seconds // 60, 60)
        return f"{fa(h)} ساعت" + (f" و {fa(m)} دقیقه" if m else "")
    d, rest = divmod(seconds, 86400)
    return f"{fa(d)} روز" + (f" و {fa(rest // 3600)} ساعت" if rest // 3600 else "")


_STRIP = re.compile(r"[*_\[\]`~]")


def esc(text: object, limit: int = 0) -> str:
    """متن کاربر را برای مارک‌داون بله بی‌خطر می‌کند."""
    value = _STRIP.sub("", str(text or "")).strip()
    if limit and len(value) > limit:
        value = value[: limit - 1] + "…"
    return value


def bold(text: object) -> str:
    return f" **{text}** "


def rand_code(length: int = 8) -> str:
    alphabet = string.ascii_lowercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def bar(value: int, total: int, width: int = 10) -> str:
    if total <= 0:
        return "░" * width
    filled = round(width * min(value, total) / total)
    return "▓" * filled + "░" * (width - filled)


_SPARK = "▁▂▃▄▅▆▇█"


def spark(values: list[int]) -> str:
    if not values:
        return ""
    top = max(values) or 1
    return "".join(_SPARK[min(7, int(v / top * 7))] if v else _SPARK[0] for v in values)


_CONTACT_RE = re.compile(
    r"(https?://|www\.|ble\.ir|t\.me|\b[\w-]+\.(?:com|ir|org|net|me|io)\b|@\w{4,}|"
    r"(?:\+?98|0)?9\d{9}|\b\d{8,}\b)",
    re.IGNORECASE,
)


def has_contact_info(text: str | None) -> bool:
    """شماره، آیدی یا لینک در متن؟ (ارقام فارسی هم بررسی می‌شود)"""
    if not text:
        return False
    plain = en_digits(text)
    squeezed = re.sub(r"(?<=\d)[\s\-.](?=\d)", "", plain)
    return bool(_CONTACT_RE.search(plain) or _CONTACT_RE.search(squeezed))


def age_group(age: int | None) -> int:
    """0 = زیر ۱۸، 1 = ۱۸ تا ۲۴، 2 = ۲۵ تا ۳۴، 3 = ۳۵ تا ۴۴، 4 = ۴۵ به بالا"""
    if not age:
        return 1
    if age < 18:
        return 0
    if age < 25:
        return 1
    if age < 35:
        return 2
    if age < 45:
        return 3
    return 4
