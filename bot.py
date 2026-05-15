#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ربات تلگرام فروش خودکار کانفیگ‌های VPN (اقتصادی و VIP) به زبان پایتون
امکانات:
1. مخازن کاملاً مجزا برای کانفیگ‌های اقتصادی و VIP (با پاکسازی خودکار جهت جلوگیری از ارسال تکراری)
2. سیستم شارژ کیف پول دستی (کارت به کارت با تایید رسید توسط ادمین) و درگاه زرین‌پال آنلاین
3. پنل فوق پیشرفته مدیریت ادمین (/panel یا .پنل) برای ادمین اصلی (Owner) و ادمین‌های فرعی
4. سیستم قفل عضویت اجباری کانال (Force Subscribe)
5. دستورات بن و آنبن کاربران (/ban و /unban)
6. مدیریت پویای شماره کارت ادمین و تغییر قیمت‌ها
7. ثبت کدهای تخفیف متنوع و تمدید خودکار/دستی
8. ذخیره‌سازی دائمی با دیتابیس SQLite3 در پایتون
"""

import sqlite3
import telebot
from telebot import types
import requests
import json
import os
import time
from datetime import datetime

# ==================== تنظیمات اولیه ====================
API_TOKEN = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"
OWNER_ID = int("12345678")  # شناسه تلگرام ادمین اصلی
SUPPORT_ID = "@jani_jorbeh"   # آیدی پشتیبانی تلگرام
REQUIRED_CHANNEL = "@my_vpn_channel" # کانال قفل عضویت اجباری (مثال: @my_channel)

bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML")

# ==================== مقداردهی دیتابیس SQLite ====================
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    # جدول کاربران
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        role TEXT DEFAULT 'user', -- owner, admin, user
        status TEXT DEFAULT 'active' -- active, banned
    )""")
    
    # جدول مخزن کانفیگ‌ها
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configs_repo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        config_type TEXT, -- economic / vip
        config_code TEXT UNIQUE,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # جدول کانفیگ‌های فروخته شده به کاربران
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS purchased_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        config_type TEXT,
        config_code TEXT,
        price INTEGER,
        purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # جدول تراکنش‌های مالی (شارژ کیف پول)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        status TEXT DEFAULT 'pending', -- pending, approved, rejected
        receipt_photo_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    # جدول کدهای تخفیف
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS discount_codes (
        code TEXT PRIMARY KEY,
        discount_type TEXT, -- percent / fixed
        value INTEGER,
        max_usage INTEGER,
        used_count INTEGER DEFAULT 0
    )""")
    
    # جدول تنظیمات پویا (شماره کارت، قیمت‌ها و غیره)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    
    # مقادیر پیش‌فرض تنظیمات
    defaults = [
        ("card_number", "6063-7312-8871-7607"),
        ("card_owner", "علی اصغر سوری"),
        ("price_economic", "300"),
        ("price_vip", "480000"),
        ("channel_lock_enabled", "1")
    ]
    for k, v in defaults:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        
    # ثبت ادمین اصلی
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, balance, role, status) VALUES (?, ?, ?, ?, ?)", 
                   (OWNER_ID, "OwnerAdmin", 0, "owner", "active"))
                   
    conn.commit()
    conn.close()

init_db()

# ==================== توابع کمکی پایگاه داده ====================
def get_setting(key, default=""):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cursor.fetchone()
    conn.close()
    return row[0] if row else default

def set_setting(key, value):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, str(value)))
    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, username, balance, role, status FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {"user_id": row[0], "username": row[1], "balance": row[2], "role": row[3], "status": row[4]}
    return None

def add_user_if_not_exists(user_id, username):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, role, status) VALUES (?, ?, 'user', 'active')", 
                   (user_id, username or "Unknown"))
    conn.commit()
    conn.close()

# ==================== میدلور بررسی بن و عضویت اجباری ====================
def check_user_status(user_id):
    user = get_user(user_id)
    if user and user["status"] == "banned":
        return "banned"
    return "ok"

def check_force_subscribe(user_id):
    if get_setting("channel_lock_enabled") != "1":
        return True
    try:
        # برای قفل عضویت اجباری، ربات باید در کانال ادمین باشد
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        if member.status in ['creator', 'administrator', 'member']:
            return True
    except Exception as e:
        # در صورت بروز خطا (مثلا کانال یافت نشد یا ربات ادمین نیست) عضویت را تایید می‌کنیم تا ربات متوقف نشود
        return True
    return False

# ==================== منوهای کیبورد تلگرام ====================
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    
    btn_buy = types.KeyboardButton("🛍 خرید کانفیگ")
    btn_wallet = types.KeyboardButton("💳 کیف پول من")
    btn_configs = types.KeyboardButton("🛡 کانفیگ‌های من")
    btn_support = types.KeyboardButton("📞 پشتیبانی")
    
    markup.add(btn_buy, btn_wallet)
    markup.add(btn_configs, btn_support)
    
    # دکمه ورود به پنل برای ادمین‌ها
    user = get_user(user_id)
    if user and user["role"] in ["owner", "admin"]:
        markup.add(types.KeyboardButton("⚙️ ورود به پنل مدیریت"))
        
    return markup

# ==================== پاسخ به پیام‌های ربات ====================
@bot.message_handler(commands=['start'])
def welcome_start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    add_user_if_not_exists(user_id, username)
    
    if check_user_status(user_id) == "banned":
        bot.send_message(user_id, "❌ متاسفانه حساب کاربری شما مسدود شده است و امکان استفاده از ربات را ندارید.")
        return
        
    if not check_force_subscribe(user_id):
        send_force_sub_msg(user_id)
        return
        
    welcome_text = (
        "سلام! به ربات فروش خودکار کانفیگ‌های اختصاصی خوش آمدید. ⚡️🛡\n\n"
        "با استفاده از منوی زیر به راحتی می‌توانید با موجودی کیف پول خود یا از طریق درگاه مستقیم بانکی کانفیگ بخرید.\n"
        "کانفیگ‌ها بلافاصله پس از خرید از مخزن استخراج شده و به شما ارائه می‌گردد."
    )
    bot.send_message(user_id, welcome_text, reply_markup=main_keyboard(user_id))

def send_force_sub_msg(user_id):
    markup = types.InlineKeyboardMarkup()
    btn_link = types.InlineKeyboardButton("عضویت در کانال رسمی 📢", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}")
    btn_check = types.InlineKeyboardButton("عضو شدم ✅ (بررسی مجدد)", callback_data="check_subscription")
    markup.add(btn_link)
    markup.add(btn_check)
    bot.send_message(
        user_id,
        f"⚠️ <b>جهت استفاده از امکانات ربات ابتدا باید عضو کانال زیر شوید:</b>\n\n"
        f"📢 {REQUIRED_CHANNEL}\n\n"
        f"پس از عضویت، دکمه زیر را بفشارید 👇",
        reply_markup=markup
    )

# ==================== فرآیند خرید کانفیگ ====================
@bot.message_handler(func=lambda message: message.text == "🛍 خرید کانفیگ")
def choose_config_type(message):
    user_id = message.from_user.id
    if check_user_status(user_id) == "banned": return
    if not check_force_subscribe(user_id):
        send_force_sub_msg(user_id); return
        
    price_econ = get_setting("price_economic")
    price_vip = get_setting("price_vip")
    
    markup = types.InlineKeyboardMarkup(row_width=1)
    btn_econ = types.InlineKeyboardButton(f"💰 پنل اقتصادی (گیگی {int(price_econ):,} تومان)", callback_data="buy_economic")
    btn_vip = types.InlineKeyboardButton(f"💎 پنل VIP (گیگی {int(price_vip):,} تومان)", callback_data="buy_vip")
    markup.add(btn_econ, btn_vip)
    
    bot.send_message(
        user_id,
        "⚡️ <b>لطفاً نوع سرویس درخواستی خود را انتخاب کنید:</b>\n\n"
        "1️⃣ <b>پنل اقتصادی:</b> سرعت عالی، آی‌پی نیمه‌اختصاصی، پایدار\n"
        "2️⃣ <b>پنل VIP:</b> بالاترین سرعت، آی‌پی کاملاً اختصاصی و ثابت، مناسب گیم و بورس",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_purchase_callbacks(call):
    user_id = call.from_user.id
    config_type = call.data.replace("buy_", "") # economic or vip
    type_label = "اقتصادی" if config_type == "economic" else "VIP"
    price = int(get_setting(f"price_{config_type}"))
    
    bot.answer_callback_query(call.id)
    
    # بررسی اتمام مخزن کانفیگ‌ها قبل از هر کار
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, config_code FROM configs_repo WHERE config_type = ? LIMIT 1", (config_type,))
    config_row = cursor.fetchone()
    conn.close()
    
    if not config_row:
        # اگر مخزن خالی باشد، تمدید/خرید دستی از ادمین
        markup = types.InlineKeyboardMarkup()
        btn_notify = types.InlineKeyboardButton("ارسال درخواست خرید دستی به پشتیبانی 💬", callback_data=f"manual_request_{config_type}")
        markup.add(btn_notify)
        
        bot.send_message(
            user_id,
            f"❌ متاسفانه در حال حاضر هیچ کانفیگ آماده‌ای در مخزن <b>{type_label}</b> موجود نیست.\n"
            f"اما می‌توانید با زدن دکمه زیر به صورت مستقیم از پشتیبانی درخواست ارسال دستی ثبت کنید:",
            reply_markup=markup
        )
        return

# بررسی موجودی کاربر
    user = get_user(user_id)
    if user["balance"] < price:
        # هدایت به افزایش موجودی
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_card = types.InlineKeyboardButton("💳 پرداخت کارت به کارت", callback_data=f"pay_card_{config_type}")
        btn_online = types.InlineKeyboardButton("⚡️ درگاه مستقیم بانکی", callback_data=f"pay_online_{config_type}")
        markup.add(btn_card, btn_online)
        
        bot.send_message(
            user_id,
            f"❌ <b>موجودی کیف پول شما برای این خرید کافی نیست!</b>\n"
            f"قیمت کانفیگ: {price:,} تومان\n"
            f"موجودی شما: {user['balance']:,} تومان\n\n"
            f"یکی از روش‌های پرداخت زیر را برای تهیه آنی کانفیگ انتخاب کنید:",
            reply_markup=markup
        )
        return
        
    # تحویل آنی کانفیگ و کسر از کیف پول و حذف از مخزن
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    config_db_id, config_code = config_row
    
    # کسر هزینه از کیف پول
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
    # حذف از مخزن به صورت آنی (جلوگیری از توزیع مجدد)
    cursor.execute("DELETE FROM configs_repo WHERE id = ?", (config_db_id,))
    # ثبت خرید در دیتابیس
    cursor.execute("INSERT INTO purchased_configs (user_id, config_type, config_code, price) VALUES (?, ?, ?, ?)", 
                   (user_id, config_type, config_code, price))
    
    conn.commit()
    conn.close()
    
    success_msg = (
        f"🎉 <b>خرید موفقیت‌آمیز بود!</b>\n"
        f"مبلغ {price:,} تومان از کیف پول شما کسر شد.\n\n"
        f"🔑 <b>کانفیگ اختصاصی شما (حذف شده از مخزن ربات):</b>\n\n"
        f"<code dir='ltr'>{config_code}</code>\n\n"
        f"سرویس خریداری شده را در نرم‌افزارهای مرتبط (V2rayNG و غیره) ایمپورت کنید."
    )
    bot.send_message(user_id, success_msg)

# ==================== درگاه پرداخت آنلاین (زرین‌پال فرضی) ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_online_"))
def zarinpal_payment_init(call):
    user_id = call.from_user.id
    config_type = call.data.replace("pay_online_", "")
    price = int(get_setting(f"price_{config_type}"))
    
    bot.answer_callback_query(call.id)
    bot.send_message(user_id, "🔗 در حال تولید لینک امن پرداخت زرین‌پال... لطفاً شکیبا باشید.")
    
    # شبیه‌سازی ساخت درگاه بانکی در وب هوک
    # در پروژه واقعی، با استفاده از requests به زرین‌پال متصل می‌شوید
    # API Zarinpal: https://api.zarinpal.com/pg/v4/payment/request.json
    
    time.sleep(1)
    # نمایش لینک و تراکنش فرضی
    markup = types.InlineKeyboardMarkup()
    btn_pay = types.InlineKeyboardButton("💳 پرداخت امن درگاه (شبیه‌سازی درگاه)", callback_data=f"verify_online_{config_type}_{price}")
    markup.add(btn_pay)
    bot.send_message(
        user_id,
        f"💳 فاکتور خرید آنلاین کانفیگ {config_type.upper()}\n"
        f"مبلغ قابل پرداخت: {price:,} تومان\n\n"
        f"جهت پرداخت و دریافت آنی کانفیگ روی دکمه پرداخت زیر کلیک کنید:",
        reply_markup=markup
    )

@bot.callback_query_handler(func=lambda call: call.data.startswith("verify_online_"))
def verify_online_payment(call):
    user_id = call.from_user.id
    parts = call.data.split("_")
    config_type = parts[2]
    price = int(parts[3])
    
    bot.answer_callback_query(call.id)
    
    # چک کردن دوباره مخزن
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT id, config_code FROM configs_repo WHERE config_type = ? LIMIT 1", (config_type,))
    config_row = cursor.fetchone()
    
    if not config_row:
        # مخزن خالی شده است. مبلغ را به کیف پول اضافه می‌کنیم
        cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (price, user_id))
        conn.commit()
        conn.close()
        bot.send_message(
            user_id, 
            f"❌ پرداخت با موفقیت انجام شد اما به دلیل اتمام موجودی مخزن، مبلغ {price:,} تومان به کیف پول شما واریز شد."
        )
        return
        
    config_db_id, config_code = config_row
    # حذف و ثبت خرید
    cursor.execute("DELETE FROM configs_repo WHERE id = ?", (config_db_id,))
    cursor.execute("INSERT INTO purchased_configs (user_id, config_type, config_code, price) VALUES (?, ?, ?, ?)", 
                   (user_id, config_type, config_code, price))
    conn.commit()
    conn.close()
    
    bot.send_message(
        user_id,
        f"⚡️ <b>پرداخت آنلاین تایید شد!</b>\n"
        f"کانفیگ استخراج شده از مخزن:\n\n"
        f"<code dir='ltr'>{config_code}</code>"
    )

# ==================== بخش شارژ دستی کارت به کارت ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_card_"))
def card_payment_init(call):
    user_id = call.from_user.id
    config_type = call.data.replace("pay_card_", "")
    price = int(get_setting(f"price_{config_type}"))
    
    bot.answer_callback_query(call.id)
    
    # هدایت به شارژ کارت به کارت
    card_number = get_setting("card_number")
    card_owner = get_setting("card_owner")
    
    bot.send_message(
        user_id,
        f"💳 <b>انتقال کارت به کارت</b>\n\n"
        f"لطفاً مبلغ <b>{price:,} تومان</b> را به شماره کارت زیر واریز کنید:\n"
        f"💳 شماره کارت: <pre>{card_number}</pre>\n"
        f"👤 به نام: <b>{card_owner}</b>\n\n"
        f"پس از واریز، رسید پرداخت خود را در قالب تصویر یا متن فیش ارسال کنید تا توسط مدیریت تایید شود."
    )
    # ذخیره حالت انتظار برای دریافت فیش
    bot.register_next_step_handler_by_chat_id(user_id, receive_receipt_photo, price)

def receive_receipt_photo(message, amount):
    user_id = message.from_user.id
    photo_id = None
    
    if message.photo:
        photo_id = message.photo[-1].file_id
    elif message.text:
        photo_id = "text:" + message.text
    else:
        bot.send_message(user_id, "❌ فرمت ارسالی نامعتبر است. لطفاً مجدداً فاکتور گرفته یا رسید بفرستید.")
        return
        
    # ذخیره تراکنش در دیتابیس به عنوان در انتظار تایید
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO transactions (user_id, amount, status, receipt_photo_id) VALUES (?, ?, 'pending', ?)", 
                   (user_id, amount, photo_id))
    tx_id = cursor.lastrowid
    conn.commit()
    conn.close()
    
    bot.send_message(user_id, "⏳ رسید شما با موفقیت برای ادمین ارسال شد. به محض تایید ادمین، کانفیگ برایتان باز خواهد شد.")
    
    # ارسال رسید برای ادمین اصلی
    markup = types.InlineKeyboardMarkup()
    btn_approve = types.InlineKeyboardButton("✅ تایید پرداخت", callback_data=f"admin_approve_{tx_id}")
    btn_reject = types.InlineKeyboardButton("❌ رد پرداخت", callback_data=f"admin_reject_{tx_id}")
    markup.add(btn_approve, btn_reject)
    
    admin_msg = (
        f"🔔 <b>درخواست شارژ جدید (کارت به کارت)</b>\n"
        f"کد تراکنش: #{tx_id}\n"
        f"کاربر: @{message.from_user.username or 'بدون_یوزرنیم'} (شناسه: {user_id})\n"
        f"مبلغ واریزی: {amount:,} تومان"
    )
    
    if photo_id and not photo_id.startswith("text:"):
        bot.send_photo(OWNER_ID, photo_id, caption=admin_msg, reply_markup=markup)
    else:
        text_receipt = photo_id.replace("text:", "")
        bot.send_message(OWNER_ID, f"{admin_msg}\n📝 متن ارسالی کاربر:\n{text_receipt}", reply_markup=markup)

# ==================== کیف پول کاربری ====================
@bot.message_handler(func=lambda message: message.text == "💳 کیف پول من")
def show_wallet(message):
    user_id = message.from_user.id
    if check_user_status(user_id) == "banned": return
    
    user = get_user(user_id)
    bot.send_message(
        user_id,
        f"💳 <b>کیف پول دیجیتال شما</b>\n\n"
        f"موجودی فعلی: <b>{user['balance']:,} تومان</b>\n\n"
        f"شما می‌توانید با گزینه افزایش موجودی کیف پول خود را همواره پر نگه دارید.",
        reply_markup=types.InlineKeyboardMarkup([
            [types.InlineKeyboardButton("➕ افزایش اعتبار کیف پول", callback_data="charge_wallet_step1")]
        ])
    )

@bot.callback_query_handler(func=lambda call: call.data == "charge_wallet_step1")
def wallet_charge_amount(call):
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)
    
    bot.send_message(user_id, "💰 لطفاً مبلغی را که می‌خواهید شارژ کنید به تومان وارد کنید (مثلاً 50000):")
    bot.register_next_step_handler_by_chat_id(user_id, wallet_charge_receipt_ask)

def wallet_charge_receipt_ask(message):
    user_id = message.from_user.id
    try:
        amount = int(message.text)
        if amount <= 0: raise ValueError
    except:
        bot.send_message(user_id, "❌ مقدار وارد شده باید یک عدد بزرگتر از صفر باشد. لطفاً مجدد امتحان کنید.")
        return
        
    card_number = get_setting("card_number")
    card_owner = get_setting("card_owner")
    
    bot.send_message(
        user_id,
        f"💳 <b>شارژ حساب به مبلغ {amount:,} تومان</b>\n\n"
        f"جهت شارژ، مبلغ را به کارت زیر واریز نمایید:\n"
        f"💳 شماره کارت: <pre>{card_number}</pre>\n"
        f"👤 به نام: <b>{card_owner}</b>\n\n"
        f"سپس فیش واریزی خود را به صورت عکس یا متن ارسال نمایید."
    )
    bot.register_next_step_handler_by_chat_id(user_id, receive_receipt_photo, amount)

# ==================== تایید و رد تراکنش‌ها توسط ادمین ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("admin_"))
def process_admin_decisions(call):
    user_id = call.from_user.id
    # فقط ادمین اصلی یا ادمین‌های ثبت شده مجازند
    user = get_user(user_id)
    if not user or user["role"] not in ["owner", "admin"]:
        bot.answer_callback_query(call.id, "⛔️ غیرمجاز", show_alert=True)
        return
        
    part