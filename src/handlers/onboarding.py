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
"""ثبت‌نام اولیه: جنسیت، سن، استان، شهر و قوانین. همچنین انتخابگر استان/شهر مشترک."""
from __future__ import annotations

import json

from baleropy import F, Router
from baleropy.types import CallbackQuery, Message

from .. import repo
from ..core import App, parse_step
from ..texts import DEFAULT_RULES, GEO, PROVINCES
from ..ui import PRIMARY, SUCCESS, b, chunk, show, toast
from ..util import fa

router = Router(name="onboarding")
PENDING_START: dict[int, str] = {}
CITY_PAGE = 30


# ---------------------------------------------------------------- سازنده‌های کیبورد
def gender_rows(prefix: str) -> list[list]:
    return [[b("👩 دختر", f"{prefix}:g:female", PRIMARY), b("👨 پسر", f"{prefix}:g:male", PRIMARY)]]


def age_rows(app: App, prefix: str) -> list[list]:
    lo = app.settings.int("min_age")
    return chunk([b(fa(a), f"{prefix}:a:{a}") for a in range(lo, 61)], 4)


def province_rows(prefix: str) -> list[list]:
    return chunk([b(p, f"{prefix}:p:{i}") for i, p in enumerate(PROVINCES)], 3)


def city_rows(prefix: str, prov_idx: int, page: int = 0) -> list[list]:
    cities = GEO[PROVINCES[prov_idx]]
    pages = max(1, -(-len(cities) // CITY_PAGE))
    page = max(0, min(page, pages - 1))
    start = page * CITY_PAGE
    rows = chunk([b(c, f"{prefix}:c:{start + i}") for i, c in enumerate(cities[start:start + CITY_PAGE])], 3)
    nav = []
    if page > 0:
        nav.append(b("◀️ قبلی", f"{prefix}:cp:{page - 1}"))
    nav.append(b("↩️ تغییر استان", f"{prefix}:pb"))
    if page < pages - 1:
        nav.append(b("بعدی ▶️", f"{prefix}:cp:{page + 1}"))
    rows.append(nav)
    return rows


# ---------------------------------------------------------------- مراحل
async def prompt_stage(app: App, event: Message | CallbackQuery, user: dict) -> None:
    stage = user["onboard"]
    if stage == "gender":
        await show(app, event, "👋 سلام به چت ناشناس بینام خوش اومدی!\n\n👇 اول جنسیتت رو انتخاب کن", gender_rows("ob"))
    elif stage == "age":
        await show(app, event, "🎂 چند سالته؟", age_rows(app, "ob"))
    elif stage == "province":
        await show(app, event, "🗺 استان محل زندگیت؟", province_rows("ob"))
    elif stage == "city":
        data = parse_step(user["step_data"])
        if "prov" not in data:
            await repo.update_user(app, user["id"], onboard="province")
            user["onboard"] = "province"
            return await prompt_stage(app, event, user)
        prov = PROVINCES[data["prov"]]
        await show(app, event, f"🏙 شهرت در استان {prov} کدومه؟", city_rows("ob", data["prov"], data.get("page", 0)))
    elif stage == "terms" and not app.settings.on("require_rules"):
        await repo.update_user(app, user["id"], onboard="done", terms=1, step="", step_data="")
        await pay_referral(app, user["id"])
        await proceed_after_signup(app, event, await repo.get_user(app, user["id"]) or user)
    elif stage == "terms":
        rules = app.settings.get("rules") or DEFAULT_RULES
        await show(app, event, rules, [[b("✅ قوانین را می‌پذیرم", "ob:t", SUCCESS)]])


async def ensure_onboarded(app: App, event: Message | CallbackQuery, user: dict) -> bool:
    """اگر ثبت‌نام کامل نیست مرحله بعد را نشان می‌دهد و False برمی‌گرداند."""
    if user["onboard"] == "done":
        return True
    fresh = await repo.get_user(app, user["id"]) or user
    await prompt_stage(app, event, fresh)
    return False


async def finish(app: App, event: CallbackQuery, user: dict) -> None:
    uid = user["id"]
    await repo.update_user(app, uid, onboard="done", terms=1, step="", step_data="")
    await pay_referral(app, uid)
    await toast(event, "🎉 ثبت‌نام کامل شد")
    if event.message:
        await app.delete(uid, event.message.message_id)
    await proceed_after_signup(app, event, await repo.get_user(app, uid) or user)


async def proceed_after_signup(app: App, event: Message | CallbackQuery, user: dict) -> None:
    """بعد از قوانین: عضویت اجباری (در صورت نیاز) و سپس منوی اصلی."""
    from ..middlewares import send_join_prompt, user_mw
    from .links import open_anonymous
    from .start import send_home
    uid = user["id"]
    if app.settings.on("force_join"):
        missing = await user_mw.missing_channels(app, uid, force=True)
        if missing:
            return await send_join_prompt(app, uid, missing)
    pending = PENDING_START.pop(uid, None)
    if pending:
        msg = event.message if isinstance(event, CallbackQuery) else event
        if msg is not None and await open_anonymous(app, msg, user, pending):
            return
    await send_home(app, event, user, intro="✅ ثبت‌نام کامل شد!\n\n", fresh=True)


async def pay_referral(app: App, uid: int) -> None:
    user = await repo.get_user(app, uid)
    if not user or not user["referrer_id"] or user["referral_paid"] or not app.settings.on("referral"):
        return
    reward = app.settings.int("referral_reward")
    await repo.update_user(app, uid, referral_paid=1)
    if reward <= 0:
        return
    new = await repo.add_coins(app, user["referrer_id"], reward, "referral", ref=str(uid), note="پاداش دعوت")
    if new is not None:
        await app.send(user["referrer_id"], f"🎁 یکی از دوستانت با لینک دعوتت عضو شد!\n"
                                            f"🪙 {fa(reward)} سکه به حسابت اضافه شد. موجودی: {fa(new)}")


# ---------------------------------------------------------------- هندلرها
@router.callback_query(F.data.startswith("ob:"))
async def on_ob(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    action = parts[1] if len(parts) > 1 else ""
    arg = parts[2] if len(parts) > 2 else ""
    uid = user["id"]
    if user["onboard"] == "done":
        return await toast(event, "✅ ثبت‌نامت قبلاً کامل شده")
    await toast(event)

    if action == "g" and arg in ("male", "female"):
        await repo.update_user(app, uid, gender=arg, onboard="age")
    elif action == "a" and arg.isdigit() and app.settings.int("min_age") <= int(arg) <= 60:
        await repo.update_user(app, uid, age=int(arg), onboard="province")
    elif action == "p" and arg.isdigit() and int(arg) < len(PROVINCES):
        await repo.set_step(app, uid, "", {"prov": int(arg), "page": 0})
        await repo.update_user(app, uid, onboard="city")
    elif action == "pb":
        await repo.update_user(app, uid, onboard="province", step_data="")
    elif action == "cp" and arg.isdigit():
        data = parse_step(user["step_data"])
        data["page"] = int(arg)
        await repo.update_user(app, uid, step_data=json.dumps(data))
    elif action == "c" and arg.isdigit():
        data = parse_step(user["step_data"])
        prov_idx = data.get("prov")
        if prov_idx is None:
            return await prompt_stage(app, event, await repo.get_user(app, uid) or user)
        cities = GEO[PROVINCES[prov_idx]]
        if int(arg) < len(cities):
            await repo.update_user(app, uid, province=PROVINCES[prov_idx], city=cities[int(arg)],
                                   onboard="terms", step_data="")
            if not app.settings.on("require_rules"):
                return await finish(app, event, await repo.get_user(app, uid) or user)
    elif action == "t" and user["onboard"] == "terms":
        return await finish(app, event, user)
    await prompt_stage(app, event, await repo.get_user(app, uid) or user)
