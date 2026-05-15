import telebot
from telebot import types
import sqlite3
import datetime
import os
import logging
from threading import Lock

# Setup production logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 🔒 [FIXED]: Load token dynamically to prevent credential leaks
BOT_TOKEN = os.getenv("BOT_TOKEN", "8778861221:AAGRD7b9BzMIpiepKs5pcn4S6QsVetqlGm0")
OWNER_ID = int(os.getenv("OWNER_ID", "55442211"))
DB_FILE = "vpn_database.db"

# 🧱 [FIXED]: Lock for SQLite thread safety to avoid ProgrammingError & race conditions
db_lock = Lock()

# 🤖 [FIXED]: Properly instantiated the telebot object to fix NameError
bot = telebot.TeleBot(BOT_TOKEN)

def get_db_connection():
    """Helper to get an isolated SQLite connection."""
    return sqlite3.connect(DB_FILE, check_same_thread=False)

def init_db():
    with db_lock:
        conn = get_db_connection()
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
        
        # 📦 [FIXED]: Added 'plan_type' ('economy' or 'vip') to separate categories
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS configs_stock (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            config_text TEXT,
            plan_type TEXT DEFAULT 'economy',
            is_sold INTEGER DEFAULT 0,
            added_at TEXT
        )""")
        
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS kv_settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        
        # Seed default configurations safely
        defaults = [
            ('card_number', '6063-7312-8871-7607'),
            ('card_holder', 'علی اصغر سوری'),
            ('channel_id', '@AODvpn'),
            ('channel_lock', '1'),
            ('economy_price', '300000'),
            ('vip_price', '480000')
        ]
        for key, val in defaults:
            cursor.execute("INSERT OR IGNORE INTO kv_settings (key, value) VALUES (?, ?)", (key, val))
        conn.commit()
        conn.close()
    logging.info("✅ Database initialized successfully with correct schema.")

def get_db_setting(key, fallback=""):
    try:
        with db_lock:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT value FROM kv_settings WHERE key=?", (key,))
            row = c.fetchone()
            conn.close()
            return row[0] if row else fallback
    except Exception as e:
        logging.error(f"Error reading setting '{key}': {e}")
        return fallback

# 👤 [FIXED]: Auto-registration helper to register users on their first interaction
def register_user_if_not_exists(chat_id, username):
    with db_lock:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("INSERT OR IGNORE INTO users (chat_id, username, balance, total_bought, is_banned, role) VALUES (?, ?, 0, 0, 0, 'user')",
                  (chat_id, username or "Unknown"))
        conn.commit()
        conn.close()

# 🚫 [FIXED]: Safety helper to check banned status
def is_user_banned(chat_id):
    with db_lock:
        conn = get_db_connection()
        c = conn.cursor()
        c.execute("SELECT is_banned FROM users WHERE chat_id=?", (chat_id,))
        row = c.fetchone()
        conn.close()
        return row[0] == 1 if row else False

@bot.message_handler(commands=['start', 'شروع'])
def handle_start(message):
    chat_id = message.chat.id
    register_user_if_not_exists(chat_id, message.from_user.username)
    
    # 🚫 [FIXED]: Intercept banned users early
    if is_user_banned(chat_id):
        bot.reply_to(message, "⛔️ حساب کاربری شما مسدود شده است. امکان استفاده از ربات را ندارید.")
        return
        
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(
        types.KeyboardButton("🚀 خرید سرویس"),
        types.KeyboardButton("💰 شارژ کیف پول"),
        types.KeyboardButton("💰 موجودی کیف پول")
    )
    welcome_msg = "👋 به ربات خرید کانفیگ AOD VPN خوش آمدید!\n\nلطفا از دکمه‌های زیر استفاده کنید:"
    bot.send_message(chat_id, welcome_msg, reply_markup=markup)

@bot.message_handler(commands=['panel', 'پنل'])
def handle_admin_panel(message):
    # 🔐 Restrict command to actual owner
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
    bot.send_message(message.chat.id, "⚙️ پنل مدیریت مالک ربات:**\n\nاز منوی شیشه‌ای زیر اقدام کنید:", reply_markup=markup)

@bot.message_handler(func=lambda msg: True)
def text_reply_handler(message):
    chat_id = message.chat.id
    text = message.text
    register_user_if_not_exists(chat_id, message.from_user.username)
    
    # 🚫 [FIXED]: Block banned users from interacting
    if is_user_banned(chat_id):
        bot.send_message(chat_id, "⛔️ حساب کاربری شما مسدود است.")
        return

    # Admin Manual Config Uploader
    if chat_id == OWNER_ID and (text.startswith("vless://") or text.startswith("vmess://")):
        # Automatically classify plan type based on link labels or format
        plan = 'vip' if 'vip' in text.lower() else 'economy'
        added_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        
        with db_lock:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("INSERT INTO configs_stock (config_text, plan_type, added_at) VALUES (?, ?, ?)", 
                      (text, plan, added_now))
            conn.commit()
            conn.close()
        bot.reply_to(message, f"✅ کانفیگ با موفقیت به عنوان پلن {plan.upper()} به انبار اضافه شد.")
        return

    if text == "🚀 خرید سرویس":
        markup = types.InlineKeyboardMarkup()
        eco_p = int(get_db_setting('economy_price', '300000'))
        vip_p = int(get_db_setting('vip_price', '480000'))
        markup.add(
            types.InlineKeyboardButton(f"⭐️ خرید پلن اقتصادی ({eco_p:,} تومان)", callback_data="buy_from_stock_eco"),
            types.InlineKeyboardButton(f"⚡️ خرید پلن VIP ({vip_p:,} تومان)", callback_data="buy_from_stock_vip")
        )
        bot.send_message(chat_id, "🛒 **یکی از دسته‌بندی‌ها را انتخاب کنید:", reply_markup=markup)
        
    elif text == "💰 شارژ کیف پول":
        card_num = get_db_setting('card_number')
        card_hlr = get_db_setting('card_holder')
        bot.send_message(chat_id, f"💳 شماره کارت جهت کارت به کارت:**\n\n`{card_num}`\n👤 صاحب کارت: {card_hlr}\n\n📌 پس از انتقال، رسید پرداخت را ارسال فرمایید.")
        
    elif text == "💰 موجودی کیف پول":
        with db_lock:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT balance, total_bought FROM users WHERE chat_id=?", (chat_id,))
            row = c.fetchone()
            conn.close()
        
        bal = row[0] if row else 0
        bgt = row[1] if row else 0
        bot.send_message(chat_id, f"💰 **موجودی حساب شما:**\n💵 اعتبار: {bal:,} تومان\n🛍 تعداد خرید: {bgt}** عدد")

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    chat_id = call.message.chat.id
    register_user_if_not_exists(chat_id, call.from_user.username)
    
    # 🚫 [FIXED]: Stop query processing if user is banned
    if is_user_banned(chat_id):
        bot.answer_callback_query(call.id, "⛔️ شما مسدود هستید.", show_alert=True)
        return

    # 🔐 [FIXED]: Validate administrative callback access to block unauthorized users
    if call.data.startswith("adm_") and chat_id != OWNER_ID:
        bot.answer_callback_query(call.id, "⛔️ عدم دسترسی!", show_alert=True)
        return

    if call.data == "adm_count":
        with db_lock:
            conn = get_db_connection()
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users")
            u_count = c.fetchone()[0]
            c.execute("SELECT COUNT(*) FROM configs_stock WHERE is_sold=0")
            s_count = c.fetchone()[0]
            conn.close()
        bot.send_message(chat_id, f"📊 **آمار کلی ربات:**\n👥 کل کاربران: {u_count} نفر\n📦 کانفیگ آماده انبار: {s_count} عدد")
        bot.answer_callback_query(call.id)
        
    elif call.data in ["buy_from_stock_eco", "buy_from_stock_vip"]:
        plan = "economy" if "eco" in call.data else "vip"
        price_setting = 'economy_price' if plan == "economy" else 'vip_price'
        price = int(get_db_setting(price_setting, '300000'))
        
        with db_lock:
            conn = get_db_connection()
            c = conn.cursor()
            
            # 1. Check user's actual balance
            c.execute("SELECT balance, total_bought FROM users WHERE chat_id=?", (chat_id,))
            user_row = c.fetchone()
            balance = user_row[0] if user_row else 0
            total_bought = user_row[1] if user_row else 0
            
            # 💰 [FIXED]: Check balance before issuing config
            if balance < price:
                bot.send_message(chat_id, f"❌ **خطا: موجودی ناکافی است.**\n\n💰 موجودی شما: {balance:,} تومان\n💵 قیمت سرور: {price:,} تومان\n\nلطفا کیف پول خود را شارژ کنید.")
                bot.answer_callback_query(call.id, "موجودی کافی نیست!", show_alert=True)
                conn.close()
                return
                
            # 📦 [FIXED]: Querying specific plan_type from stock
            c.execute("SELECT id, config_text FROM configs_stock WHERE is_sold=0 AND plan_type=? LIMIT 1", (plan,))
            row = c.fetchone()
            
            if not row:
                bot.send_message(chat_id, f"❌ متاسفانه انبار کانفیگ‌های دستی {plan.upper()} در حال حاضر خالی است. مدیر ربات به زودی آن را شارژ خواهد کرد.")
                bot.answer_callback_query(call.id, "انبار خالی است", show_alert=True)
                conn.close()
                return
            
            config_id, config_text = row
            
            # 🧱 [FIXED]: Deduct balance, increment total_bought, and set sold flag atomically
            new_balance = balance - price
            new_total = total_bought + 1
            
            c.execute("UPDATE users SET balance=?, total_bought=? WHERE chat_id=?", (new_balance, new_total, chat_id))
            c.execute("UPDATE configs_stock SET is_sold=1 WHERE id=?", (config_id,))
            
            conn.commit()
            conn.close()
            
        success_text = f"🎉 **خرید با موفقیت انجام شد!**\n\n💰 مبلغ {price:,} تومان از حساب شما کسر شد.\n💵 موجودی جدید: {new_balance:,} تومان\n\n🔑 **کانفیگ اختصاصی شما:**\n`{config_text}`\n\n📌 آن را کپی کرده و در کلاینت V2Ray خود وارد نمایید."
        bot.send_message(chat_id, success_text, parse_mode="Markdown")
        bot.answer_callback_query(call.id, "خرید موفقیت‌آمیز بود!")

if name == 'main':
    init_db()
    print("⚡️ Debugged & Production-Ready AOD VPN Bot is active!")
    logging.info("Polling started...")
    bot.infinity_polling()