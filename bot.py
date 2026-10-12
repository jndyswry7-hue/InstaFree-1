import re
import sqlite3
from datetime import datetime, timedelta
import telebot
from telebot import types

# توكن البوت الخاص بك
TELEGRAM_BOT_TOKEN = '8728570816:AAEX9tKnfb3qmNsVcyPgUD5c8X40Aa1urHA'
bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# 🔴 معرف الـ Chat ID الخاص بك للإدارة وتلقي الإثباتات
OWNER_CHAT_ID = 2115819869

# تكلفة إنشاء ترويج جديد (مقدار النقاط التي سيتم اقتطاعها)
PROMOTION_COST = 10.0

# جلب يوزر البوت تلقائياً ليكون رابط الإحالة فعالاً
try:
    BOT_USERNAME = bot.get_me().username
except Exception:
    BOT_USERNAME = "YourBot"

active_tasks = []          # قائمة روابط المهام المتاحة للترويج
user_pending_tasks = {}    # لتتبع الخطوة الحالية للمستخدم
admin_waiting_rejection = {} # لتتبع المدير عند كتابة سبب الرفض

# إعداد قاعدة البيانات وتحديث الجداول تلقائياً
def init_db():
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    
    # جدول المستخدمين
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            balance REAL DEFAULT 20.0,
            last_daily_gift TEXT
        )
    ''')
    
    # جدول المهام المكتملة لمنع تكرارها
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS completed_tasks (
            user_id INTEGER,
            task_url TEXT,
            PRIMARY KEY (user_id, task_url)
        )
    ''')
    
    cursor.execute("PRAGMA table_info(users)")
    columns = [column[1] for column in cursor.fetchall()]
    if 'invited_by' not in columns:
        cursor.execute('ALTER TABLE users ADD COLUMN invited_by INTEGER')
        
    conn.commit()
    conn.close()

init_db()

def get_or_create_user(user_id, username, first_name, referrer_id=None):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance, last_daily_gift FROM users WHERE user_id = ?', (user_id,))
    user = cursor.fetchone()
    
    if not user:
        cursor.execute('''
            INSERT INTO users (user_id, username, first_name, balance, last_daily_gift, invited_by)
            VALUES (?, ?, ?, 20.0, NULL, ?)
        ''', (user_id, username, first_name, referrer_id))
        conn.commit()
        
        # مكافأة الإحالة للشخص الداعي
        if referrer_id and referrer_id != user_id:
            cursor.execute('SELECT balance FROM users WHERE user_id = ?', (referrer_id,))
            ref_user = cursor.fetchone()
            if ref_user:
                new_ref_balance = ref_user[0] + 5.0
                cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_ref_balance, referrer_id))
                conn.commit()
                try:
                    bot.send_message(referrer_id, "🎁 انضم مستخدم جديد عبر رابط الإحالة الخاص بك! تمت إضافة `5 نقاط` لرصيدك.", parse_mode="Markdown")
                except:
                    pass
                    
        balance = 20.0
        last_gift = None
    else:
        balance, last_gift = user
        
    conn.close()
    return balance, last_gift

def update_user_balance(user_id, amount):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT balance FROM users WHERE user_id = ?', (user_id,))
    res = cursor.fetchone()
    if res:
        new_balance = res[0] + amount
        cursor.execute('UPDATE users SET balance = ? WHERE user_id = ?', (new_balance, user_id))
        conn.commit()
    conn.close()

def update_last_gift_time(user_id):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cursor.execute('UPDATE users SET last_daily_gift = ? WHERE user_id = ?', (now, user_id))
    conn.commit()
    conn.close()

def has_user_completed_task(user_id, task_url):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('SELECT 1 FROM completed_tasks WHERE user_id = ? AND task_url = ?', (user_id, task_url))
    res = cursor.fetchone()
    conn.close()
    return res is not None

def mark_task_as_completed(user_id, task_url):
    conn = sqlite3.connect('bot_database.db')
    cursor = conn.cursor()
    cursor.execute('INSERT OR IGNORE INTO completed_tasks (user_id, task_url) VALUES (?, ?)', (user_id, task_url))
    conn.commit()
    conn.close()

def extract_shortcode_from_url(url):
    match = re.search(r'/(?:p|reel|reels)/([^/?]+)', url)
    if match:
        return match.group(1)
    return None

# لوحة المفاتيح الرئيسية
def get_main_menu():
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn1 = types.KeyboardButton("👁️ تنفيذ مهام وكسب نقاط")
    btn2 = types.KeyboardButton("🚀 إنشاء ترويج مجاني")
    btn3 = types.KeyboardButton("🎁 الهدية اليومية")
    btn4 = types.KeyboardButton("📺 شاهد الإعلان واكسب نقاط")
    btn5 = types.KeyboardButton("💳 رصيدي الحالي")
    btn6 = types.KeyboardButton("👥 دعوة أصدقاء")
    markup.add(btn1, btn2, btn3, btn4, btn5, btn6)
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    user = message.from_user
    args = message.text.split()
    
    referrer_id = None
    if len(args) > 1 and args[1].startswith('ref_'):
        try:
            referrer_id = int(args[1].split('_')[1])
        except ValueError:
            pass
            
    balance, _ = get_or_create_user(user.id, user.username, user.first_name, referrer_id)
    
    welcome_text = (
        f"أهلاً بك يا *{user.first_name}* في منصة الترويج لإنستجرام! 🌟🔥\n\n"
        f"📊 **رصيدك الحالي:** `{balance} نقطة`\n\n"
        "أرسل رابط إنستجرام مباشرة لإضافته كمهام (تكلفة الترويج: 10 نقاط)، أو اختر من القائمة أدناه:"
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_menu(), parse_mode="Markdown")

@bot.message_handler(func=lambda message: message.text in [
    "👁️ تنفيذ مهام وكسب نقاط", 
    "🚀 إنشاء ترويج مجاني", 
    "🎁 الهدية اليومية", 
    "📺 شاهد الإعلان واكسب نقاط", 
    "💳 رصيدي الحالي", 
    "👥 دعوة أصدقاء"
])
def handle_buttons(message):
    text = message.text
    chat_id = message.chat.id
    user = message.from_user
    balance, last_gift = get_or_create_user(user.id, user.username, user.first_name)
    
    if "تنفيذ مهام" in text:
        if not active_tasks:
            bot.send_message(chat_id, "📭 لا توجد مهام متاحة حالياً. أرسل رابطاً جديداً للترويج لتظهر المهام للمستخدمين!")
        else:
            markup = types.InlineKeyboardMarkup()
            for idx, task_url in enumerate(active_tasks):
                if not has_user_completed_task(chat_id, task_url):
                    markup.add(types.InlineKeyboardButton(f"🔗 تنفيذ المهمة #{idx+1}", callback_data=f"do_task_{idx}"))
            
            if not markup.keyboard:
                bot.send_message(chat_id, "✅ لقد قمتم بتنفيذ جميع المهام المتاحة حالياً! عُودوا لاحقاً للمزيد.")
            else:
                bot.send_message(chat_id, "📋 **المهام المتاحة لك (يمكنك تنفيذ كل مهمة مرة واحدة فقط):**", reply_markup=markup, parse_mode="Markdown")
            
    elif "إنشاء ترويج" in text:
        bot.send_message(chat_id, f"🚀 **لإنشاء ترويج جديد:**\nتكلفة إنشاء ترويج هي **{PROMOTION_COST} نقاط**.\nأرسل رابط المنشور أو الريلز (Instagram Link) هنا في المحادثة ليتم خصم النقاط ونشر المهمة تلقائياً!")
        
    elif "الهدية اليومية" in text:
        now = datetime.now()
        can_take_gift = True
        
        if last_gift:
            last_gift_time = datetime.strptime(last_gift, '%Y-%m-%d %H:%M:%S')
            time_diff = now - last_gift_time
            if time_diff < timedelta(hours=24):
                can_take_gift = False
                remaining_time = timedelta(hours=24) - time_diff
                hours, remainder = divmod(int(remaining_time.total_seconds()), 3600)
                minutes, _ = divmod(remainder, 60)
                bot.send_message(chat_id, f"⏳ لقد استلمت هديتك اليومية مسبقاً!\nيمكنك استلامها بعد: **{hours} ساعة و {minutes} دقيقة**.", parse_mode="Markdown")
                
        if can_take_gift:
            gift_amount = 5.0
            update_user_balance(user.id, gift_amount)
            update_last_gift_time(user.id)
            new_balance, _ = get_or_create_user(user.id, user.username, user.first_name)
            bot.send_message(chat_id, f"🎁 مبروك! حصلت على الهدية اليومية (`+{gift_amount} نقطة`).\n📊 رصيدك الجديد: **{new_balance} نقطة**", parse_mode="Markdown", reply_markup=get_main_menu())
            
    elif "شاهد الإعلان" in text:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔗 اضغط هنا لمشاهدة الإعلان", url="https://uplcm.com/4/11967886"))
        bot.send_message(chat
    
