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
"""کدهای هدیه و گزارش‌های مالی."""
from __future__ import annotations

from baleropy import Button, F, Router
from baleropy.types import CallbackQuery, Message

from .. import repo
from ..core import App, parse_step
from ..filters import Step
from ..ui import DANGER, PRIMARY, SUCCESS, b, chunk, pager, show, toast
from ..util import day_start, fa, jdate, now, parse_int, rand_code
from .common import PER_PAGE, admin_only, back, uname

router = Router(name="admin_economy")


# ---------------------------------------------------------------- کد هدیه
def gift_label(g: dict) -> str:
    return f"{'🟢' if g['active'] and g['used'] < g['max_uses'] else '⚪️'} {g['code']} • " \
           f"{fa(g['reward_qty'])} {'سکه' if g['reward_kind'] == 'coin' else 'روز'} • {fa(g['used'])}/{fa(g['max_uses'])}"


@router.callback_query(F.data.startswith("a:gf:l:"))
async def cb_list(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "")
    page = int((event.data or "a:gf:l:0").split(":")[3])
    total = await app.db.val("SELECT COUNT(*) FROM gift_codes", default=0)
    items = await app.db.all("SELECT * FROM gift_codes ORDER BY id DESC LIMIT ? OFFSET ?", (PER_PAGE, page * PER_PAGE))
    rows = [[b("➕ ساخت کد جدید", "a:gf:new", SUCCESS)]] + chunk([b(gift_label(g), f"a:gf:v:{g['id']}") for g in items], 1)
    nav = pager("a:gf:l:", page, total, PER_PAGE)
    if nav:
        rows.append(nav)
    rows.append(back())
    await show(app, event, f"🎁 **کدهای هدیه** ({fa(total)})\n━━━━━━━━━━━━━━" + ("" if items else "\nهنوز کدی نساخته‌ای."), rows)


@router.callback_query(F.data == "a:gf:new")
async def cb_new(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await show(app, event, "🎁 پاداش کد چه باشد؟",
               [[b("🪙 سکه", "a:gf:k:coin", PRIMARY), b("👑 روز حساب ویژه", "a:gf:k:premium", PRIMARY)], back("a:gf:l:0")])


@router.callback_query(F.data.startswith("a:gf:k:"))
async def cb_kind(event: CallbackQuery, app: App, user: dict) -> None:
    kind = (event.data or "").split(":")[3]
    if kind not in ("coin", "premium") or not await admin_only(app, event, user["id"], "gifts"):
        return await toast(event)
    await toast(event)
    await repo.set_step(app, user["id"], "a_gf", {"kind": kind, "stage": "qty"})
    await show(app, event, f"{'🪙 تعداد سکه' if kind == 'coin' else '👑 تعداد روز ویژه'} برای هر نفر؟ (عدد بفرست)",
               [[b("❌ انصراف", "a:gf:l:0", DANGER)]])


@router.message(Step("a_gf"), F.text)
async def in_wizard(message: Message, app: App, user: dict) -> None:
    if not await admin_only(app, message, user["id"], "gifts"):
        return
    data = parse_step(user["step_data"])
    stage = data.get("stage")
    text = (message.text or "").strip()
    uid = user["id"]
    if stage in ("qty", "uses", "days"):
        number = parse_int(text)
        if number is None or number <= 0 or number > 10**6:
            return await app.send(uid, "یک عدد مثبت معتبر بفرست.")
        if stage == "qty":
            data.update(qty=number, stage="uses")
            await repo.set_step(app, uid, "a_gf", data)
            return await app.send(uid, "👥 حداکثر تعداد دفعات استفاده (کل کاربران)؟")
        if stage == "uses":
            data.update(uses=number, stage="days")
            await repo.set_step(app, uid, "a_gf", data)
            return await app.send(uid, "⏳ اعتبار کد چند روز باشد؟ (۰ = بدون انقضا)", [[b("♾ بدون انقضا", "a:gf:nd")]])
        data.update(days=number, stage="code")
        await repo.set_step(app, uid, "a_gf", data)
        return await app.send(uid, "🔤 متن کد را بفرست (حروف انگلیسی/عدد) یا برای کد خودکار دکمه را بزن:",
                              [[b("🎲 کد خودکار", "a:gf:auto")]])
    if stage == "code":
        code = text.upper()
        if not code.replace("-", "").replace("_", "").isalnum() or not code.isascii() or not 4 <= len(code) <= 24:
            return await app.send(uid, "کد باید ۴ تا ۲۴ حرف انگلیسی/عدد باشد.")
        await _finish(app, uid, data, code)


@router.callback_query(F.data == "a:gf:nd")
async def cb_no_expire(event: CallbackQuery, app: App, user: dict) -> None:
    data = parse_step(user["step_data"])
    if data.get("stage") != "days":
        return await toast(event)
    await toast(event)
    data.update(days=0, stage="code")
    await repo.set_step(app, user["id"], "a_gf", data)
    await app.send(user["id"], "🔤 متن کد را بفرست یا کد خودکار بساز:", [[b("🎲 کد خودکار", "a:gf:auto")]])


@router.callback_query(F.data == "a:gf:auto")
async def cb_auto(event: CallbackQuery, app: App, user: dict) -> None:
    data = parse_step(user["step_data"])
    if data.get("stage") != "code":
        return await toast(event)
    await toast(event)
    await _finish(app, user["id"], data, f"BN-{rand_code(6).upper()}")


async def _finish(app: App, admin_id: int, data: dict, code: str) -> None:
    expires = now() + data["days"] * 86400 if data["days"] else 0
    try:
        await app.db.execute(
            "INSERT INTO gift_codes(code, reward_kind, reward_qty, max_uses, expires_at, created_by, created_at) VALUES(?,?,?,?,?,?,?)",
            (code, data["kind"], data["qty"], data["uses"], expires, admin_id, now()))
    except Exception:  # noqa: BLE001  (کد تکراری)
        return await app.send(admin_id, "❌ این کد قبلاً وجود دارد؛ کد دیگری بفرست.")
    await repo.set_step(app, admin_id, "")
    await app.audit(admin_id, "gift_create", code, f"{data['kind']}×{data['qty']} uses={data['uses']}")
    await app.send(admin_id, f"✅ کد ساخته شد:\n\n`{code}`\n\n{'🪙' if data['kind'] == 'coin' else '👑'} {fa(data['qty'])} "
                             f"{'سکه' if data['kind'] == 'coin' else 'روز'} • {fa(data['uses'])} بار استفاده",
                   [[Button.copy_text("📋 کپی کد", code, style=PRIMARY)], [b("🎁 کدهای هدیه", "a:gf:l:0")]])


@router.callback_query(F.data.startswith("a:gf:v:"))
async def cb_view(event: CallbackQuery, app: App) -> None:
    gid = (event.data or "").split(":")[3]
    g = await app.db.one("SELECT * FROM gift_codes WHERE id = ?", (int(gid),)) if gid.isdigit() else None
    if not g:
        return await toast(event, "پیدا نشد", True)
    await toast(event)
    exp = jdate(g["expires_at"], "full") if g["expires_at"] else "بدون انقضا"
    text = (f"🎁 **کد `{g['code']}`**\n━━━━━━━━━━━━━━\n"
            f"پاداش: {fa(g['reward_qty'])} {'سکه' if g['reward_kind'] == 'coin' else 'روز حساب ویژه'}\n"
            f"استفاده: {fa(g['used'])} از {fa(g['max_uses'])}\n⏳ انقضا: {exp}\n"
            f"{'🟢 فعال' if g['active'] else '🔴 غیرفعال'}\n📅 ساخته‌شده: {jdate(g['created_at'], 'short')}")
    await show(app, event, text, [
        [Button.copy_text("📋 کپی کد", g["code"], style=PRIMARY)],
        [b("🔴 غیرفعال‌سازی" if g["active"] else "🟢 فعال‌سازی", f"a:gf:t:{g['id']}"), b("🗑 حذف", f"a:gf:d:{g['id']}", DANGER)],
        back("a:gf:l:0")])


@router.callback_query(F.data.startswith("a:gf:t:"))
async def cb_toggle(event: CallbackQuery, app: App, user: dict) -> None:
    gid = (event.data or "").split(":")[3]
    if gid.isdigit() and await admin_only(app, event, user["id"], "gifts"):
        await app.db.execute("UPDATE gift_codes SET active = 1 - active WHERE id = ?", (int(gid),))
        await app.audit(user["id"], "gift_toggle", gid)
    event_data = f"a:gf:v:{gid}"
    await toast(event, "انجام شد")
    g = await app.db.one("SELECT * FROM gift_codes WHERE id = ?", (int(gid),)) if gid.isdigit() else None
    if g:
        await show(app, event, f"{'🟢' if g['active'] else '🔴'} کد `{g['code']}` اکنون {'فعال' if g['active'] else 'غیرفعال'} است.",
                   [[b("🔙 جزئیات", event_data)]])


@router.callback_query(F.data.startswith("a:gf:d:"))
async def cb_delete(event: CallbackQuery, app: App, user: dict) -> None:
    gid = (event.data or "").split(":")[3]
    if gid.isdigit() and await admin_only(app, event, user["id"], "gifts"):
        await app.db.execute("DELETE FROM gift_uses WHERE gift_id = ?", (int(gid),))
        await app.db.execute("DELETE FROM gift_codes WHERE id = ?", (int(gid),))
        await app.audit(user["id"], "gift_delete", gid)
    await toast(event, "حذف شد")
    await show(app, event, "🗑 کد حذف شد.", [back("a:gf:l:0")])


# ---------------------------------------------------------------- امور مالی
@router.callback_query(F.data == "a:fn")
async def cb_finance(event: CallbackQuery, app: App) -> None:
    await toast(event)
    db = app.db
    t0 = day_start()

    async def revenue(since: int) -> int:
        return await db.val("SELECT COALESCE(SUM(amount_irr),0) FROM payments WHERE status = 'paid' AND paid_at >= ?", (since,), 0) // 10

    count_all = await db.val("SELECT COUNT(*) FROM payments WHERE status = 'paid'", default=0)
    coins_sold = await db.val("SELECT COALESCE(SUM(qty),0) FROM payments WHERE status = 'paid' AND kind = 'coin'", default=0)
    prem_cnt = await db.val("SELECT COUNT(*) FROM payments WHERE status = 'paid' AND kind = 'premium'", default=0)
    pending = await db.val("SELECT COUNT(*) FROM payments WHERE status = 'pending' AND created_at > ?", (now() - 86400,), 0)
    buyers = await db.val("SELECT COUNT(DISTINCT user_id) FROM payments WHERE status = 'paid'", default=0)
    users = await db.val("SELECT COUNT(*) FROM users", default=0) or 1
    total = await revenue(0)
    text = ("💰 **امور مالی**\n━━━━━━━━━━━━━━\n"
            f"📅 امروز: {fa(await revenue(t0))} تومان\n"
            f"🗓 ۷ روز اخیر: {fa(await revenue(t0 - 6 * 86400))} تومان\n"
            f"📆 ۳۰ روز اخیر: {fa(await revenue(t0 - 29 * 86400))} تومان\n"
            f"💎 مجموع: {fa(total)} تومان\n\n"
            f"🧾 پرداخت موفق: {fa(count_all)} • خریداران: {fa(buyers)} ({fa(round(buyers * 100 / users, 1))}٪ کاربران)\n"
            f"🪙 سکه فروخته‌شده: {fa(coins_sold)}\n👑 اشتراک فروخته‌شده: {fa(prem_cnt)}\n"
            f"⏳ فاکتور بی‌پرداخت (۲۴ ساعت): {fa(pending)}\n"
            f"📊 میانگین خرید: {fa(total // count_all if count_all else 0)} تومان")
    await show(app, event, text, [[b("🧾 آخرین پرداخت‌ها", "a:fn:p:0"), b("🏆 برترین خریداران", "a:fn:t:0")], back()])


@router.callback_query(F.data.startswith("a:fn:p:"))
async def cb_payments(event: CallbackQuery, app: App) -> None:
    await toast(event)
    page = int((event.data or "a:fn:p:0").split(":")[3])
    total = await app.db.val("SELECT COUNT(*) FROM payments WHERE status = 'paid'", default=0)
    items = await app.db.all("SELECT * FROM payments WHERE status = 'paid' ORDER BY paid_at DESC LIMIT ? OFFSET ?",
                             (10, page * 10))
    body = "\n".join(f"• {jdate(p['paid_at'], 'full')} • {p['user_id']} • "
                     f"{fa(p['qty'])} {'سکه' if p['kind'] == 'coin' else 'روز ویژه'} • {fa(p['amount_irr'] // 10)} ت" for p in items) or "—"
    rows = []
    nav = pager("a:fn:p:", page, total, 10)
    if nav:
        rows.append(nav)
    rows.append(back("a:fn"))
    await show(app, event, f"🧾 **پرداخت‌های موفق** ({fa(total)})\n━━━━━━━━━━━━━━\n{body}", rows)


@router.callback_query(F.data.startswith("a:fn:t:"))
async def cb_top(event: CallbackQuery, app: App) -> None:
    await toast(event)
    items = await app.db.all("SELECT user_id, SUM(amount_irr) s, COUNT(*) c FROM payments WHERE status = 'paid' "
                             "GROUP BY user_id ORDER BY s DESC LIMIT 10")
    lines = []
    for i, r in enumerate(items, 1):
        u = await repo.get_user(app, r["user_id"])
        lines.append(f"{fa(i)}. {uname(u)} ({r['user_id']}) — {fa(r['s'] // 10)} تومان ({fa(r['c'])} خرید)")
    await show(app, event, "🏆 **برترین خریداران**\n━━━━━━━━━━━━━━\n" + ("\n".join(lines) or "—"), [back("a:fn")])
