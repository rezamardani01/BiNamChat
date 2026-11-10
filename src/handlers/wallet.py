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
"""فروشگاه: سکه، حساب ویژه، پرداخت بله، کد هدیه، تراکنش‌ها و دعوت دوستان."""
from __future__ import annotations

import logging

from baleropy import Button, F, Router
from baleropy.types import CallbackQuery, Message, PreCheckoutQuery
from baleropy.types.payments import LabeledPrice

from .. import repo
from ..core import App
from ..filters import Step
from ..ui import PRIMARY, SUCCESS, b, chunk, show, toast
from ..util import esc, fa, jdate, now, parse_int, rand_code

log = logging.getLogger("binam.wallet")
router = Router(name="wallet")

TX_LABEL = {
    "welcome": "🎁 هدیه ثبت‌نام", "referral": "👥 پاداش دعوت", "purchase": "🛒 خرید سکه", "search": "🔎 جستجو",
    "profile_edit": "✏️ ویرایش پروفایل", "admin": "🛠 تغییر توسط مدیریت", "gift": "🎁 کد هدیه",
}


def tracking_code(payload: str) -> str:
    return "BN-" + payload.rsplit("-", 1)[-1].upper()


def _toman(rial: int) -> str:
    return fa(rial // 10)


# ---------------------------------------------------------------- صفحه اصلی
async def wallet_view(app: App, user: dict) -> tuple[str, list[list]]:
    prem = (f"👑 حساب ویژه تا {jdate(user['premium_until'], 'short')}" if repo.is_premium(user) else "👑 حساب ویژه: ندارید")
    text = (f"🛍 **فروشگاه**\n━━━━━━━━━━━━━━\nموجودی: {fa(user['coins'])} سکه\n{prem}\n\n"
            "سکه برای جستجوی دختر/پسر و ویرایش پروفایل استفاده می‌شه.")
    rows = []
    if app.settings.on("coin_purchase"):
        rows.append([b("🛒 خرید سکه", "w:buy", SUCCESS)])
    if app.settings.on("premium_purchase"):
        rows.append([b("👑 حساب ویژه", "w:prem", PRIMARY)])
    rows.append([b("🎁 کد هدیه", "w:gift"), b("📜 تراکنش‌ها", "w:tx")])
    rows.append([b("👥 دعوت دوستان (سکه رایگان)", "w:ref")])
    rows.append([b("🏠 منوی اصلی", "m:home")])
    return text, rows


@router.callback_query(F.data == "w:home")
async def cb_home(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "")
    text, rows = await wallet_view(app, user)
    await show(app, event, text, rows)


# ---------------------------------------------------------------- خرید سکه
def _pack_sizes(app: App) -> list[int]:
    lo, hi = app.settings.int("coin_min"), app.settings.int("coin_max")
    sizes = [n for n in (lo, lo * 2, lo * 5, lo * 10, lo * 20, lo * 50) if lo <= n <= hi]
    return sorted(set(sizes)) or [lo]


@router.callback_query(F.data == "w:buy")
async def cb_buy(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if not app.settings.on("coin_purchase"):
        return await show(app, event, "⏸ فروش سکه فعلاً غیرفعال است.", [[b("🔙 بازگشت", "w:home")]])
    price = app.settings.int("coin_price")
    buttons = [b(f"{fa(n)} سکه • {fa(n * price)} تومان", f"w:cb:{n}", PRIMARY) for n in _pack_sizes(app)]
    rows = chunk(buttons, 1) + [[b("✍️ تعداد دلخواه", "w:cq")], [b("🔙 بازگشت", "w:home")]]
    await show(app, event, f"🛒 **خرید سکه**\n━━━━━━━━━━━━━━\nقیمت هر سکه: {fa(price)} تومان\n"
                           f"بین {fa(app.settings.int('coin_min'))} تا {fa(app.settings.int('coin_max'))} سکه می‌تونی بخری.",
               rows)


@router.callback_query(F.data == "w:cq")
async def cb_custom_qty(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "coin_qty")
    await show(app, event, f"✍️ تعداد سکه (بین {fa(app.settings.int('coin_min'))} تا {fa(app.settings.int('coin_max'))}) "
                           "رو به عدد بفرست:", [[b("❌ انصراف", "w:buy")]])


@router.message(Step("coin_qty"), F.text)
async def in_qty(message: Message, app: App, user: dict) -> None:
    qty = parse_int(message.text)
    lo, hi = app.settings.int("coin_min"), app.settings.int("coin_max")
    if qty is None or not lo <= qty <= hi:
        return await app.send(user["id"], f"عدد معتبر بین {fa(lo)} تا {fa(hi)} بفرست.", [[b("❌ انصراف", "w:buy")]])
    await repo.set_step(app, user["id"], "")
    await invoice(app, user, "coin", qty)


async def invoice(app: App, user: dict, kind: str, qty: int) -> None:
    token = app.settings.get("provider_token").strip()
    if not token:
        return await app.send(user["id"], "💤 درگاه پرداخت هنوز توسط مدیریت تنظیم نشده است.", [[b("🎧 پشتیبانی", "sp:home")]])
    if kind == "coin":
        if not app.settings.on("coin_purchase"):
            return await app.send(user["id"], "فروش سکه غیرفعال است.")
        toman = qty * app.settings.int("coin_price")
        title, desc, label = f"{fa(qty)} سکه", f"خرید {fa(qty)} سکه برای ربات بینام", f"{fa(qty)} سکه"
    else:
        if not app.settings.on("premium_purchase"):
            return await app.send(user["id"], "فروش حساب ویژه غیرفعال است.")
        plans = dict(app.settings.premium_plans())
        if qty not in plans:
            return
        toman = plans[qty]
        title, desc, label = f"حساب ویژه {fa(qty)} روزه", f"اشتراک حساب ویژه بینام برای {fa(qty)} روز", f"حساب ویژه {fa(qty)} روزه"
    rial = toman * 10
    payload = f"{kind}-{user['id']}-{rand_code(10)}"
    await app.db.execute(
        "INSERT INTO payments(payload, user_id, kind, qty, amount_irr, status, created_at) VALUES(?,?,?,?,?,?,?)",
        (payload, user["id"], kind, qty, rial, "pending", now()))
    try:
        await app.bot.send_invoice(user["id"], title[:32], desc[:255], payload, token,
                                   [LabeledPrice(label=label[:32], amount=rial)])
    except Exception as exc:  # noqa: BLE001
        await app.error("invoice", repr(exc))
        await app.db.execute("UPDATE payments SET status = 'failed' WHERE payload = ?", (payload,))
        await app.send(user["id"], "⚠️ ساخت فاکتور ناموفق بود. کمی بعد دوباره تلاش کن یا به پشتیبانی خبر بده.")


@router.callback_query(F.data.startswith("w:cb:"))
async def cb_pack(event: CallbackQuery, app: App, user: dict) -> None:
    qty = parse_int((event.data or "").split(":")[2])
    lo, hi = app.settings.int("coin_min"), app.settings.int("coin_max")
    if qty is None or not lo <= qty <= hi:
        return await toast(event, "تعداد نامعتبر", True)
    await toast(event, "فاکتور در حال ساخت است...")
    await invoice(app, user, "coin", qty)


# ---------------------------------------------------------------- حساب ویژه
@router.callback_query(F.data == "w:prem")
async def cb_premium(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    s = app.settings
    perks = ["💎 ویژگی‌های حساب ویژه:"]
    if s.on("premium_media"):
        perks.append("• ارسال عکس، ویدیو، ویس و فایل در چت")
    if s.on("premium_priority"):
        perks.append("• اولویت در صف اتصال")
    if s.on("premium_free_search"):
        perks.append("• جستجوی دختر/پسر و فیلترها رایگان")
    if s.on("premium_free_edit"):
        perks.append("• ویرایش رایگان پروفایل")
    perks.append("👑 • نشان کنار پروفایل")
    text = "👑 **حساب ویژه**\n━━━━━━━━━━━━━━\n" + "\n".join(perks)
    if repo.is_premium(user):
        text += f"\n\n✅ اشتراک فعلی تا {jdate(user['premium_until'], 'full')} فعال است (تمدید به انتهای آن اضافه می‌شود)."
    rows = []
    if s.on("premium_purchase"):
        rows = [[b(f"{fa(d)} روزه • {fa(p)} تومان", f"w:pp:{d}", SUCCESS)] for d, p in s.premium_plans()]
    else:
        text += "\n\n⏸ فروش حساب ویژه فعلاً غیرفعال است."
    rows.append([b("🔙 بازگشت", "w:home")])
    await show(app, event, text, rows)


@router.callback_query(F.data.startswith("w:pp:"))
async def cb_plan(event: CallbackQuery, app: App, user: dict) -> None:
    days = parse_int((event.data or "").split(":")[2])
    await toast(event, "فاکتور در حال ساخت است...")
    if days:
        await invoice(app, user, "premium", days)


# ---------------------------------------------------------------- پرداخت
@router.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery, app: App) -> None:
    pay = await app.db.one("SELECT * FROM payments WHERE payload = ?", (query.invoice_payload,))
    ok = bool(pay) and pay["status"] == "pending" and pay["user_id"] == query.from_user.id \
        and pay["amount_irr"] == query.total_amount and query.currency == "IRR"
    try:
        await query.answer(ok, None if ok else "این فاکتور معتبر نیست یا قبلاً پرداخت شده است.")
    except Exception as exc:  # noqa: BLE001
        await app.error("pre_checkout", repr(exc))


@router.message(F.successful_payment)
async def paid(message: Message, app: App, user: dict) -> None:
    sp = message.successful_payment
    assert sp is not None
    credited = None
    async with app.db.tx() as tx:
        pay = await tx.one("SELECT * FROM payments WHERE payload = ?", (sp.invoice_payload,))
        if not pay or pay["user_id"] != user["id"] or pay["amount_irr"] != sp.total_amount:
            log.error("unmatched payment %s", sp.invoice_payload)
            credited = "unmatched"
        elif pay["status"] == "paid":
            credited = "duplicate"
        else:
            await tx.execute("UPDATE payments SET status = 'paid', paid_at = ?, charge_id = ? WHERE id = ?",
                             (now(), sp.provider_payment_charge_id or sp.telegram_payment_charge_id, pay["id"]))
            if pay["kind"] == "coin":
                bal = int(await tx.val("SELECT coins FROM users WHERE id = ?", (user["id"],), 0)) + pay["qty"]
                await tx.execute("UPDATE users SET coins = ? WHERE id = ?", (bal, user["id"]))
                await tx.execute(
                    "INSERT INTO wallet_tx(user_id, delta, balance, kind, ref, note, created_at) VALUES(?,?,?,?,?,?,?)",
                    (user["id"], pay["qty"], bal, "purchase", pay["payload"], "خرید سکه", now()))
                credited = ("coin", bal)
            else:
                cur = int(await tx.val("SELECT premium_until FROM users WHERE id = ?", (user["id"],), 0))
                until = max(cur, now()) + pay["qty"] * 86400
                await tx.execute("UPDATE users SET premium_until = ? WHERE id = ?", (until, user["id"]))
                credited = ("premium", until)
    if credited == "unmatched":
        await app.error("payment", f"unmatched payload {sp.invoice_payload} user {user['id']} amount {sp.total_amount}")
        return await app.send(user["id"], "⚠️ پرداخت شما دریافت شد اما فاکتور پیدا نشد. لطفاً با پشتیبانی تماس بگیر.",
                              [[b("🎧 پشتیبانی", "sp:home")]])
    if credited == "duplicate":
        return
    kind, val = credited  # type: ignore[misc]
    tracking = tracking_code(pay["payload"])
    charge = sp.provider_payment_charge_id or sp.telegram_payment_charge_id
    stamp = f"{jdate(now())} - {jdate(now(), 'time')}"
    lines = ["✅ پرداخت با موفقیت انجام شد!", ""]
    if kind == "coin":
        lines.append(f"🛍 بسته: {fa(pay['qty'])} سکه")
    else:
        lines.append(f"🛍 بسته: حساب ویژه {fa(pay['qty'])} روزه")
    lines.append(f"💵 مبلغ پرداختی: {_toman(pay['amount_irr'])} تومان")
    lines.append(f"🔖 کد پیگیری: {tracking}")
    if charge:
        lines.append(f"🏦 شناسه تراکنش: {charge}")
    lines.append(f"📅 تاریخ و ساعت: {stamp}")
    if kind == "coin":
        lines.append(f"🪙 موجودی جدید: {fa(val)} سکه")
        lines += ["", f"🎉 {fa(pay['qty'])} سکه با موفقیت به حساب شما افزوده شد."]
    else:
        lines.append(f"⏳ اعتبار تا: {jdate(val)} - {jdate(val, 'time')}")
        lines += ["", "👑 حساب ویژه شما با موفقیت فعال شد."]
    note = app.settings.get("receipt_note").strip()
    if note:
        lines += ["", f"ℹ️ {note}"]
    await app.send(user["id"], "\n".join(lines))
    await app.event(
        "💰 خرید موفق\n"
        f"👤 کاربر: {esc(user['name'], 30)} ({user['id']})\n"
        f"🛍 بسته: {fa(pay['qty'])} {'سکه' if kind == 'coin' else 'روز حساب ویژه'}\n"
        f"💵 مبلغ: {_toman(pay['amount_irr'])} تومان\n"
        f"🔖 کد پیگیری: {tracking}\n"
        f"📅 زمان: {stamp}", "payments")


# ---------------------------------------------------------------- کد هدیه
@router.callback_query(F.data == "w:gift")
async def cb_gift(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    await repo.set_step(app, user["id"], "gift")
    await show(app, event, "🎁 کد هدیه‌ات رو بفرست:", [[b("❌ انصراف", "w:home")]])


async def redeem(app: App, uid: int, code: str) -> tuple[bool, str]:
    code = code.strip().upper()
    async with app.db.tx() as tx:
        gift = await tx.one("SELECT * FROM gift_codes WHERE code = ?", (code,))
        if not gift or not gift["active"]:
            return False, "❌ کد هدیه معتبر نیست."
        if gift["expires_at"] and gift["expires_at"] < now():
            return False, "⌛️ مهلت این کد تمام شده است."
        if gift["used"] >= gift["max_uses"]:
            return False, "😕 ظرفیت استفاده از این کد تکمیل شده است."
        if await tx.one("SELECT 1 FROM gift_uses WHERE gift_id = ? AND user_id = ?", (gift["id"], uid)):
            return False, "شما قبلاً از این کد استفاده کرده‌اید."
        await tx.execute("INSERT INTO gift_uses(gift_id, user_id, used_at) VALUES(?,?,?)", (gift["id"], uid, now()))
        await tx.execute("UPDATE gift_codes SET used = used + 1 WHERE id = ?", (gift["id"],))
        if gift["reward_kind"] == "coin":
            bal = int(await tx.val("SELECT coins FROM users WHERE id = ?", (uid,), 0)) + gift["reward_qty"]
            await tx.execute("UPDATE users SET coins = ? WHERE id = ?", (bal, uid))
            await tx.execute(
                "INSERT INTO wallet_tx(user_id, delta, balance, kind, ref, note, created_at) VALUES(?,?,?,?,?,?,?)",
                (uid, gift["reward_qty"], bal, "gift", code, "کد هدیه", now()))
            return True, f"🎉 {fa(gift['reward_qty'])} سکه به حسابت اضافه شد! موجودی: {fa(bal)}"
        cur = int(await tx.val("SELECT premium_until FROM users WHERE id = ?", (uid,), 0))
        until = max(cur, now()) + gift["reward_qty"] * 86400
        await tx.execute("UPDATE users SET premium_until = ? WHERE id = ?", (until, uid))
        return True, f"🎉 {fa(gift['reward_qty'])} روز حساب ویژه فعال شد (تا {jdate(until, 'short')})."


@router.message(Step("gift"), F.text)
async def in_gift(message: Message, app: App, user: dict) -> None:
    ok, text = await redeem(app, user["id"], message.text or "")
    if ok:
        await app.event(f"🎁 استفاده از کد هدیه\n👤 کاربر: {esc(user['name'], 30)} ({user['id']})\n🔖 کد: {(message.text or '').strip().upper()}", "payments")
        await repo.set_step(app, user["id"], "")
    await app.send(user["id"], text, [[b("🛍 فروشگاه", "w:home"), b("🏠 منو", "m:home")]] if ok
                   else [[b("❌ انصراف", "w:home")]])


# ---------------------------------------------------------------- تراکنش‌ها / دعوت
@router.callback_query(F.data == "w:tx")
async def cb_tx(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    rows_db = await app.db.all("SELECT * FROM wallet_tx WHERE user_id = ? ORDER BY id DESC LIMIT 12", (user["id"],))
    if not rows_db:
        text = "📜 هنوز تراکنشی نداری."
    else:
        lines = [f"{TX_LABEL.get(r['kind'], '🔹 ' + r['kind'])}: {'+' if r['delta'] > 0 else '-'}{fa(abs(r['delta']))} سکه • {jdate(r['created_at'], 'day')}"
                 for r in rows_db]
        text = "📜 **آخرین تراکنش‌ها**\n━━━━━━━━━━━━━━\n" + "\n".join(lines)
    await show(app, event, text, [[b("🔙 بازگشت", "w:home")]])


@router.callback_query(F.data == "w:ref")
async def cb_ref(event: CallbackQuery, app: App, user: dict) -> None:
    await toast(event)
    if not app.settings.on("referral"):
        return await show(app, event, "⏸ سیستم دعوت فعلاً غیرفعال است.", [[b("🏠 منو", "m:home")]])
    link = app.start_link(f"ref_{user['id']}")
    invited = await app.db.val("SELECT COUNT(*) FROM users WHERE referrer_id = ?", (user["id"],), 0)
    paid_cnt = await app.db.val("SELECT COUNT(*) FROM users WHERE referrer_id = ? AND referral_paid = 1", (user["id"],), 0)
    reward = app.settings.int("referral_reward")
    text = (f"🎁 **دعوت دوستان**\n━━━━━━━━━━━━━━\nبه ازای هر دوستی که با لینک تو عضو بشه و ثبت‌نامش رو کامل کنه، "
            f"{fa(reward)} سکه می‌گیری!\n\n🔗 لینک دعوت تو:\n{link}\n\n"
            f"👥 دعوت‌شده‌ها: {fa(invited)}\n✅ ثبت‌نام کامل: {fa(paid_cnt)}\n🪙 درآمد: {fa(paid_cnt * reward)} سکه")
    await show(app, event, text, [[Button.copy_text("📋 کپی لینک دعوت", link, style=PRIMARY)],
                                  [b("🏠 منوی اصلی", "m:home")]])
