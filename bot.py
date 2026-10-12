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
        bot.send_message(chat_id, "📺 اضغط على الزر أدناه لمشاهدة الإعلان:", reply_markup=markup)
        
    elif "رصيدي الحالي" in text:
        current_balance, _ = get_or_create_user(user.id, user.username, user.first_name)
        bot.send_message(chat_id, f"📊 رصيدك الحالي هو: **{current_balance} نقطة**", parse_mode="Markdown")
        
    elif "دعوة أصدقاء" in text:
        referral_link = f"https://t.me/{BOT_USERNAME}?start=ref_{chat_id}"
        invite_msg = (
            f"👥 **نظام دعوة الأصدقاء:**\n\n"
            f"شاركه مع أصدقائك واكسب نقاط إضافية لكل شخص ينضم عبر رابطك!\n\n"
            f"🔗 رابط الإحالة الخاص بك:\n`{referral_link}`"
        )
        bot.send_message(chat_id, invite_msg, parse_mode="Markdown")

# استقبال الرابط واقتطاع النقاط من المستخدم عند إنشاء ترويج
@bot.message_handler(func=lambda message: message.text and "instagram.com" in message.text)
def handle_user_instagram_link(message):
    chat_id = message.chat.id
    user = message.from_user
    user_link = message.text.strip()
    
    if not extract_shortcode_from_url(user_link):
        bot.reply_to(message, "⚠️ الرابط غير صالح. يرجى إرسال رابط صحيح من إنستجرام.")
        return
        
    # التحقق من رصيد المستخدم قبل الخصم
    current_balance, _ = get_or_create_user(chat_id, user.username, user.first_name)
    
    if current_balance < PROMOTION_COST:
        bot.reply_to(
            message,
            f"❌ **عذراً، رصيدك غير كافٍ لإنشاء ترويج!**\n\n"
            f"💰 رصيدك الحالي: `{current_balance} نقطة`\n"
            f"🏷️ التكلفة المطلوبة: `{PROMOTION_COST} نقاط`\n\n"
            f"قم بجمع النقاط عبر تنفيذ المهام أو دعوة الأصدقاء أو الهدية اليومية.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        return
        
    # اقتطاع النقاط وإضافة الرابط للمهام
    update_user_balance(chat_id, -PROMOTION_COST)
    active_tasks.append(user_link)
    
    updated_balance, _ = get_or_create_user(chat_id, user.username, user.first_name)
    
    bot.reply_to(
        message, 
        f"✅ **تم خصم ({PROMOTION_COST} نقاط) بنجاح وإضافة رابطك لقائمة المهام!**\n\n"
        f"🔗 الرابط: {user_link}\n"
        f"📊 رصيدك المتبقي: **{updated_balance} نقطة**", 
        parse_mode="Markdown",
        reply_markup=get_main_menu()
    )

# الخطوة 1: عندما يضغط المستخدم على المهمة
@bot.callback_query_handler(func=lambda call: call.data.startswith('do_task_'))
def handle_task_selection(call):
    task_idx = int(call.data.split('_')[2])
    chat_id = call.message.chat.id
    
    if task_idx < len(active_tasks):
        task_url = active_tasks[task_idx]
        
        if has_user_completed_task(chat_id, task_url):
            bot.answer_callback_query(call.id, "⚠️ لقد قمت بتنفيذ هذه المهمة مسبقاً ولا يمكنك إعادتها.", show_alert=True)
            return
            
        user_pending_tasks[chat_id] = {'task_url': task_url, 'step': 'waiting_ig_username'}
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔗 اضغط هنا لفتح المنشور/الحساب والتفاعل", url=task_url))
        
        bot.send_message(
            chat_id,
            f"🎯 **خطوات تنفيذ المهمة:**\n"
            f"1. اضغط على الزر أدناه لفتح الرابط وقم بالمتابعة أو الإعجاب.\n"
            f"2. **أرسل يوزر حسابك على إنستجرام (مثل: @username أو username) هنا في الشات أولاً:**",
            reply_markup=markup,
            parse_mode="Markdown"
        )
    else:
        bot.answer_callback_query(call.id, "عذراً، هذه المهمة لم تعد متاحة.")

# الخطوة 2: استقبال يوزر إنستجرام من المستخدم
@bot.message_handler(func=lambda message: message.chat.id in user_pending_tasks and user_pending_tasks[message.chat.id].get('step') == 'waiting_ig_username')
def handle_user_ig_username(message):
    chat_id = message.chat.id
    ig_username = message.text.strip()
    
    user_pending_tasks[chat_id]['ig_username'] = ig_username
    user_pending_tasks[chat_id]['step'] = 'waiting_proof_photo'
    
    bot.reply_to(
        message,
        f"✅ تم حفظ يوزر إنستجرام (`{ig_username}`).\n"
        f"📸 **الآن أرسل صورة الشاشة (سكرين شوت) كإثبات للتفاعل:**",
        parse_mode="Markdown"
    )

# الخطوة 3: استقبال صورة الإثبات وإرسالها للإدارة
@bot.message_handler(content_types=['photo'])
def handle_user_proof_photo(message):
    chat_id = message.chat.id
    user = message.from_user
    
    if chat_id not in user_pending_tasks or user_pending_tasks[chat_id].get('step') != 'waiting_proof_photo':
        bot.reply_to(message, "⚠️ يرجى اختيار مهمة من قسم 'تنفيذ مهام' أولاً واتباع الخطوات.")
        return
        
    task_data = user_pending_tasks[chat_id]
    task_url = task_data['task_url']
    ig_username = task_data['ig_username']
    photo_file_id = message.photo[-1].file_id
    
    bot.reply_to(message, "⏳ تم إرسال صورة الإثبات ومعلوماتك إلى الإدارة بنجاح. سيتم مراجعتها قريباً.")
    
    markup = types.InlineKeyboardMarkup()
    btn_accept = types.InlineKeyboardButton("✅ قبول وإعطاء المكافأة", callback_data=f"accept_{chat_id}")
    btn_reject = types.InlineKeyboardButton("❌ رفض مع ذكر السبب", callback_data=f"reject_{chat_id}")
    markup.add(btn_accept, btn_reject)
    
    username_display = f"@{user.username}" if user.username else "بدون معرف"
    admin_caption = (
        f"🚨 **إثبات مهمة جديد للمراجعة!**\n\n"
        f"👤 اسم المستخدم: {user.first_name}\n"
        f"🔗 يوزر تليجرام: {username_display}\n"
        f"📱 يوزر إنستجرام: `{ig_username}`\n"
        f"🆔 الآي دي: `{chat_id}`\n"
        f"🔗 رابط المهمة: {task_url}"
    )
    
    try:
        bot.send_photo(OWNER_CHAT_ID, photo_file_id, caption=admin_caption, reply_markup=markup, parse_mode="Markdown")
    except Exception as e:
        print(f"Error sending to admin: {e}")
        
    del user_pending_tasks[chat_id]

# معالجة تفاعل المدير (القبول أو طلب سبب الرفض)
@bot.callback_query_handler(func=lambda call: call.data.startswith('accept_') or call.data.startswith('reject_'))
def handle_admin_decision(call):
    action, target_user_id = call.data.split('_')
    target_user_id = int(target_user_id)
    admin_id = call.message.chat.id
    
    caption = call.message.caption or ""
    task_url_match = re.search(r'🔗 رابط المهمة: (https://[^\s]+)', caption)
    task_url = task_url_match.group(1) if task_url_match else None
    
    if action == 'accept':
        reward_amount = 10.0
        update_user_balance(target_user_id, reward_amount)
        
        if task_url:
            mark_task_as_completed(target_user_id, task_url)
        
        bot.edit_message_caption(
            caption=caption + f"\n\n✅ **الحالة:** تم القبول وإضافة ({reward_amount} نقطة) للمستخدم بنجاح.",
            chat_id=admin_id,
            message_id=call.message.message_id,
            parse_mode="Markdown"
        )
        
        try:
            bot.send_message(
                target_user_id,
                f"🎉 **مبروك! تم قبول إثبات تفاعلك ومتابعتك من قِبل الإدارة.**\nتمت إضافة `{reward_amount} نقطة` إلى رصيدك.",
                parse_mode="Markdown",
                reply_markup=get_main_menu()
            )
        except Exception as e:
            print(f"Could not notify user: {e}")
            
    elif action == 'reject':
        admin_waiting_rejection[admin_id] = {
            'target_user_id': target_user_id,
            'message_id': call.message.message_id,
            'caption': caption
        }
        bot.answer_callback_query(call.id, "أرسل الآن رسالة في الشات تحتوي على (سبب الرفض) ليتم إرسالها للمستخدم.")
        bot.send_message(admin_id, "✍️ **اكتب سبب رفض الإثبات الآن في الشات:**", parse_mode="Markdown")

# استقبال سبب الرفض المكتوب من المدير وإرساله للمستخدم
@bot.message_handler(func=lambda message: message.chat.id == OWNER_CHAT_ID and message.chat.id in admin_waiting_rejection)
def handle_admin_rejection_reason(message):
    admin_id = message.chat.id
    rejection_reason = message.text.strip()
    
    data = admin_waiting_rejection[admin_id]
    target_user_id = data['target_user_id']
    message_id = data['message_id']
    caption = data['caption']
    
    try:
        bot.edit_message_caption(
            caption=caption + f"\n\n❌ **الحالة:** تم الرفض.\n💬 **السبب:** {rejection_reason}",
            chat_id=admin_id,
            message_id=message_id,
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Error editing admin caption: {e}")
        
    try:
        bot.send_message(
            target_user_id,
            f"❌ **عذراً، تم رفض إثبات التفاعل الخاص بك من قبل الإدارة.**\n\n"
            f"💬 **السبب:** {rejection_reason}\n\n"
            f"يرجى تصحيح الخطأ وإعادة المحاولة.",
            parse_mode="Markdown",
            reply_markup=get_main_menu()
        )
        bot.send_message(admin_id, "✅ تم إرسال سبب الرفض للمستخدم بنجاح.")
    except Exception as e:
        print(f"Could not notify user: {e}")
        
    del admin_waiting_rejection[admin_id]

if __name__ == "__main__":
    print("Bot is running with Promotion Cost Deduction configured...")
    bot.infinity_polling()
