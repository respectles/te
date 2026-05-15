#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ربات تلگرام فروش خودکار کانفیگ‌های VPN (اقتصادی و VIP)
"""

import sqlite3
import telebot
from telebot import types
import time
from datetime import datetime

# ==================== تنظیمات اولیه ====================
API_TOKEN = "123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ"  # ← تغییر دهید
OWNER_ID = 12345678  # ← تغییر دهید
SUPPORT_ID = "@jani_jorbeh"
REQUIRED_CHANNEL = "@my_vpn_channel"

bot = telebot.TeleBot(API_TOKEN, parse_mode="HTML")

# ==================== دیتابیس ====================
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        user_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        role TEXT DEFAULT 'user',
        status TEXT DEFAULT 'active'
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configs_repo (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        config_type TEXT,
        config_code TEXT UNIQUE,
        added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS purchased_configs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        config_type TEXT,
        config_code TEXT,
        price INTEGER,
        purchase_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS transactions (
        tx_id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        amount INTEGER,
        status TEXT DEFAULT 'pending',
        receipt_photo_id TEXT,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    
    defaults = [
        ("card_number", "6063-7312-8871-7607"),
        ("card_owner", "علی اصغر سوری"),
        ("price_economic", "300000"),
        ("price_vip", "480000"),
        ("channel_lock_enabled", "1")
    ]
    for k, v in defaults:
        cursor.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
    
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username, role, status) VALUES (?, ?, ?, ?)", 
                   (OWNER_ID, "Owner", 0, "owner", "active"))
    
    conn.commit()
    conn.close()

init_db()

# ==================== توابع دیتابیس ====================
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

# ==================== چک کردن وضعیت کاربر ====================
def check_user_status(user_id):
    user = get_user(user_id)
    if user and user["status"] == "banned":
        return "banned"
    return "ok"

def check_force_subscribe(user_id):
    if get_setting("channel_lock_enabled") != "1":
        return True
    try:
        member = bot.get_chat_member(REQUIRED_CHANNEL, user_id)
        return member.status in ['creator', 'administrator', 'member']
    except:
        return False  # بهتر است False برگرداند تا کاربر مجبور به عضویت شود

# ==================== کیبوردها ====================
def main_keyboard(user_id):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🛍 خرید کانفیگ"))
    markup.add(types.KeyboardButton("💳 کیف پول من"), types.KeyboardButton("🛡 کانفیگ‌های من"))
    markup.add(types.KeyboardButton("📞 پشتیبانی"))
    
    user = get_user(user_id)
    if user and user["role"] in ["owner", "admin"]:
        markup.add(types.KeyboardButton("⚙️ ورود به پنل مدیریت"))
    return markup

# ==================== هندلرها ====================
@bot.message_handler(commands=['start'])
def welcome_start(message):
    user_id = message.from_user.id
    username = message.from_user.username
    add_user_if_not_exists(user_id, username)
    
    if check_user_status(user_id) == "banned":
        bot.send_message(user_id, "❌ حساب شما مسدود شده است.")
        return
        
    if not check_force_subscribe(user_id):
        send_force_sub_msg(user_id)
        return
        
    text = "سلام! به ربات فروش کانفیگ VPN خوش آمدید ⚡️\nاز منوی زیر استفاده کنید."
    bot.send_message(user_id, text, reply_markup=main_keyboard(user_id))

def send_force_sub_msg(user_id):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("عضویت در کانال", url=f"https://t.me/{REQUIRED_CHANNEL.replace('@', '')}"))
    markup.add(types.InlineKeyboardButton("عضو شدم ✅", callback_data="check_subscription"))
    bot.send_message(user_id, f"⚠️ برای استفاده از ربات ابتدا عضو کانال شوید:\n\n{REQUIRED_CHANNEL}", reply_markup=markup)

# ==================== خرید کانفیگ ====================
@bot.message_handler(func=lambda m: m.text == "🛍 خرید کانفیگ")
def choose_config_type(message):
    user_id = message.from_user.id
    if check_user_status(user_id) == "banned": return
    if not check_force_subscribe(user_id):
        send_force_sub_msg(user_id); return

    price_econ = int(get_setting("price_economic"))
    price_vip = int(get_setting("price_vip"))

    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton(f"💰 اقتصادی - {price_econ:,} تومان", callback_data="buy_economic"))
    markup.add(types.InlineKeyboardButton(f"💎 VIP - {price_vip:,} تومان", callback_data="buy_vip"))
    
    bot.send_message(user_id, "نوع سرویس مورد نظر را انتخاب کنید:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("buy_"))
def handle_purchase_callbacks(call):
    user_id = call.from_user.id
    config_type = call.data.replace("buy_", "")
    price = int(get_setting(f"price_{config_type}"))
    type_label = "اقتصادی" if config_type == "economic" else "VIP"

    bot.answer_callback_query(call.id)

    # بررسی موجودی کانفیگ با لاک
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("BEGIN IMMEDIATE")
    cursor.execute("SELECT id, config_code FROM configs_repo WHERE config_type = ? LIMIT 1", (config_type,))
    config_row = cursor.fetchone()

    if not config_row:
        conn.rollback()
        conn.close()
        bot.send_message(user_id, f"❌ موجودی کانفیگ {type_label} تمام شده است.")
        return

    user = get_user(user_id)
    if user["balance"] < price:
        conn.rollback()
        conn.close()
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("💳 کارت به کارت", callback_data=f"pay_card_{config_type}"),
            types.InlineKeyboardButton("⚡️ پرداخت آنلاین", callback_data=f"pay_online_{config_type}")
        )
        bot.send_message(user_id, f"❌ موجودی کافی نیست!\nقیمت: {price:,} تومان\nموجودی شما: {user['balance']:,} تومان", 
                        reply_markup=markup)
        return

    # خرید موفق
    config_id, config_code = config_row
    cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (price, user_id))
    cursor.execute("DELETE FROM configs_repo WHERE id = ?", (config_id,))
    cursor.execute("INSERT INTO purchased_configs (user_id, config_type, config_code, price) VALUES (?, ?, ?, ?)",
                   (user_id, config_type, config_code, price))
    conn.commit()
    conn.close()

    bot.send_message(user_id,
        f"🎉 خرید موفق!\n\n"
        f"🔑 کانفیگ شما:\n<code>{config_code}</code>",
        parse_mode="HTML"
    )

# ==================== پرداخت آنلاین (شبیه‌سازی) ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_online_"))
def zarinpal_payment_init(call):
    # ... (شبیه‌سازی)
    bot.answer_callback_query(call.id)
    bot.send_message(call.from_user.id, "🔗 در حال اتصال به درگاه... (شبیه‌سازی)")

# ==================== کارت به کارت ====================
@bot.callback_query_handler(func=lambda call: call.data.startswith("pay_card_"))
def card_payment_init(call):
    user_id = call.from_user.id
    config_type = call.data.replace("pay_card_", "")
    price = int(get_setting(f"price_{config_type}"))
    
    bot.answer_callback_query(call.id)
    
    card_number = get_setting("card_number")
    card_owner = get_setting("card_owner")
    
    bot.send_message(user_id,
        f"💳 واریز مبلغ {price:,} تومان به:\n"
        f"<pre>{card_number}</pre>\n"
        f"به نام: {card_owner}\n\n"
        f"رسید را ارسال کنید."
    )
    bot.register_next_step_handler_by_chat_id(user_id, receive_receipt_photo, price, config_type)

def receive_receipt_photo(message, amount, config_type=None):
    user_id = message.from_user.id
    photo_id = message.photo[-1].file_id if message.photo else f"text:{message.text}"

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO transactions (user_id, amount, receipt_photo_id) VALUES (?, ?, ?)", 
                   (user_id, amount, photo_id))
    tx_id = cursor.lastrowid
    conn.commit()
    conn.close()

    bot.send_message(user_id, "✅ رسید ثبت شد. در حال بررسی توسط ادمین...")

    # ارسال به ادمین
    markup = types.InlineKeyboardMarkup()
    markup.add(
        types.InlineKeyboardButton("✅ تایید", callback_data=f"admin_approve_{tx_id}"),
        types.InlineKeyboardButton("❌ رد", callback_data=f"admin_reject_{tx_id}")
    )
    
    if photo_id.startswith("text:"):
        bot.send_message(OWNER_ID, f"رسید جدید #{tx_id}\nمبلغ: {amount:,}", reply_markup=markup)
    else:
        bot.send_photo(OWNER_ID, photo_id, caption=f"رسید جدید #{tx_id}\nمبلغ: {amount:,}", reply_markup=markup)

# ==================== سایر هندلرها (کیف پول، کانفیگ‌ها، پشتیبانی و ...) ====================
# ... (بقیه کدهای شما که سالم بودند)

@bot.callback_query_handler(func=lambda call: call.data == "check_subscription")
def check_subscription_callback(call):
    user_id = call.from_user.id
    bot.answer_callback_query(call.id)
    if check_force_subscribe(user_id):
        bot.send_message(user_id, "✅ عضویت تایید شد!", reply_markup=main_keyboard(user_id))
    else:
        send_force_sub_msg(user_id)

# پنل مدیریت (نمونه)
@bot.message_handler(func=lambda m: m.text in ["⚙️ ورود به پنل مدیریت", "پنل"])
def admin_panel(message):
    user = get_user(message.from_user.id)
    if not user or user["role"] not in ["owner", "admin"]:
        return bot.send_message(message.from_user.id, "⛔️ دسترسی ندارید.")
    # ادامه پنل...

# ==================== اجرای ربات ====================
if __name__ == "__main__":
    print("✅ ربات در حال اجرا...")
    bot.infinity_polling(none_stop=True)