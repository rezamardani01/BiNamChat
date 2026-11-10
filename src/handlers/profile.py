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
"""پروفایل: نمایش، ویرایش با هزینه سکه و کارت پروفایل برای دیگران."""
from __future__ import annotations

import json

from baleropy import F, Router
from baleropy.types import CallbackQuery, Message

from .. import repo
from ..core import App, parse_step
from ..filters import Step
from ..texts import GEO, PROVINCES
from ..ui import DANGER, PRIMARY, SUCCESS, b, show, toast
from ..util import esc, fa, jdate
from .onboarding import age_rows, city_rows, ensure_onboarded, gender_rows, province_rows

router = Router(name="profile")

FIELD_LABEL = {"name": "نام", "gender": "جنسیت", "age": "سن", "city": "شهر", "bio": "درباره من",
               "photo": "عکس پروفایل", "delphoto": "عکس پروفایل"}


LEVELS = [(0, "🌱 تازه‌وارد"), (5, "⚡️ فعال"), (25, "🔥 حرفه‌ای"), (100, "💎 افسانه‌ای")]


def level_of(chats: int) -> str:
    label = LEVELS[0][1]
    for need, name in LEVELS:
        if chats >= need:
            label = name
    return label


def completeness(u: dict) -> tuple[int, list[str]]:
    """درصد کامل‌بودن پروفایل و کارهای باقی‌مانده."""
    checks = [("gender", "جنسیت"), ("age", "سن"), ("city", "شهر"), ("bio", "درباره من"), ("photo", "عکس پروفایل")]
    missing = [label for key, label in checks if not u.get(key)]
    return round((len(checks) - len(missing)) * 100 / len(checks)), missing


def profile_text(u: dict, *, own: bool = False, friends: int = 0) -> str:
    prem = repo.is_premium(u)
    name = esc(u["name"], 30) or "کاربر"
    lines = [f"{'👑' if prem else '👤'} **{name}**" + ("  •  ویژه" if prem else ""),
             f"{level_of(u['chats_count'])}", "━━━━━━━━━━━━━━",
             f"{repo.gender_text(u['gender'])}",
             f"🎂 {fa(u['age']) + ' ساله' if u['age'] else '—'}",
             f"📍 {esc(u['city'])}، {esc(u['province'])}" if u["city"] else "📍 —",
             "",
             "💭 **درباره من**",
             esc(u["bio"], 200) or "🤐 هنوز چیزی ننوشته"]
    if own:
        pct, missing = completeness(u)
        lines += ["", "━━━━━━━━━━━━━━",
                  f"📊 کامل‌بودن پروفایل: {pct}٪",
                  f"{'▓' * (pct // 10)}{'░' * (10 - pct // 10)}"]
        if missing:
            lines.append("💡 تکمیل کن: " + "، ".join(missing))
        lines += ["━━━━━━━━━━━━━━",
                  f"🪙 سکه: {fa(u['coins'])}", f"💬 تعداد چت: {fa(u['chats_count'])}", f"👥 دوستان: {fa(friends)}",
                  "👑 ویژه: " + (f"فعال تا {jdate(u['premium_until'], 'short')}" if prem else "غیرفعال"),
                  f"📅 عضویت: {jdate(u['joined_at'])}  •  🆔 {u['id']}"]
    else:
        lines += ["", f"💬 تعداد گفتگو: {fa(u['chats_count'])}", f"📅 عضو از {jdate(u['joined_at'], 'short')}"]
    return "\n".join(lines)


async def send_profile_card(app: App, to: int, target: dict, rows=None, anonymous: bool = False) -> None:
    text = profile_text(target)
    if target.get("photo"):
        if await app.send_photo(to, target["photo"], text, rows):
            return
    await app.send(to, text, rows)


def own_rows() -> list[list]:
    return [
        [b("✏️ نام", "pe:name"), b("🎂 سن", "pe:age"), b("⚧ جنسیت", "pe:gender")],
        [b("🏙 شهر", "pe:city"), b("💭 درباره من", "pe:bio")],
        [b("📸 تغییر عکس", "pe:photo"), b("🗑 حذف عکس", "pe:delphoto")],
        [b("🏠 منوی اصلی", "m:home")],
    ]


async def show_own(app: App, event: Message | CallbackQuery, user: dict) -> None:
    if isinstance(event, CallbackQuery) and event.message is not None:
        await app.delete(user["id"], event.message.message_id)
    friends = await app.db.val("SELECT COUNT(*) FROM friends WHERE user_id = ?", (user["id"],), 0)
    text = profile_text(user, own=True, friends=friends)
    prem = [] if repo.is_premium(user) else [[b("👑 ارتقا به حساب ویژه", "w:prem", SUCCESS)]]
    rows = prem + own_rows()
    if user.get("photo") and await app.send_photo(user["id"], user["photo"], text, rows):
        return
    await app.send(user["id"], text, rows)


@router.callback_query(F.data == "p:home")
async def cb_home(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if not await ensure_onboarded(app, event, user):
        return
    await repo.set_step(app, user["id"], "")
    await show_own(app, event, user)


# ---------------------------------------------------------------- هزینه
def edit_cost(app: App, user: dict, field: str) -> int:
    if repo.is_premium(user) and app.settings.on("premium_free_edit"):
        return 0
    if field == "gender":
        return app.settings.int("cost_gender_edit")
    if field in ("photo", "delphoto"):
        return app.settings.int("cost_photo")
    return app.settings.int("cost_edit")


async def _prompt(app: App, uid: int, text: str, rows: list[list] | None = None) -> None:
    await app.send(uid, text, (rows or []) + [[b("❌ انصراف", "pe:cancel")]])


@router.callback_query(F.data.startswith("pe:"))
async def cb_edit(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    action = parts[1]
    arg = parts[2] if len(parts) > 2 else ""
    uid = user["id"]
    if user["state"] != "idle":
        return await toast(event, "در حین جستجو یا گفتگو نمی‌توانی پروفایل را ویرایش کنی", True)
    if not await ensure_onboarded(app, event, user):
        return await toast(event)
    await toast(event)
    msg_id = event.message.message_id if event.message else None

    if action == "cancel":
        await repo.set_step(app, uid, "")
        await app.delete(uid, msg_id)
        return
    if action in FIELD_LABEL and action != "city":
        await app.delete(uid, msg_id)
        cost = edit_cost(app, user, action)
        price = f"\n🪙 هزینه تغییر: {fa(cost)} سکه" if cost else "\n✅ برای تو رایگان است"
        if action == "name":
            await repo.set_step(app, uid, "pe_name")
            return await _prompt(app, uid, "✏️ **اسم نمایشی جدید**\nچه اسمی دوست داری مخاطب‌هات ببینن؟ (۲ تا ۲۵ حرف)\n💡 برای حفظ ناشناسی، اسم واقعی‌ات رو ننویس." + price,
                                 [[b("🤖 استفاده از نام بله", "pe:bale")]])
        if action == "bio":
            await repo.set_step(app, uid, "pe_bio")
            return await _prompt(app, uid, "💭 **درباره من**\nیه معرفی کوتاه و جذاب از خودت بنویس: علایق، سبک صحبت، چیزی که دنبالشی... (حداکثر ۲۰۰ حرف)" + price)
        if action == "photo":
            await repo.set_step(app, uid, "pe_photo")
            return await _prompt(app, uid, "📸 **عکس پروفایل**\nعکسی که می‌خوای مخاطب‌هات ببینن رو بفرست (فقط به‌عنوان عکس، نه فایل)." + price)
        if action == "delphoto":
            if not user["photo"]:
                return await app.send(uid, "عکسی برای حذف نداری.", [[b("🔙 پروفایل", "p:home")]])
            return await _confirm(app, user, "delphoto", "حذف")
        if action == "age":
            return await app.send(uid, "🎂 سن جدیدت؟" + price, age_rows(app, "pe") + [[b("❌ انصراف", "pe:cancel")]])
        if action == "gender":
            return await app.send(uid, "⚧ جنسیت جدیدت؟" + price, gender_rows("pe") + [[b("❌ انصراف", "pe:cancel")]])
    if action == "city":
        await app.delete(uid, msg_id)
        await repo.set_step(app, uid, "pe_city", {})
        return await app.send(uid, "🗺 استان جدیدت؟", province_rows("pe") + [[b("❌ انصراف", "pe:cancel")]])
    if action == "bale":
        await repo.set_step(app, uid, "")
        await app.delete(uid, msg_id)
        return await _confirm(app, user, "name", esc(event.from_user.full_name, 25) or "کاربر")
    if action == "g" and arg in ("male", "female"):
        await app.delete(uid, msg_id)
        return await _confirm(app, user, "gender", arg)
    if action == "a" and arg.isdigit():
        await app.delete(uid, msg_id)
        return await _confirm(app, user, "age", int(arg))
    if action == "p" and arg.isdigit() and int(arg) < len(PROVINCES):
        await repo.set_step(app, uid, "pe_city", {"prov": int(arg), "page": 0})
        return await show(app, event, f"🏙 شهرت در استان {PROVINCES[int(arg)]}؟",
                          city_rows("pe", int(arg)))
    if action == "pb":
        await repo.set_step(app, uid, "pe_city", {})
        return await show(app, event, "🗺 استان جدیدت؟", province_rows("pe"))
    if action == "cp" and arg.isdigit():
        data = parse_step(user["step_data"])
        if "prov" in data:
            data["page"] = int(arg)
            await repo.update_user(app, uid, step_data=json.dumps(data))
            return await show(app, event, f"🏙 شهرت در استان {PROVINCES[data['prov']]}؟",
                              city_rows("pe", data["prov"], int(arg)))
    if action == "c" and arg.isdigit():
        data = parse_step(user["step_data"])
        if "prov" in data:
            cities = GEO[PROVINCES[data["prov"]]]
            if int(arg) < len(cities):
                await app.delete(uid, msg_id)
                return await _confirm(app, user, "city", {"province": PROVINCES[data["prov"]], "city": cities[int(arg)]})
    if action == "ok":
        return await _apply(app, event, user)


async def _confirm(app: App, user: dict, field: str, value) -> None:
    cost = edit_cost(app, user, field)
    await repo.set_step(app, user["id"], "pe_confirm", {"field": field, "value": value})
    if field == "gender":
        shown = repo.gender_text(value)
    elif field == "age":
        shown = f"{fa(value)} سال"
    elif field == "city":
        shown = f"{value['city']}، {value['province']}"
    elif field == "delphoto":
        shown = "حذف عکس پروفایل"
    elif field == "photo":
        shown = "عکس جدید"
    else:
        shown = esc(value, 200)
    price = f"🪙 {fa(cost)} سکه از موجودی‌ات کسر می‌شود" if cost else "✅ رایگان"
    text = (f"❓ **تأیید تغییر {FIELD_LABEL[field]}**\n━━━━━━━━━━━━━━\n"
            f"مقدار جدید: {shown}\n{price}\n🪙 موجودی فعلی: {fa(user['coins'])}")
    await app.send(user["id"], text, [[b("✅ تأیید", "pe:ok", SUCCESS), b("❌ انصراف", "pe:cancel", DANGER)]])


async def _apply(app: App, event: CallbackQuery, user: dict) -> None:
    uid = user["id"]
    fresh = await repo.get_user(app, uid) or user
    if not fresh["step"].startswith("pe_confirm"):
        return
    data = parse_step(fresh["step_data"])
    field, value = data.get("field"), data.get("value")
    await app.delete(uid, event.message.message_id if event.message else None)
    if field not in FIELD_LABEL:
        return
    cost = edit_cost(app, fresh, field)
    if cost:
        paid = await repo.add_coins(app, uid, -cost, "profile_edit", ref=field, note=f"ویرایش {FIELD_LABEL[field]}")
        if paid is None:
            await repo.set_step(app, uid, "")
            return await app.send(uid, f"🪙 موجودی کافی نیست (نیاز به {fa(cost)} سکه).",
                                  [[b("🛍 فروشگاه", "w:home", PRIMARY)], [b("🔙 پروفایل", "p:home")]])
    patch: dict = {"step": "", "step_data": ""}
    if field == "name":
        patch["name"] = esc(value, 25)
    elif field == "gender":
        patch["gender"] = value
    elif field == "age":
        patch["age"] = int(value)
    elif field == "city":
        patch.update(province=value["province"], city=value["city"])
    elif field == "bio":
        patch["bio"] = esc(value, 200)
    elif field == "photo":
        patch["photo"] = value
    elif field == "delphoto":
        patch["photo"] = None
    await repo.update_user(app, uid, **patch)
    await app.send(uid, "✅ تغییر انجام شد.")
    await show_own(app, event, await repo.get_user(app, uid) or fresh)


# ---------------------------------------------------------------- ورودی متنی/عکس
@router.message(Step("pe_name"), F.text)
async def in_name(message: Message, app: App, user: dict) -> None:
    name = esc(message.text, 25)
    if len(name) < 2:
        return await app.send(user["id"], "نام باید حداقل ۲ حرف (بدون * _ [ ]) باشد.", [[b("❌ انصراف", "pe:cancel")]])
    await _confirm(app, user, "name", name)


@router.message(Step("pe_bio"), F.text)
async def in_bio(message: Message, app: App, user: dict) -> None:
    bio = esc(message.text, 200)
    if len(bio) < 3:
        return await app.send(user["id"], "متن خیلی کوتاه است.", [[b("❌ انصراف", "pe:cancel")]])
    await _confirm(app, user, "bio", bio)


@router.message(Step("pe_photo"))
async def in_photo(message: Message, app: App, user: dict) -> None:
    if not message.photo:
        return await app.send(user["id"], "🖼 لطفاً یک عکس بفرست", [[b("❌ انصراف", "pe:cancel")]])
    await _confirm(app, user, "photo", message.photo[-1].file_id)
