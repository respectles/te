#!/usr/bin/env python
# -*- coding: utf-8 -*-
import telebot
from telebot import types
import sqlite3
import datetime
import os

BOT_TOKEN = "8570590196:AAFvSG85QNkvFahkuqnQ5skDVatQsaVZsWo"
OWNER_ID = 7345545445
DB_FILE = "vpn_database.db"

bot = telebot.TeleBot(BOT_TOKEN)

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        chat_id INTEGER PRIMARY KEY,
        username TEXT,
        balance INTEGER DEFAULT 0,
        total_bought INTEGER DEFAULT 0,
        is_banned INTEGER DEFAULT 0,
        role TEXT DEFAULT 'user'
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS configs_stock (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        config_text TEXT,
        is_sold INTEGER DEFAULT 0,
        added_at TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS kv_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    cursor.execute("INSERT OR IGNORE INTO kv_settings (key, value) VALUES ('card_number', '6063-7312-8871-7607')")
    cursor.execute("INSERT OR IGNORE INTO kv_settings (key, value) VALUES ('card_holder', 'علی اصغر سوری')")
    cursor.execute("INSERT OR IGNORE INTO kv_settings (key, value) VALUES ('channel_id', '@AODvpn')")
    cursor.execute("INSERT OR IGNORE INTO kv_settings (key, value) VALUES ('channel_lock', '1')")
    cursor.execute("INSERT OR IGNORE INTO kv_settings (key, value) VALUES ('economy_price', '300000')")
    cursor.execute("INSERT OR IGNORE INTO kv_settings (key, value) VALUES ('vip_price', '480000')")
    conn.commit()
    conn.close()

def get_db_setting(key, fallback=""):
    try:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT value FROM kv_settings WHERE key=?", (key,))
        row = c.fetchone()
        conn.close()
        return row[0] if row else fallback
    except:
        return fallback

@bot.message_handler(commands=['panel', 'پنل'])
def handle_admin_panel(message):
    if message.chat.id != OWNER_ID:
        bot.reply_to(message, "⛔️ خطا: شما دسترسی به پنل مدیریت مالک را ندارید.")
        return
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("تغییر شماره کارت", callback_data="adm_card"),
        types.InlineKeyboardButton("وضعیت قفل چنل", callback_data="adm_lock")
    )
    markup.add(
        types.InlineKeyboardButton("بن / آن بن کاربر", callback_data="adm_ban"),
        types.InlineKeyboardButton("تعداد کل کاربران", callback_data="adm_count")
    )
    markup.add(types.InlineKeyboardButton("مشاهده لیست کانفیگ دستی", callback_data="adm_add_config"))
    bot.send_message(message.chat.id, "⚙️ **پنل مدیریت مالک ربات:**\n\nاز منوی شیشه‌ای زیر اقدام کنید:", reply_markup=markup)

@bot.message_handler(func=lambda msg: True)
def text_reply_handler(message):
    chat_id = message.chat.id
    text = message.text
    
    # اضافه کردن دستی کانفیگ توسط خود مالک
    if chat_id == OWNER_ID and (text.startswith("vless://") or text.startswith("vmess://")):
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("INSERT INTO configs_stock (config_text) VALUES (?)", (text,))
        conn.commit()
        conn.close()
        bot.reply_to(message, "✅ کانفیگ ارسالی شما با موفقیت به انبار دستی اضافه شد و به نوبت فروخته خواهد شد.")
        return

    if text == "🚀 خرید سرویس":
        markup = types.InlineKeyboardMarkup()
        eco_p = get_db_setting('economy_price', '300000')
        vip_p = get_db_setting('vip_price', '480000')
        markup.add(
            types.InlineKeyboardButton(f"⭐️ خرید پلن اقتصادی ({eco_p} تومان)", callback_data="buy_from_stock_eco"),
            types.InlineKeyboardButton(f"⚡️ خرید پلن VIP ({vip_p} تومان)", callback_data="buy_from_stock_vip")
        )
        bot.send_message(chat_id, "🛒 **یکی از دسته‌بندی‌ها را انتخاب کنید:**", reply_markup=markup)
        
    elif text == "⭐️ خرید کانفیگ اقتصادی":
        eco_p = get_db_setting('economy_price', '300000')
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"🟢 تایید و کسر {eco_p} تومان از کیف پول", callback_data="buy_from_stock_eco"))
        bot.send_message(chat_id, f"📦 قیمت مصوب دیتابیس برای سرور اقتصادی: {eco_p} تومان", reply_markup=markup)
        
    elif text == "⚡️ خرید کانفیگ VIP":
        vip_p = get_db_setting('vip_price', '480000')
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton(f"👑 تایید و کسر {vip_p} تومان از کیف پول", callback_data="buy_from_stock_vip"))
        bot.send_message(chat_id, f"📦 قیمت مصوب دیتابیس برای سرور VIP: {vip_p} تومان", reply_markup=markup)
        
    elif text == "💰 شارژ کیف پول":
        bot.send_message(chat_id, f"💳 شماره کارت: {get_db_setting('card_number')}\nصاحب کارت: {get_db_setting('card_holder')}")
    elif text == "💰 موجودی کیف پول":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT balance, total_bought FROM users WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        conn.close()
        bal = row[0] if row else 0
        bgt = row[1] if row else 0
        bot.send_message(chat_id, f"💰 **موجودی حساب شما در دیتابیس:**\n💵 اعتبار: {bal:,} تومان\n🛍 تعداد خرید: {bgt} عدد")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    if call.data == "adm_count":
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM users")
        u_count = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM configs_stock WHERE is_sold=0")
        s_count = c.fetchone()[0]
        conn.close()
        bot.send_message(chat_id, f"📊 آمار:\nکل کاربران: {u_count}\nکانفیگ آماده انبار: {s_count}")
        
    elif call.data in ["buy_from_stock_eco", "buy_from_stock_vip"]:
        conn = sqlite3.connect(DB_FILE)
        c = conn.cursor()
        c.execute("SELECT id, config_text FROM configs_stock WHERE is_sold=0 LIMIT 1")
        row = c.fetchone()
        if not row:
            bot.send_message(chat_id, "❌ متاسفانه انبار کانفیگ‌های دستی شما در حال حاضر خالی است.")
        else:
            c.execute("UPDATE configs_stock SET is_sold=1 WHERE id=?", (row[0],))
            conn.commit()
            bot.send_message(chat_id, f"🎉 کانفیگ اختصاصی شما از مخزن دستی مالک صادر شد:\n\n<code>{row[1]}</code>")
        conn.close()
    bot.answer_callback_query(call.id)

if __name__ == '__main__':
    init_db()
    print("Python Admin Bot with dynamic pricing is ready.")
    bot.infinity_polling()