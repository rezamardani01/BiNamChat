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
"""ویرایش تنظیمات ربات از داخل پنل (کاملاً پویا از روی تعریف تنظیمات)."""
from __future__ import annotations

from baleropy import F, Router
from baleropy.types import CallbackQuery, Message

from .. import repo
from ..core import App
from ..filters import Step
from ..settings import DEF_MAP, GROUPS
from ..texts import DEFAULT_RULES, DEFAULT_WELCOME
from ..ui import DANGER, PRIMARY, SUCCESS, b, chunk, show, toast
from ..util import esc, fa, parse_int
from .common import admin_only, back

router = Router(name="admin_settings")
SECRET = {"provider_token"}


def shown(app: App, key: str) -> str:
    d = DEF_MAP[key]
    value = app.settings.get(key)
    if d.kind == "bool":
        return "✅" if value == "1" else "▫️"
    if not value:
        return "—"
    if key in SECRET:
        return value[:6] + "…"
    if d.kind == "int":
        return fa(int(value)) if value.lstrip("-").isdigit() else value
    return esc(value, 18)


@router.callback_query(F.data == "a:se")
async def cb_menu(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "")
    rows = chunk([b(f"{icon} {title}", f"a:se:g:{key}", PRIMARY) for key, (icon, title) in GROUPS.items()], 2)
    rows.append(back())
    await show(app, event, "⚙️ **تنظیمات ربات**\n━━━━━━━━━━━━━━\nیک دسته را انتخاب کن. تغییرها بلافاصله اعمال می‌شود.", rows)


async def group_view(app: App, group: str) -> tuple[str, list[list]]:
    icon, title = GROUPS[group]
    rows = []
    for d in app.settings.in_group(group):
        if d.kind == "bool":
            on = app.settings.on(d.key)
            rows.append([b(f"{'✅' if on else '▫️'} {d.label}", f"a:se:t:{d.key}", SUCCESS if on else None)])
        else:
            rows.append([b(f"{d.label}: {shown(app, d.key)}", f"a:se:e:{d.key}")])
    rows.append(back("a:se"))
    return f"{icon} **{title}**\n━━━━━━━━━━━━━━\nروی هر مورد بزن تا تغییر کند.", rows


@router.callback_query(F.data.startswith("a:se:g:"))
async def cb_group(event: CallbackQuery, app: App) -> None:
    group = (event.data or "").split(":")[3]
    if group not in GROUPS:
        return await toast(event)
    await toast(event)
    text, rows = await group_view(app, group)
    await show(app, event, text, rows)


@router.callback_query(F.data.startswith("a:se:t:"))
async def cb_toggle(event: CallbackQuery, app: App, user: dict) -> None:
    key = (event.data or "").split(":")[3]
    d = DEF_MAP.get(key)
    if not d or d.kind != "bool":
        return await toast(event)
    on = await app.settings.toggle(key)
    await app.audit(user["id"], "setting", key, "on" if on else "off")
    await toast(event, ("روشن شد: " if on else "خاموش شد: ") + d.label)
    text, rows = await group_view(app, d.group)
    await show(app, event, text, rows)


@router.callback_query(F.data.startswith("a:se:e:"))
async def cb_edit(event: CallbackQuery, app: App, user: dict) -> None:
    key = (event.data or "").split(":")[3]
    d = DEF_MAP.get(key)
    if not d or d.kind == "bool":
        return await toast(event)
    await toast(event)
    await repo.set_step(app, user["id"], f"a_set:{key}")
    current = app.settings.get(key)
    hint = f"\n💡 {d.hint}" if d.hint else ""
    rng = f"\n📏 بازه مجاز: {fa(d.min)} تا {fa(d.max)}" if d.kind == "int" else ""
    default_text = {"rules": DEFAULT_RULES, "welcome": DEFAULT_WELCOME}.get(key)
    if key in SECRET and current:
        cur = "•••"
    elif current:
        cur = esc(current, 1500)
    elif default_text:
        cur = "(پیش‌فرض ربات)\n" + default_text[:1500]
    else:
        cur = "—"
    rows = [[b("↩️ مقدار پیش‌فرض", f"a:se:r:{key}")]]
    if d.kind == "text":
        rows.append([b("🗑 پاک کردن", f"a:se:r:{key}:clear", DANGER)])
    rows.append([b("❌ انصراف", f"a:se:g:{d.group}")])
    extra = "\n🖼 برای بنر می‌توانی مستقیم یک عکس بفرستی." if key == "banner" else ""
    await show(app, event, f"✏️ **{d.label}**{hint}{rng}{extra}\n\nمقدار فعلی: {cur}\n\nمقدار جدید را بفرست:", rows)


@router.callback_query(F.data.startswith("a:se:r:"))
async def cb_reset(event: CallbackQuery, app: App, user: dict) -> None:
    parts = (event.data or "").split(":")
    d = DEF_MAP.get(parts[3])
    if not d:
        return await toast(event)
    value = "" if len(parts) > 4 else d.default
    await app.settings.set(d.key, value)
    await repo.set_step(app, user["id"], "")
    await app.audit(user["id"], "setting", d.key, "reset")
    await toast(event, "انجام شد")
    text, rows = await group_view(app, d.group)
    await show(app, event, text, rows)


@router.message(Step("a_set"))
async def in_value(message: Message, app: App, user: dict, step_arg: str) -> None:
    if not await admin_only(app, message, user["id"], "settings"):
        return
    d = DEF_MAP.get(step_arg)
    if not d:
        return await repo.set_step(app, user["id"], "")
    if d.key == "banner" and message.photo:
        value = message.photo[-1].file_id
    elif message.text:
        value = message.text.strip()
        if d.kind == "int":
            number = parse_int(value)
            if number is None or not d.min <= number <= d.max:
                return await app.send(user["id"], f"❌ یک عدد بین {fa(d.min)} تا {fa(d.max)} بفرست.")
            value = str(number)
        elif d.key == "official_channel" and value and not value.startswith("http"):
            return await app.send(user["id"], "❌ لینک باید با http شروع شود.")
        elif d.key == "support_username":
            value = value.lstrip("@")
    else:
        return await app.send(user["id"], "❌ فقط متن (یا برای بنر، عکس) بفرست.")
    await app.settings.set(d.key, value)
    await repo.set_step(app, user["id"], "")
    await app.audit(user["id"], "setting", d.key, "***" if d.key in SECRET else value[:80])
    if d.key in SECRET:
        await app.delete(user["id"], message.message_id)
    text, rows = await group_view(app, d.group)
    await app.send(user["id"], "✅ ذخیره شد.\n\n" + text, rows)
