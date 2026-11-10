<!--
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
-->

<div dir="rtl">

<h1 align="center">💬 بینام | ربات چت و پیام ناشناس بله</h1>

<p align="center">
یک ربات فارسی برای گفت‌وگوی ناشناس، آشنایی با افراد جدید و دریافت پیام ناشناس در پیام‌رسان بله.
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python&logoColor=white" alt="Python">
  <img src="https://img.shields.io/badge/Platform-Bale-00A884" alt="Bale">
  <img src="https://img.shields.io/badge/Library-baleropy-6C5CE7" alt="baleropy">
  <img src="https://img.shields.io/badge/Database-SQLite-003B57?logo=sqlite&logoColor=white" alt="SQLite">
</p>

---

## ✨ امکانات

- گفت‌وگوی ناشناس تصادفی و جست‌وجو با فیلترهای مختلف
- ساخت لینک اختصاصی برای دریافت پیام ناشناس
- پروفایل، دوستی، گزارش و مسدودکردن کاربران
- کیف پول، سکه و حساب ویژه
- پنل مدیریت برای تنظیمات، کاربران، گزارش‌ها و پیام همگانی
- ذخیره‌سازی اطلاعات در SQLite

## 🧰 فناوری‌ها و کتابخانه‌ها

- **[baleropy](https://pypi.org/project/baleropy/)**: کتابخانهٔ ساخت ربات و ارتباط با پیام‌رسان بله
- **[aiosqlite](https://pypi.org/project/aiosqlite/)**: دسترسی ناهمگام به پایگاه دادهٔ SQLite
- **SQLite**: نگه‌داری داده‌های ربات در فایل محلی

## 🚀 نصب و اجرا

### پیش‌نیاز

Python نسخهٔ **۳٫۱۰ یا جدیدتر** را نصب کنید.

### ۱. دریافت پروژه و نصب وابستگی‌ها

```bash
git clone https://github.com/rezamardani01/BiNamChat.git
cd BiNamChat
python -m venv .venv
```

فعال‌سازی محیط مجازی:

**ویندوز (PowerShell):**

```powershell
.\.venv\Scripts\Activate.ps1
```

**لینوکس یا macOS:**

```bash
source .venv/bin/activate
```

سپس کتابخانه‌های موردنیاز را نصب کنید:

```bash
python -m pip install -r requirements.txt
```

### ۲. تنظیم توکن و شناسهٔ مالک

در پوشهٔ اصلی پروژه یک فایل به نام `config.py` بسازید و این تنظیمات را در آن قرار دهید:

```python
TOKEN = "توکن ربات بله"
OWNER_ID = 123456789  # شناسه عددی حساب مالک، بدون کوتیشن
```

توکن را از **BotFather بله** دریافت کنید. مقدار `OWNER_ID` باید شناسهٔ عددی حساب مالک باشد، نه نام کاربری. فایل `config.py` عمداً در Git نادیده گرفته می‌شود تا توکن و تنظیمات خصوصی وارد ریپازیتوری نشوند.

### ۳. اجرای ربات

```bash
python run.py
```

با اولین اجرا، پایگاه داده و فایل‌های گزارش در پوشهٔ `data` ساخته می‌شوند. برای توقف ربات از `Ctrl+C` استفاده کنید.

## 🗂 ساختار پروژه

```text
binam/
├── data/
│   └── geo.json          # فهرست استان‌ها و شهرها
├── run.py                # نقطهٔ شروع اجرا
├── src/
│   ├── app.py            # اجرای ربات
│   ├── admin/            # پنل مدیریت
│   ├── handlers/         # مدیریت پیام‌ها
│   └── ...               # سایر فایل‌های اصلی برنامه
├── requirements.txt      # وابستگی‌ها
├── config.py             # تنظیمات محلی؛ در Git ثبت نمی‌شود
└── README.md
```

## 🔐 نکتهٔ امنیتی

توکن ربات را در کد عمومی، تصویر، پیام یا فایل قابل‌انتشار قرار ندهید. اگر توکن افشا شد، آن را فوراً از طریق BotFather باطل و دوباره تولید کنید.

</div>
