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
"""فیلترهای سفارشی."""
from __future__ import annotations

from typing import Any

from baleropy.filters import Filter


class Step(Filter):
    """پیام را فقط وقتی می‌پذیرد که «گام» فعلی کاربر یکی از نام‌های داده‌شده باشد.

    گام در دیتابیس به‌صورت `name` یا `name:arg` ذخیره می‌شود و بعد از ری‌استارت هم باقی می‌ماند.
    """

    def __init__(self, *names: str) -> None:
        self.names = set(names)

    async def __call__(self, event: Any, **data: Any) -> bool | dict[str, Any]:
        user = data.get("user")
        if not user or not user["step"]:
            return False
        head, _, arg = user["step"].partition(":")
        if head in self.names:
            return {"step_arg": arg}
        return False


class InChat(Filter):
    """کاربر در یک گفتگوی فعال است."""

    async def __call__(self, event: Any, **data: Any) -> bool:
        user = data.get("user")
        return bool(user) and user["state"] == "chat"
