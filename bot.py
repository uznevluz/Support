import os
import time
import json
import csv
import io
import logging
import asyncio

import aiohttp
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile, ErrorEvent
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

# ======================= SOZLAMALAR =======================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "5383321037").split(",") if x.strip()]
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "bot.db")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

CATEGORIES = {
    "taklif": "💡 Taklif",
    "murojaat": "❓ Murojaat",
    "reklama": "📢 Reklama",
}

OFFICIAL_CHANNELS = [
    ("Anifilm.uz kanali", "https://t.me/anifilm_uz"),
]

FLOOD_LIMIT_MESSAGES = 5
FLOOD_LIMIT_SECONDS = 60
DUPLICATE_WINDOW_SECONDS = 30

FAQ_ANSWERS = {
    "ish vaqt": "🕐 Biz har kuni 09:00 dan 18:00 gacha ishlaymiz. Ushbu vaqtdan tashqarida yozgan xabarlaringizga ish vaqti boshlanishi bilan javob beramiz.",
    "qachon javob": "⏳ Odatda xabarlarga bir necha soat ichida javob beramiz. Iltimos, biroz kuting.",
    "reklama narx": "📢 Reklama narxlari va shartlari haqida to'liq ma'lumot uchun 'Reklama' bo'limi orqali murojaat qiling, admin siz bilan bog'lanadi.",
    "kanal manzil": "📢 Rasmiy kanallarimiz ro'yxatini /start menyusidagi '📢 Rasmiy kanallarimiz' tugmasidan ko'rishingiz mumkin.",
}

BANNED_WORDS = []

DEFAULT_WORKING_HOURS_ENABLED = True
DEFAULT_WORKING_HOURS_START = "09:00"
DEFAULT_WORKING_HOURS_END = "18:00"

# ======================= TILLAR =======================

LANG_LABELS = {
    "uz": "🇺🇿 O'zbek tili",
    "ru": "🇷🇺 Русский язык",
    "en": "🇬🇧 English",
}

TEXTS = {
    "welcome": {
        "uz": (
            "📢 <b>Taklif, Murojaat va Reklama</b>\n\n"
            "Assalomu alaykum!\n\n"
            "Anifilm.uz jamoasi sizning har bir fikr va taklifingizni qadrlaydi.\n\n"
            "💡 Takliflaringiz orqali saytimizni yanada rivojlantirishga yordam bera olasiz.\n"
            "❓ Savol yoki murojaatlaringiz bo'lsa, administrator bilan bog'laning.\n"
            "📢 Reklama, hamkorlik yoki biznes takliflari bo'yicha ham murojaat qilishingiz mumkin.\n\n"
            "📝 Quyidagi bo'limlardan birini tanlang."
        ),
        "ru": (
            "📢 <b>Предложение, Обращение и Реклама</b>\n\n"
            "Ассалому алайкум!\n\n"
            "Команда Anifilm.uz ценит каждое ваше мнение и предложение.\n\n"
            "💡 Через свои предложения вы можете помочь развитию нашего сайта.\n"
            "❓ Если у вас есть вопросы или обращения, свяжитесь с администратором.\n"
            "📢 Вы также можете обратиться по вопросам рекламы и сотрудничества.\n\n"
            "📝 Выберите один из разделов ниже."
        ),
        "en": (
            "📢 <b>Suggestions, Inquiries and Advertising</b>\n\n"
            "Hello!\n\n"
            "The Anifilm.uz team values every opinion and suggestion you share.\n\n"
            "💡 Your suggestions help us improve our site.\n"
            "❓ If you have questions or inquiries, contact the administrator.\n"
            "📢 You can also reach out regarding advertising or partnership offers.\n\n"
            "📝 Please choose one of the sections below."
        ),
    },
    "prompt_taklif": {
        "uz": "💡 Taklifingizni yozib qoldiring (matn, rasm yoki video yuborishingiz mumkin).",
        "ru": "💡 Напишите ваше предложение (можно отправить текст, фото или видео).",
        "en": "💡 Write your suggestion (you can send text, photo, or video).",
    },
    "prompt_murojaat": {
        "uz": "❓ Murojaatingizni yozib qoldiring (matn, rasm yoki video yuborishingiz mumkin).",
        "ru": "❓ Напишите ваше обращение (можно отправить текст, фото или видео).",
        "en": "❓ Write your inquiry (you can send text, photo, or video).",
    },
    "prompt_reklama": {
        "uz": "📢 Reklama/hamkorlik taklifingizni yozib qoldiring (matn, rasm yoki video yuborishingiz mumkin).",
        "ru": "📢 Напишите предложение по рекламе/сотрудничеству (можно отправить текст, фото или видео).",
        "en": "📢 Write your advertising/partnership offer (you can send text, photo, or video).",
    },
    "btn_taklif": {"uz": "💡 Taklif", "ru": "💡 Предложение", "en": "💡 Suggestion"},
    "btn_murojaat": {"uz": "❓ Murojaat", "ru": "❓ Обращение", "en": "❓ Inquiry"},
    "btn_reklama": {"uz": "📢 Reklama", "ru": "📢 Реклама", "en": "📢 Advertising"},
    "btn_channels": {
        "uz": "📢 Rasmiy kanallarimiz",
        "ru": "📢 Наши официальные каналы",
        "en": "📢 Our official channels",
    },
    "btn_my_tickets": {
        "uz": "📄 Mening murojaatlarim",
        "ru": "📄 Мои обращения",
        "en": "📄 My requests",
    },
    "btn_language": {"uz": "🌐 Til", "ru": "🌐 Язык", "en": "🌐 Language"},
    "blocked": {
        "uz": "🚫 Siz botdan foydalanish huquqidan mahrum qilingansiz.",
        "ru": "🚫 Вы лишены права пользоваться ботом.",
        "en": "🚫 You have been restricted from using this bot.",
    },
    "choose_category_first": {
        "uz": "Iltimos, avval bo'lim tanlang:",
        "ru": "Пожалуйста, сначала выберите раздел:",
        "en": "Please choose a section first:",
    },
    "confirm_received": {
        "uz": "✅ Xabaringiz qabul qilindi, tez orada javob beramiz.",
        "ru": "✅ Ваше сообщение принято, скоро ответим.",
        "en": "✅ Your message has been received, we'll reply soon.",
    },
    "after_hours_add": {
        "uz": "\n\n🕐 Hozir ish vaqtidan tashqari, shuning uchun javob berish biroz kechikishi mumkin.",
        "ru": "\n\n🕐 Сейчас нерабочее время, поэтому ответ может немного задержаться.",
        "en": "\n\n🕐 It's currently outside working hours, so the reply may be a bit delayed.",
    },
    "flood_msg": {
        "uz": "⏳ Siz juda tez-tez xabar yuboryapsiz. Iltimos, biroz kuting.",
        "ru": "⏳ Вы отправляете сообщения слишком часто. Пожалуйста, подождите.",
        "en": "⏳ You're sending messages too fast. Please wait a moment.",
    },
    "duplicate_msg": {
        "uz": "📵 Siz shu xabarni allaqachon yubordingiz. Iltimos, kuting, tez orada javob beramiz.",
        "ru": "📵 Вы уже отправили это сообщение. Пожалуйста, подождите, скоро ответим.",
        "en": "📵 You've already sent this message. Please wait, we'll respond soon.",
    },
    "banned_msg": {
        "uz": "⚠️ Xabaringizda taqiqlangan so'zlar aniqlandi. Iltimos, xabaringizni tahrirlab qayta yuboring.",
        "ru": "⚠️ В вашем сообщении обнаружены запрещённые слова. Пожалуйста, отредактируйте и отправьте снова.",
        "en": "⚠️ Your message contains restricted words. Please edit and resend.",
    },
    "my_tickets_header": {
        "uz": "📄 <b>Mening murojaatlarim:</b>\n",
        "ru": "📄 <b>Мои обращения:</b>\n",
        "en": "📄 <b>My requests:</b>\n",
    },
    "no_tickets": {
        "uz": "📄 Sizda hali murojaatlar yo'q.",
        "ru": "📄 У вас пока нет обращений.",
        "en": "📄 You don't have any requests yet.",
    },
    "channels_header": {
        "uz": "📢 <b>Rasmiy kanallarimiz:</b>\n\nQuyidagi tugmalar orqali kanallarimizga o'ting.",
        "ru": "📢 <b>Наши официальные каналы:</b>\n\nПерейдите по кнопкам ниже.",
        "en": "📢 <b>Our official channels:</b>\n\nUse the buttons below to visit.",
    },
    "rating_prompt": {
        "uz": "Javobdan mamnunmisiz? Bahoni tanlang:",
        "ru": "Довольны ли вы ответом? Выберите оценку:",
        "en": "Are you satisfied with the response? Choose a rating:",
    },
    "rating_thanks": {
        "uz": "Rahmat! Siz {score}/5 baho berdingiz. ⭐",
        "ru": "Спасибо! Вы поставили оценку {score}/5. ⭐",
        "en": "Thanks! You rated {score}/5. ⭐",
    },
    "reveal_opened": {
        "uz": "✅ Javob ochildi (yuqorida).",
        "ru": "✅ Ответ открыт (выше).",
        "en": "✅ Reply opened (above).",
    },
    "reply_notify": {
        "uz": "📩 Sizga javob keldi. Ko'rish uchun tugmani bosing.",
        "ru": "📩 Вам пришёл ответ. Нажмите кнопку, чтобы посмотреть.",
        "en": "📩 You've received a reply. Tap the button to view.",
    },
    "back_button": {"uz": "⬅️ Ortga", "ru": "⬅️ Назад", "en": "⬅️ Back"},
    "cancel_button": {"uz": "❌ Bekor qilish", "ru": "❌ Отмена", "en": "❌ Cancel"},
    "choose_language": {
        "uz": "🌐 Tilni tanlang:",
        "ru": "🌐 Выберите язык:",
        "en": "🌐 Choose your language:",
    },
    "language_set": {
        "uz": "✅ Til o'zgartirildi.",
        "ru": "✅ Язык изменён.",
        "en": "✅ Language updated.",
    },
    "ai_prefix": {
        "uz": "🤖 AI dastlabki javob:",
        "ru": "🤖 Предварительный ответ ИИ:",
        "en": "🤖 Preliminary AI reply:",
    },
}


def t(key, lang, **kwargs):
    bundle = TEXTS.get(key, {})
    text_val = bundle.get(lang) or bundle.get("uz", "")
    if kwargs:
        text_val = text_val.format(**kwargs)
    return text_val


# ======================= GEMINI AI =======================

async def call_gemini(prompt, system_instruction=None):
    if not GEMINI_API_KEY or not prompt:
        return None
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    if system_instruction:
        payload["systemInstruction"] = {"parts": [{"text": system_instruction}]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=20)
            ) as resp:
                data = await resp.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        return (parts[0].get("text") or "").strip() or None
    except Exception as e:
        logging.error(f"Gemini xatolik: {e}")
    return None


async def ai_summarize_ticket(ticket_id):
    history = await get_ticket_history(ticket_id)
    if not history:
        return None
    convo_lines = []
    for m in history:
        sender = "Foydalanuvchi" if m["sender"] == "user" else "Admin"
        content = m["text"] or f"[{m['content_type']}]"
        convo_lines.append(f"{sender}: {content}")
    convo_text = "\n".join(convo_lines)
    system_instruction = (
        "Siz admin uchun yordamchisiz. Quyidagi yozishmani 2-4 gapda o'zbek tilida "
        "qisqacha xulosalab ber: asosiy muammo nima, foydalanuvchi nima kutmoqda, "
        "va hozirgi holat qanday."
    )
    return await call_gemini(convo_text, system_instruction)


# ======================= MA'LUMOTLAR BAZASI =======================

async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT,
            is_blocked INTEGER DEFAULT 0,
            first_seen INTEGER,
            last_message_at INTEGER,
            window_start INTEGER DEFAULT 0,
            window_count INTEGER DEFAULT 0,
            last_text TEXT,
            last_text_time INTEGER DEFAULT 0
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS tickets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            category TEXT,
            status TEXT DEFAULT 'open',
            tag TEXT DEFAULT 'kutilmoqda',
            claimed_by INTEGER,
            pinned INTEGER DEFAULT 0,
            created_at INTEGER
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ticket_id INTEGER,
            sender TEXT,
            admin_id INTEGER,
            content_type TEXT,
            text TEXT,
            file_id TEXT,
            admin_chat_message_id INTEGER,
            is_read INTEGER DEFAULT 0,
            created_at INTEGER
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS admin_forward (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message_id INTEGER,
            ticket_id INTEGER,
            admin_id INTEGER,
            chat_message_id INTEGER
        )""")
        await db.commit()

        for alter_sql in [
            "ALTER TABLE messages ADD COLUMN rating INTEGER",
            "ALTER TABLE users ADD COLUMN language TEXT DEFAULT 'uz'",
            "ALTER TABLE tickets ADD COLUMN last_reminder_at INTEGER DEFAULT 0",
        ]:
            try:
                await db.execute(alter_sql)
                await db.commit()
            except Exception:
                pass

        defaults = {
            "working_hours_enabled": "1" if DEFAULT_WORKING_HOURS_ENABLED else "0",
            "working_hours_start": DEFAULT_WORKING_HOURS_START,
            "working_hours_end": DEFAULT_WORKING_HOURS_END,
            "flood_limit_messages": str(FLOOD_LIMIT_MESSAGES),
            "flood_limit_seconds": str(FLOOD_LIMIT_SECONDS),
            "duplicate_window_seconds": str(DUPLICATE_WINDOW_SECONDS),
            "reminder_minutes": "30",
            "auto_assign_enabled": "1",
            "admin_rotation_index": "0",
        }
        for k, v in defaults.items():
            await db.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v))
        await db.commit()


async def get_or_create_user(user_id, username, full_name):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            await db.execute(
                "INSERT INTO users (user_id, username, full_name, first_seen) VALUES (?,?,?,?)",
                (user_id, username, full_name, int(time.time()))
            )
        else:
            await db.execute(
                "UPDATE users SET username=?, full_name=? WHERE user_id=?",
                (username, full_name, user_id)
            )
        await db.commit()


async def get_user_language(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT language FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return (row[0] if row and row[0] else "uz")


async def set_user_language(user_id, lang):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET language=? WHERE user_id=?", (lang, user_id))
        await db.commit()


async def is_blocked(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT is_blocked FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return bool(row and row[0])


async def set_blocked(user_id, blocked):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_blocked=? WHERE user_id=?", (1 if blocked else 0, user_id))
        await db.commit()


async def get_blocked_users():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT user_id, username, full_name FROM users WHERE is_blocked=1")
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_all_active_user_ids():
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT user_id FROM users WHERE is_blocked=0")
        rows = await cur.fetchall()
        return [r[0] for r in rows]


async def get_flood_settings():
    limit_msgs = int(await get_setting("flood_limit_messages", str(FLOOD_LIMIT_MESSAGES)))
    limit_secs = int(await get_setting("flood_limit_seconds", str(FLOOD_LIMIT_SECONDS)))
    dup_window = int(await get_setting("duplicate_window_seconds", str(DUPLICATE_WINDOW_SECONDS)))
    return limit_msgs, limit_secs, dup_window


async def check_flood(user_id):
    limit_msgs, limit_secs, _ = await get_flood_settings()
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT window_start, window_count FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return True
        window_start, window_count = row
        if now - window_start > limit_secs:
            await db.execute("UPDATE users SET window_start=?, window_count=1 WHERE user_id=?", (now, user_id))
            await db.commit()
            return True
        if window_count >= limit_msgs:
            return False
        await db.execute("UPDATE users SET window_count=window_count+1 WHERE user_id=?", (user_id,))
        await db.commit()
        return True


async def check_duplicate(user_id, text):
    if not text:
        return False
    _, _, dup_window = await get_flood_settings()
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT last_text, last_text_time FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        is_dup = False
        if row and row[0] == text and (now - (row[1] or 0)) < dup_window:
            is_dup = True
        await db.execute("UPDATE users SET last_text=?, last_text_time=?, last_message_at=? WHERE user_id=?",
                          (text, now, now, user_id))
        await db.commit()
        return is_dup


async def get_open_ticket(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM tickets WHERE user_id=? AND status!='resolved' ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def create_ticket(user_id, category):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(
            "INSERT INTO tickets (user_id, category, status, tag, created_at) VALUES (?,?,?,?,?)",
            (user_id, category, "open", "kutilmoqda", int(time.time()))
        )
        await db.commit()
        return cur.lastrowid


async def get_ticket(ticket_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM tickets WHERE id=?", (ticket_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def claim_ticket(ticket_id, admin_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tickets SET claimed_by=? WHERE id=?", (admin_id, ticket_id))
        await db.commit()


async def get_next_admin():
    if not ADMIN_IDS:
        return None
    if len(ADMIN_IDS) == 1:
        return ADMIN_IDS[0]
    enabled = await get_setting("auto_assign_enabled", "1")
    if enabled != "1":
        return None
    idx = int(await get_setting("admin_rotation_index", "0"))
    admin_id = ADMIN_IDS[idx % len(ADMIN_IDS)]
    await set_setting("admin_rotation_index", str((idx + 1) % len(ADMIN_IDS)))
    return admin_id


async def set_tag(ticket_id, tag):
    status = "resolved" if tag == "hal qilindi" else "open"
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tickets SET tag=?, status=? WHERE id=?", (tag, status, ticket_id))
        await db.commit()


async def pin_ticket(ticket_id, pinned):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tickets SET pinned=? WHERE id=?", (1 if pinned else 0, ticket_id))
        await db.commit()


async def delete_ticket(ticket_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tickets WHERE id=?", (ticket_id,))
        await db.execute("DELETE FROM messages WHERE ticket_id=?", (ticket_id,))
        await db.commit()


async def list_tickets(category=None, unread_only=False, limit=15):
    query = """
        SELECT t.*, u.username, u.full_name,
        (SELECT COUNT(*) FROM messages m WHERE m.ticket_id=t.id AND m.sender='user' AND m.is_read=0) as unread
        FROM tickets t JOIN users u ON u.user_id = t.user_id
        WHERE 1=1
    """
    params = []
    if category:
        query += " AND t.category=?"
        params.append(category)
    query += " ORDER BY t.pinned DESC, t.id DESC LIMIT ?"
    params.append(limit)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(query, params)
        rows = await cur.fetchall()
        result = [dict(r) for r in rows]
        if unread_only:
            result = [r for r in result if r["unread"] > 0]
        return result


async def search_tickets(query_text, limit=15):
    like = f"%{query_text}%"
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT DISTINCT t.*, u.username, u.full_name
            FROM tickets t
            JOIN users u ON u.user_id = t.user_id
            LEFT JOIN messages m ON m.ticket_id = t.id
            WHERE u.username LIKE ? OR u.full_name LIKE ? OR m.text LIKE ?
            ORDER BY t.id DESC LIMIT ?
        """, (like, like, like, limit))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_user_tickets(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM tickets WHERE user_id=? ORDER BY id DESC", (user_id,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def add_message(ticket_id, sender, content_type, text=None, file_id=None,
                       admin_id=None, admin_chat_message_id=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("""
            INSERT INTO messages (ticket_id, sender, admin_id, content_type, text, file_id,
                                   admin_chat_message_id, created_at)
            VALUES (?,?,?,?,?,?,?,?)
        """, (ticket_id, sender, admin_id, content_type, text, file_id,
              admin_chat_message_id, int(time.time())))
        await db.commit()
        return cur.lastrowid


async def get_message(message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM messages WHERE id=?", (message_id,))
        row = await cur.fetchone()
        return dict(row) if row else None


async def add_admin_forward(message_id, ticket_id, admin_id, chat_message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO admin_forward (message_id, ticket_id, admin_id, chat_message_id) VALUES (?,?,?,?)",
            (message_id, ticket_id, admin_id, chat_message_id)
        )
        await db.commit()


async def get_ticket_by_admin_forward(admin_id, chat_message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(
            "SELECT * FROM admin_forward WHERE admin_id=? AND chat_message_id=?",
            (admin_id, chat_message_id)
        )
        row = await cur.fetchone()
        return dict(row) if row else None


async def mark_message_read(message_id):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE messages SET is_read=1 WHERE id=?", (message_id,))
        await db.commit()


async def set_rating(message_id, score):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE messages SET rating=? WHERE id=?", (score, message_id))
        await db.commit()


async def get_top_users(limit=5):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT u.user_id, u.username, u.full_name, COUNT(t.id) as cnt
            FROM tickets t JOIN users u ON u.user_id = t.user_id
            GROUP BY t.user_id ORDER BY cnt DESC LIMIT ?
        """, (limit,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_ticket_history(ticket_id):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("SELECT * FROM messages WHERE ticket_id=? ORDER BY id ASC", (ticket_id,))
        rows = await cur.fetchall()
        return [dict(r) for r in rows]


async def get_setting(key, default=None):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
        return row[0] if row else default


async def set_setting(key, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT INTO settings (key, value) VALUES (?,?) "
                          "ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
        await db.commit()


async def get_channels():
    raw = await get_setting("channels", None)
    if raw is None:
        default = OFFICIAL_CHANNELS
        await set_setting("channels", json.dumps(default, ensure_ascii=False))
        return default
    return json.loads(raw)


async def add_channel(name, link):
    channels = await get_channels()
    channels.append([name, link])
    await set_setting("channels", json.dumps(channels, ensure_ascii=False))


async def remove_channel(index):
    channels = await get_channels()
    if 0 <= index < len(channels):
        channels.pop(index)
        await set_setting("channels", json.dumps(channels, ensure_ascii=False))
        return True
    return False


async def get_templates():
    raw = await get_setting("templates", None)
    if raw is None:
        default = [
            {"id": "thanks", "label": "🙏 Rahmat", "text": "🙏 Rahmat, xabaringiz uchun!"},
            {"id": "review", "label": "🔍 Ko'rib chiqamiz", "text": "🔍 Ko'rib chiqmoqdamiz, tez orada to'liq javob beramiz."},
            {"id": "done", "label": "✅ Hal qilindi", "text": "✅ Muammo hal qilindi. Boshqa savol bo'lsa, yozishingiz mumkin."},
        ]
        await set_setting("templates", json.dumps(default, ensure_ascii=False))
        return default
    return json.loads(raw)


async def add_template(label, text_val):
    templates = await get_templates()
    new_id = f"tpl_{int(time.time())}_{len(templates)}"
    templates.append({"id": new_id, "label": label, "text": text_val})
    await set_setting("templates", json.dumps(templates, ensure_ascii=False))


async def remove_template(index):
    templates = await get_templates()
    if 0 <= index < len(templates):
        templates.pop(index)
        await set_setting("templates", json.dumps(templates, ensure_ascii=False))
        return True
    return False


async def get_stats():
    async with aiosqlite.connect(DB_PATH) as db:
        stats = {}
        cur = await db.execute("SELECT COUNT(*) FROM users")
        stats["users"] = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM tickets")
        stats["tickets_total"] = (await cur.fetchone())[0]
        for cat in CATEGORIES:
            cur = await db.execute("SELECT COUNT(*) FROM tickets WHERE category=?", (cat,))
            stats[f"cat_{cat}"] = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM tickets WHERE tag='hal qilindi'")
        stats["resolved"] = (await cur.fetchone())[0]
        cur = await db.execute("SELECT COUNT(*) FROM tickets WHERE tag='kutilmoqda'")
        stats["pending"] = (await cur.fetchone())[0]
        return stats


async def export_csv():
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute("""
            SELECT t.id as ticket_id, u.user_id, u.username, u.full_name, t.category, t.tag,
                   t.created_at, m.sender, m.text, m.created_at as msg_time
            FROM tickets t
            JOIN users u ON u.user_id = t.user_id
            LEFT JOIN messages m ON m.ticket_id = t.id
            ORDER BY t.id ASC, m.id ASC
        """)
        rows = await cur.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ticket_id", "user_id", "username", "full_name", "category", "tag",
                      "ticket_created_at", "sender", "text", "msg_time"])
    for r in rows:
        writer.writerow(list(r))
    return output.getvalue()


# ======================= TUGMALAR =======================

def main_menu_kb(lang="uz"):
    b = InlineKeyboardBuilder()
    b.button(text=t("btn_taklif", lang), callback_data="cat:taklif", style="success")
    b.button(text=t("btn_murojaat", lang), callback_data="cat:murojaat", style="primary")
    b.button(text=t("btn_reklama", lang), callback_data="cat:reklama", style="success")
    b.button(text=t("btn_channels", lang), callback_data="channels", style="primary")
    b.button(text=t("btn_my_tickets", lang), callback_data="my_tickets", style="primary")
    b.button(text=t("btn_language", lang), callback_data="choose_language")
    b.adjust(2, 2, 2)
    return b.as_markup()


def language_kb():
    b = InlineKeyboardBuilder()
    for code, label in LANG_LABELS.items():
        b.button(text=label, callback_data=f"setlang:{code}", style="primary")
    b.button(text="⬅️ Ortga", callback_data="back_to_menu")
    b.adjust(1)
    return b.as_markup()


async def quick_reply_kb(message_id):
    templates = await get_templates()
    b = InlineKeyboardBuilder()
    styles_cycle = ["success", "primary"]
    for i, tpl in enumerate(templates):
        b.button(text=tpl["label"], callback_data=f"qreply:{message_id}:{tpl['id']}", style=styles_cycle[i % 2])
    b.adjust(1)
    return b.as_markup()


def rating_kb(message_id):
    b = InlineKeyboardBuilder()
    for i in range(1, 6):
        b.button(text="⭐" * i, callback_data=f"rate:{message_id}:{i}")
    b.adjust(5)
    return b.as_markup()


async def channels_kb(lang="uz"):
    channels = await get_channels()
    b = InlineKeyboardBuilder()
    for name, link in channels:
        b.button(text=name, url=link, style="success")
    b.button(text=t("back_button", lang), callback_data="back_to_menu", style="primary")
    b.adjust(1)
    return b.as_markup()


def view_msg_kb(message_id):
    b = InlineKeyboardBuilder()
    b.button(text="👁 Xabarni ko'rish", callback_data=f"view_msg:{message_id}", style="success")
    b.adjust(1)
    return b.as_markup()


def claim_kb(ticket_id):
    b = InlineKeyboardBuilder()
    b.button(text="🙋 Men javob beraman", callback_data=f"claim:{ticket_id}", style="success")
    b.adjust(1)
    return b.as_markup()


def view_reply_kb(message_id):
    b = InlineKeyboardBuilder()
    b.button(text="👁 Javobni ko'rish", callback_data=f"reveal_reply:{message_id}", style="primary")
    b.adjust(1)
    return b.as_markup()


def admin_main_kb():
    b = InlineKeyboardBuilder()
    b.button(text="📋 Barcha", callback_data="adm_list:all", style="primary")
    b.button(text="🔵 O'qilmagan", callback_data="adm_list:unread", style="danger")
    b.button(text="💡 Taklif", callback_data="adm_list:taklif")
    b.button(text="❓ Murojaat", callback_data="adm_list:murojaat", style="primary")
    b.button(text="📢 Reklama", callback_data="adm_list:reklama")
    b.button(text="📊 Statistika", callback_data="adm_stats", style="primary")
    b.button(text="📤 Eksport", callback_data="adm_export", style="success")
    b.button(text="🔍 Qidiruv", callback_data="adm_search", style="primary")
    b.button(text="🏆 TOP", callback_data="adm_topusers")
    b.button(text="📣 Xabar", callback_data="adm_broadcast", style="success")
    b.button(text="🗂 Shablonlar", callback_data="adm_templates", style="primary")
    b.button(text="🚫 Bloklangan", callback_data="adm_blocked", style="danger")
    b.button(text="📢 Kanallar", callback_data="adm_channels", style="success")
    b.button(text="🔄 Backup", callback_data="adm_backup")
    b.button(text="⚙️ Sozlamalar", callback_data="adm_settings", style="primary")
    b.adjust(2, 3, 2, 2, 2, 2, 2)
    return b.as_markup()


def ticket_admin_kb(ticket):
    tid = ticket["id"]
    b = InlineKeyboardBuilder()
    b.button(text="👤 Foydalanuvchi tarixi", callback_data=f"adm_history:{ticket['user_id']}", style="primary")
    b.button(text="🤖 AI xulosa", callback_data=f"adm_aisum:{tid}", style="primary")
    if ticket["tag"] == "hal qilindi":
        b.button(text="⏳ Kutilmoqda deb belgilash", callback_data=f"adm_tag:{tid}:kutilmoqda")
    else:
        b.button(text="✅ Hal qilindi deb belgilash", callback_data=f"adm_tag:{tid}:hal qilindi", style="success")
    if ticket.get("pinned"):
        b.button(text="📌 Pindan olish", callback_data=f"adm_pin:{tid}:0")
    else:
        b.button(text="📌 Pin qilish", callback_data=f"adm_pin:{tid}:1")
    b.button(text="🚫 Foydalanuvchini bloklash", callback_data=f"adm_block:{ticket['user_id']}", style="danger")
    b.button(text="🗑 O'chirish", callback_data=f"adm_delete:{tid}", style="danger")
    b.adjust(1)
    return b.as_markup()


def channels_manage_kb(channels):
    b = InlineKeyboardBuilder()
    for idx, (name, link) in enumerate(channels):
        b.button(text=f"🗑 {name}", callback_data=f"adm_delchannel:{idx}", style="danger")
    b.button(text="➕ Kanal qo'shish", callback_data="adm_addchannel", style="success")
    b.button(text="⬅️ Ortga", callback_data="adm_back", style="primary")
    b.adjust(1)
    return b.as_markup()


async def templates_manage_kb(templates):
    b = InlineKeyboardBuilder()
    for idx, tpl in enumerate(templates):
        b.button(text=f"🗑 {tpl['label']}", callback_data=f"adm_deltemplate:{idx}", style="danger")
    b.button(text="➕ Shablon qo'shish", callback_data="adm_addtemplate", style="success")
    b.button(text="⬅️ Ortga", callback_data="adm_back", style="primary")
    b.adjust(1)
    return b.as_markup()


def blocked_manage_kb(users):
    b = InlineKeyboardBuilder()
    for u in users:
        label = f"@{u['username']}" if u.get("username") else (u.get("full_name") or str(u["user_id"]))
        b.button(text=f"🔓 {label}", callback_data=f"adm_unblock:{u['user_id']}", style="success")
    b.button(text="⬅️ Ortga", callback_data="adm_back", style="primary")
    b.adjust(1)
    return b.as_markup()


def tickets_list_kb(tickets):
    b = InlineKeyboardBuilder()
    for tt in tickets:
        b.button(text=f"#{tt['id']}", callback_data=f"adm_open:{tt['id']}")
    b.button(text="⬅️ Ortga", callback_data="adm_back", style="primary")
    b.adjust(5)
    return b.as_markup()


def settings_kb(hours_enabled, auto_assign_enabled):
    b = InlineKeyboardBuilder()
    b.button(
        text=("🕐 Ish vaqtini o'chirish" if hours_enabled else "🕐 Ish vaqtini yoqish"),
        callback_data="adm_toggle_hours",
        style="danger" if hours_enabled else "success",
    )
    b.button(text="✏️ Vaqtni o'zgartirish", callback_data="adm_sethours", style="primary")
    b.button(
        text=("🎯 Avto-taqsimlashni o'chirish" if auto_assign_enabled else "🎯 Avto-taqsimlashni yoqish"),
        callback_data="adm_toggle_autoassign",
        style="danger" if auto_assign_enabled else "success",
    )
    b.button(text="🚦 Rate-limit sozlash", callback_data="adm_setflood", style="primary")
    b.button(text="⏰ Eslatma vaqti", callback_data="adm_setreminder", style="primary")
    b.button(text="⬅️ Ortga", callback_data="adm_back", style="primary")
    b.adjust(2, 2, 1, 1)
    return b.as_markup()


def cancel_kb(lang="uz", callback="cancel_category"):
    b = InlineKeyboardBuilder()
    b.button(text=t("cancel_button", lang), callback_data=callback, style="danger")
    b.adjust(1)
    return b.as_markup()


def admin_cancel_kb():
    b = InlineKeyboardBuilder()
    b.button(text="❌ Bekor qilish", callback_data="adm_cancel_pending", style="danger")
    b.adjust(1)
    return b.as_markup()


# ======================= FOYDALANUVCHI QISMI =======================

user_router = Router()

user_pending_category = {}


async def is_within_working_hours():
    enabled = await get_setting("working_hours_enabled", "1")
    if enabled != "1":
        return True
    start = await get_setting("working_hours_start", DEFAULT_WORKING_HOURS_START)
    end = await get_setting("working_hours_end", DEFAULT_WORKING_HOURS_END)
    now = time.strftime("%H:%M")
    return start <= now <= end


def match_faq(text):
    if not text:
        return None
    lowered = text.lower()
    for keyword, answer in FAQ_ANSWERS.items():
        if keyword in lowered:
            return answer
    return None


def contains_banned_words(text):
    if not text:
        return False
    lowered = text.lower()
    return any(w in lowered for w in BANNED_WORDS)


def make_preview(content_type, text_val, limit=80):
    type_labels = {"photo": "🖼 Rasm", "video": "🎥 Video", "document": "📎 Fayl"}
    base = type_labels.get(content_type)
    snippet = (text_val or "").strip()
    if snippet:
        if len(snippet) > limit:
            snippet = snippet[:limit] + "…"
        return f"{base + ': ' if base else ''}{snippet}"
    return base or "(matn yo'q)"


@user_router.message(CommandStart())
async def cmd_start(message: Message):
    await get_or_create_user(message.from_user.id, message.from_user.username, message.from_user.full_name)
    if await is_blocked(message.from_user.id):
        await message.answer("🚫 Siz botdan foydalanish huquqidan mahrum qilingansiz.")
        return
    lang = await get_user_language(message.from_user.id)
    await message.answer(t("welcome", lang), reply_markup=main_menu_kb(lang))


@user_router.callback_query(F.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery):
    lang = await get_user_language(call.from_user.id)
    await call.message.edit_text(t("welcome", lang), reply_markup=main_menu_kb(lang))
    await call.answer()


@user_router.callback_query(F.data == "choose_language")
async def choose_language_cb(call: CallbackQuery):
    lang = await get_user_language(call.from_user.id)
    await call.message.edit_text(t("choose_language", lang), reply_markup=language_kb())
    await call.answer()


@user_router.callback_query(F.data.startswith("setlang:"))
async def set_language_cb(call: CallbackQuery):
    lang = call.data.split(":")[1]
    await set_user_language(call.from_user.id, lang)
    await call.message.edit_text(t("language_set", lang), reply_markup=main_menu_kb(lang))
    await call.answer()


@user_router.callback_query(F.data == "channels")
async def show_channels(call: CallbackQuery):
    lang = await get_user_language(call.from_user.id)
    text = t("channels_header", lang)
    await call.message.edit_text(text, reply_markup=await channels_kb(lang))
    await call.answer()


@user_router.callback_query(F.data == "my_tickets")
async def my_tickets(call: CallbackQuery):
    lang = await get_user_language(call.from_user.id)
    tickets = await get_user_tickets(call.from_user.id)
    if not tickets:
        text = t("no_tickets", lang)
    else:
        lines = [t("my_tickets_header", lang)]
        for tt in tickets:
            tag_mark = "✅" if tt["tag"] == "hal qilindi" else "⏳"
            cat = CATEGORIES.get(tt["category"], tt["category"])
            lines.append(f"{tag_mark} #{tt['id']} — {cat}")
        text = "\n".join(lines)
    b = InlineKeyboardBuilder()
    b.button(text=t("back_button", lang), callback_data="back_to_menu", style="primary")
    b.adjust(1)
    await call.message.edit_text(text, reply_markup=b.as_markup())
    await call.answer()


@user_router.callback_query(F.data.startswith("cat:"))
async def choose_category(call: CallbackQuery):
    category = call.data.split(":")[1]
    user_pending_category[call.from_user.id] = category
    lang = await get_user_language(call.from_user.id)
    prompt = t(f"prompt_{category}", lang)
    await call.message.answer(prompt, reply_markup=cancel_kb(lang, "cancel_category"))
    await call.answer()


@user_router.callback_query(F.data == "cancel_category")
async def cancel_category_cb(call: CallbackQuery):
    user_pending_category.pop(call.from_user.id, None)
    lang = await get_user_language(call.from_user.id)
    try:
        await call.message.edit_text(t("welcome", lang), reply_markup=main_menu_kb(lang))
    except Exception:
        await call.message.answer(t("welcome", lang), reply_markup=main_menu_kb(lang))
    await call.answer("Bekor qilindi")


@user_router.message(F.text | F.photo | F.video | F.document)
async def handle_user_message(message: Message):
    user = message.from_user
    if user.id in ADMIN_IDS:
        return

    await get_or_create_user(user.id, user.username, user.full_name)
    lang = await get_user_language(user.id)

    if await is_blocked(user.id):
        await message.answer(t("blocked", lang))
        return

    if not await check_flood(user.id):
        await message.answer(t("flood_msg", lang))
        return

    text = message.text or message.caption

    if contains_banned_words(text):
        await message.answer(t("banned_msg", lang))
        return

    if text and await check_duplicate(user.id, text):
        await message.answer(t("duplicate_msg", lang))
        return

    faq_answer = match_faq(text)

    category = user_pending_category.pop(user.id, None)
    ticket = await get_open_ticket(user.id)

    if category:
        ticket_id = await create_ticket(user.id, category)
        ticket = await get_ticket(ticket_id)
        assigned_admin = await get_next_admin()
        if assigned_admin:
            await claim_ticket(ticket_id, assigned_admin)
            ticket = await get_ticket(ticket_id)
    elif ticket:
        ticket_id = ticket["id"]
    else:
        await message.answer(t("choose_category_first", lang), reply_markup=main_menu_kb(lang))
        return

    if message.text:
        content_type, text_val, file_id = "text", message.text, None
    elif message.photo:
        content_type, text_val, file_id = "photo", message.caption, message.photo[-1].file_id
    elif message.video:
        content_type, text_val, file_id = "video", message.caption, message.video.file_id
    elif message.document:
        content_type, text_val, file_id = "document", message.caption, message.document.file_id
    else:
        content_type, text_val, file_id = "text", message.text or "", None

    msg_id = await add_message(ticket_id, "user", content_type, text_val, file_id)

    category_label = CATEGORIES.get(ticket["category"], ticket["category"])
    username = f"@{user.username}" if user.username else "username yo'q"
    header = (
        f"🆕 <b>Yangi xabar</b> | {category_label}\n"
        f"👤 {user.full_name} ({username})\n"
        f"🆔 <code>{user.id}</code>\n"
        f"🎫 Ticket #{ticket_id}\n"
        f"───────────────"
    )

    working = await is_within_working_hours()
    preview = make_preview(content_type, text_val)
    silent = not working
    assigned_to = ticket.get("claimed_by")

    for admin_id in ADMIN_IDS:
        header_for_admin = header
        if assigned_to:
            header_for_admin += "\n🎯 Sizga biriktirildi!" if admin_id == assigned_to else "\n👤 Boshqa adminga biriktirilgan"
        try:
            await message.bot.send_message(
                admin_id, header_for_admin, reply_markup=claim_kb(ticket_id), disable_notification=silent
            )
            await message.bot.send_message(
                admin_id,
                f"📩 <b>Yangi xabar:</b>\n<i>{preview}</i>\n\nTo'liq ko'rish uchun tugmani bosing.",
                reply_markup=view_msg_kb(msg_id),
                disable_notification=silent
            )
        except Exception:
            continue

    ai_answer = None
    if not faq_answer and text:
        system_instruction = (
            "Siz Anifilm.uz sayti uchun mijozlarni qo'llab-quvvatlash yordamchisisiz. "
            f"Foydalanuvchiga qisqa (2-3 gap), do'stona javob bering. Javobni ushbu til kodida yozing: {lang}. "
            "Agar aniq javob bera olmasangiz, tez orada admin javob berishini bildiring."
        )
        ai_answer = await call_gemini(text, system_instruction)

    if faq_answer:
        await message.answer(faq_answer)
    else:
        confirm = t("confirm_received", lang)
        if not working:
            confirm += t("after_hours_add", lang)
        await message.answer(confirm)
        if ai_answer:
            await message.answer(f"{t('ai_prefix', lang)}\n\n{ai_answer}")


@user_router.callback_query(F.data.startswith("reveal_reply:"))
async def user_reveal_reply(call: CallbackQuery):
    lang = await get_user_language(call.from_user.id)
    message_id = int(call.data.split(":")[1])
    msg = await get_message(message_id)
    if not msg:
        await call.answer("Xabar topilmadi.")
        return

    already_read = bool(msg["is_read"])

    try:
        if msg["content_type"] == "text":
            await call.bot.send_message(call.from_user.id, msg["text"] or "")
        elif msg["content_type"] == "photo":
            await call.bot.send_photo(call.from_user.id, msg["file_id"], caption=msg["text"] or "")
        elif msg["content_type"] == "video":
            await call.bot.send_video(call.from_user.id, msg["file_id"], caption=msg["text"] or "")
        elif msg["content_type"] == "document":
            await call.bot.send_document(call.from_user.id, msg["file_id"], caption=msg["text"] or "")
    except Exception:
        pass

    try:
        await call.message.edit_text(t("reveal_opened", lang))
    except Exception:
        pass

    if not already_read:
        await mark_message_read(message_id)
        ticket = await get_ticket(msg["ticket_id"])
        admin_id = msg["admin_id"] or (ticket.get("claimed_by") if ticket else None)
        if admin_id:
            try:
                await call.bot.send_message(
                    admin_id,
                    f"✅ Foydalanuvchi javobingizni o'qidi. (Ticket #{ticket['id']})"
                )
            except Exception:
                pass
        try:
            await call.bot.send_message(
                call.from_user.id,
                t("rating_prompt", lang),
                reply_markup=rating_kb(message_id)
            )
        except Exception:
            pass
    await call.answer()


@user_router.callback_query(F.data.startswith("rate:"))
async def user_rate(call: CallbackQuery):
    lang = await get_user_language(call.from_user.id)
    _, message_id, score = call.data.split(":")
    message_id, score = int(message_id), int(score)
    await set_rating(message_id, score)
    msg = await get_message(message_id)
    if msg:
        ticket = await get_ticket(msg["ticket_id"])
        admin_id = msg["admin_id"]
        if admin_id and ticket:
            try:
                await call.bot.send_message(
                    admin_id,
                    f"⭐ Foydalanuvchi javobingizni {score}/5 baholadi. (Ticket #{ticket['id']})"
                )
            except Exception:
                pass
    try:
        await call.message.edit_text(t("rating_thanks", lang, score=score))
    except Exception:
        pass
    await call.answer()


# ======================= ADMIN QISMI =======================

admin_router = Router()
admin_router.message.filter(F.from_user.id.in_(ADMIN_IDS))
admin_router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))

admin_pending = {}
broadcast_pending_text = {}


def is_admin(user_id):
    return user_id in ADMIN_IDS


def ticket_summary_line(t_dict):
    unread_mark = "🔵" if t_dict.get("unread", 0) > 0 else "🟢"
    pin_mark = "📌 " if t_dict.get("pinned") else ""
    tag_mark = "✅" if t_dict.get("tag") == "hal qilindi" else "⏳"
    username = f"@{t_dict['username']}" if t_dict.get("username") else t_dict.get("full_name", "?")
    return f"{pin_mark}{unread_mark} {tag_mark} #{t_dict['id']} — {username} ({CATEGORIES.get(t_dict['category'], t_dict['category'])})"


@admin_router.message(Command("admin"))
async def admin_panel(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer("🛠 <b>Admin panel</b>", reply_markup=admin_main_kb())


@admin_router.callback_query(F.data == "adm_back")
async def adm_back(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await call.message.edit_text("🛠 <b>Admin panel</b>", reply_markup=admin_main_kb())
    await call.answer()


@admin_router.callback_query(F.data.startswith("adm_list:"))
async def adm_list(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    kind = call.data.split(":")[1]
    if kind == "all":
        tickets = await list_tickets()
    elif kind == "unread":
        tickets = await list_tickets(unread_only=True)
    else:
        tickets = await list_tickets(category=kind)

    if not tickets:
        await call.message.edit_text("Hozircha xabar yo'q.", reply_markup=admin_main_kb())
        return await call.answer()

    text = "📋 <b>Xabarlar ro'yxati</b>\n\n" + "\n".join(ticket_summary_line(tt) for tt in tickets)
    text += "\n\nOchish uchun raqamni bosing:"
    await call.message.edit_text(text, reply_markup=tickets_list_kb(tickets))
    await call.answer()


@admin_router.callback_query(F.data.startswith("adm_open:"))
async def adm_open_ticket(call: CallbackQuery):
    ticket_id = int(call.data.split(":")[1])
    ticket = await get_ticket(ticket_id)
    if not ticket:
        await call.answer("Bunday ticket topilmadi.", show_alert=True)
        return
    history = await get_ticket_history(ticket_id)
    lines = [f"🎫 <b>Ticket #{ticket_id}</b> | {CATEGORIES.get(ticket['category'], ticket['category'])} | {ticket['tag']}\n"]
    for m in history:
        sender = "👤 Foydalanuvchi" if m["sender"] == "user" else "🛠 Admin"
        content_label = m["text"] if m["text"] else f"[{m['content_type']}]"
        lines.append(f"{sender}: {content_label}")
    await call.message.answer("\n".join(lines), reply_markup=ticket_admin_kb(ticket))
    await call.answer()


@admin_router.callback_query(F.data.startswith("adm_aisum:"))
async def adm_ai_summary(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    ticket_id = int(call.data.split(":")[1])
    await call.answer("AI xulosa tayyorlanmoqda...")
    if not GEMINI_API_KEY:
        await call.message.answer("❌ GEMINI_API_KEY sozlanmagan, AI xulosa ishlamaydi.")
        return
    summary = await ai_summarize_ticket(ticket_id)
    if summary:
        await call.message.answer(f"🤖 <b>AI xulosa</b> (Ticket #{ticket_id}):\n\n{summary}")
    else:
        await call.message.answer("❌ AI xulosa olishda xatolik yuz berdi.")


@admin_router.callback_query(F.data.startswith("adm_history:"))
async def adm_history(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    user_id = int(call.data.split(":")[1])
    tickets = await get_user_tickets(user_id)
    if not tickets:
        await call.answer("Tarix topilmadi.", show_alert=True)
        return
    lines = [f"👤 Foydalanuvchi <code>{user_id}</code> tarixi:\n"]
    for tt in tickets:
        lines.append(ticket_summary_line(tt))
    await call.message.answer("\n".join(lines))
    await call.answer()


@admin_router.callback_query(F.data.startswith("adm_tag:"))
async def adm_tag(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    _, ticket_id, tag = call.data.split(":", 2)
    await set_tag(int(ticket_id), tag)
    await call.answer(f"Status: {tag}")


@admin_router.callback_query(F.data.startswith("adm_pin:"))
async def adm_pin(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    _, ticket_id, val = call.data.split(":")
    await pin_ticket(int(ticket_id), val == "1")
    await call.answer("Yangilandi")


@admin_router.callback_query(F.data.startswith("adm_delete:"))
async def adm_delete(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    ticket_id = int(call.data.split(":")[1])
    await delete_ticket(ticket_id)
    await call.answer("O'chirildi")
    await call.message.answer(f"🗑 Ticket #{ticket_id} o'chirildi.")


@admin_router.callback_query(F.data.startswith("adm_block:"))
async def adm_block(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    user_id = int(call.data.split(":")[1])
    await set_blocked(user_id, True)
    await call.answer("Bloklandi")
    await call.message.answer(f"🚫 Foydalanuvchi <code>{user_id}</code> bloklandi.")


@admin_router.callback_query(F.data == "adm_blocked")
async def adm_blocked_list(call: CallbackQuery):
    users = await get_blocked_users()
    text = (
        "🚫 <b>Bloklangan foydalanuvchilar yo'q.</b>"
        if not users
        else "🚫 <b>Bloklangan foydalanuvchilar</b>\n\nBlokdan chiqarish uchun tugmani bosing:"
    )
    await call.message.edit_text(text, reply_markup=blocked_manage_kb(users))
    await call.answer()


@admin_router.callback_query(F.data.startswith("adm_unblock:"))
async def adm_unblock(call: CallbackQuery):
    user_id = int(call.data.split(":")[1])
    await set_blocked(user_id, False)
    users = await get_blocked_users()
    text = (
        "🚫 <b>Bloklangan foydalanuvchilar yo'q.</b>"
        if not users
        else "🚫 <b>Bloklangan foydalanuvchilar</b>\n\nBlokdan chiqarish uchun tugmani bosing:"
    )
    await call.message.edit_text(text, reply_markup=blocked_manage_kb(users))
    await call.answer("Blokdan chiqarildi ✅")


@admin_router.callback_query(F.data == "adm_channels")
async def adm_channels(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    channels = await get_channels()
    if channels:
        lines = "\n".join(f"🟢 {name} — {link}" for name, link in channels)
    else:
        lines = "Hozircha kanal qo'shilmagan."
    text = f"📢 <b>Rasmiy kanallar</b>\n\n{lines}\n\nQo'shish yoki o'chirish uchun tugmalardan foydalaning."
    await call.message.edit_text(text, reply_markup=channels_manage_kb(channels))
    await call.answer()


@admin_router.callback_query(F.data.startswith("adm_delchannel:"))
async def adm_delchannel(call: CallbackQuery):
    idx = int(call.data.split(":")[1])
    ok = await remove_channel(idx)
    channels = await get_channels()
    if ok:
        await call.answer("Kanal o'chirildi ✅")
    else:
        await call.answer("Topilmadi")
    lines = "\n".join(f"🟢 {name} — {link}" for name, link in channels) if channels else "Hozircha kanal qo'shilmagan."
    text = f"📢 <b>Rasmiy kanallar</b>\n\n{lines}\n\nQo'shish yoki o'chirish uchun tugmalardan foydalaning."
    await call.message.edit_text(text, reply_markup=channels_manage_kb(channels))


@admin_router.callback_query(F.data == "adm_addchannel")
async def adm_addchannel_start(call: CallbackQuery):
    admin_pending[call.from_user.id] = "addchannel"
    await call.message.answer(
        "➕ Yangi kanal ma'lumotini shu formatda yuboring:\n<code>Nomi | https://t.me/link</code>",
        reply_markup=admin_cancel_kb()
    )
    await call.answer()


@admin_router.callback_query(F.data == "adm_templates")
async def adm_templates(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    templates = await get_templates()
    lines = "\n".join(f"🟢 {tpl['label']} — {tpl['text']}" for tpl in templates) if templates else "Hozircha shablon yo'q."
    text = f"🗂 <b>Tayyor javob shablonlari</b>\n\n{lines}\n\nQo'shish yoki o'chirish uchun tugmalardan foydalaning."
    await call.message.edit_text(text, reply_markup=await templates_manage_kb(templates))
    await call.answer()


@admin_router.callback_query(F.data.startswith("adm_deltemplate:"))
async def adm_deltemplate(call: CallbackQuery):
    idx = int(call.data.split(":")[1])
    ok = await remove_template(idx)
    templates = await get_templates()
    await call.answer("O'chirildi ✅" if ok else "Topilmadi")
    lines = "\n".join(f"🟢 {tpl['label']} — {tpl['text']}" for tpl in templates) if templates else "Hozircha shablon yo'q."
    text = f"🗂 <b>Tayyor javob shablonlari</b>\n\n{lines}\n\nQo'shish yoki o'chirish uchun tugmalardan foydalaning."
    await call.message.edit_text(text, reply_markup=await templates_manage_kb(templates))


@admin_router.callback_query(F.data == "adm_addtemplate")
async def adm_addtemplate_start(call: CallbackQuery):
    admin_pending[call.from_user.id] = "addtemplate"
    await call.message.answer(
        "➕ Yangi shablonni shu formatda yuboring:\n<code>Nomi | Matni</code>",
        reply_markup=admin_cancel_kb()
    )
    await call.answer()


@admin_router.callback_query(F.data == "adm_broadcast")
async def adm_broadcast_start(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    admin_pending[call.from_user.id] = "broadcast"
    await call.message.answer(
        "📣 Barcha foydalanuvchilarga yuboriladigan xabar matnini kiriting:",
        reply_markup=admin_cancel_kb()
    )
    await call.answer()


@admin_router.callback_query(F.data == "adm_broadcast_send")
async def adm_broadcast_send(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    text_val = broadcast_pending_text.pop(call.from_user.id, None)
    if not text_val:
        await call.answer("Xabar topilmadi")
        return
    await call.answer("Yuborilmoqda...")
    user_ids = await get_all_active_user_ids()
    sent, failed = 0, 0
    for uid in user_ids:
        try:
            await call.bot.send_message(uid, text_val)
            sent += 1
        except Exception:
            failed += 1
    await call.message.answer(f"📣 Xabar yuborildi.\n✅ Yuborildi: {sent}\n❌ Xato: {failed}")


@admin_router.callback_query(F.data == "adm_cancel_pending")
async def adm_cancel_pending(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    admin_pending.pop(call.from_user.id, None)
    broadcast_pending_text.pop(call.from_user.id, None)
    await call.answer("Bekor qilindi")
    await call.message.edit_text("🛠 <b>Admin panel</b>", reply_markup=admin_main_kb())


@admin_router.callback_query(F.data.startswith("claim:"))
async def claim_ticket_cb(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    ticket_id = int(call.data.split(":")[1])
    await claim_ticket(ticket_id, call.from_user.id)
    await call.answer("Siz ushbu ticket'ga javob berasiz.")
    await call.message.answer(f"🙋 Siz Ticket #{ticket_id} ga javobgar sifatida belgilandingiz.")


@admin_router.callback_query(F.data.startswith("view_msg:"))
async def admin_view_msg(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    message_id = int(call.data.split(":")[1])
    msg = await get_message(message_id)
    if not msg:
        await call.answer("Xabar topilmadi.")
        return

    already_read = bool(msg["is_read"])
    admin_id = call.from_user.id

    sent = None
    try:
        if msg["content_type"] == "text":
            sent = await call.bot.send_message(admin_id, msg["text"] or "")
        elif msg["content_type"] == "photo":
            sent = await call.bot.send_photo(admin_id, msg["file_id"], caption=msg["text"] or "")
        elif msg["content_type"] == "video":
            sent = await call.bot.send_video(admin_id, msg["file_id"], caption=msg["text"] or "")
        elif msg["content_type"] == "document":
            sent = await call.bot.send_document(admin_id, msg["file_id"], caption=msg["text"] or "")
    except Exception:
        pass

    if sent:
        await add_admin_forward(message_id, msg["ticket_id"], admin_id, sent.message_id)
        try:
            await call.bot.send_message(
                admin_id,
                "👆 Javob berish uchun shu xabarga <b>Reply</b> qiling,\nyoki tayyor javoblardan birini tanlang:",
                reply_markup=await quick_reply_kb(message_id)
            )
        except Exception:
            pass

    try:
        await call.message.edit_text("✅ Xabar ochildi (yuqorida).")
    except Exception:
        pass

    if not already_read:
        await mark_message_read(message_id)
        ticket = await get_ticket(msg["ticket_id"])
        if ticket:
            try:
                await call.bot.send_message(ticket["user_id"], "✅ Xabaringiz o'qildi. Tez orada javob beramiz.")
            except Exception:
                pass
    await call.answer()


@admin_router.callback_query(F.data.startswith("qreply:"))
async def admin_quick_reply(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    _, message_id, key = call.data.split(":")
    message_id = int(message_id)
    templates = await get_templates()
    tpl = next((x for x in templates if x["id"] == key), None)
    if not tpl:
        await call.answer("Noma'lum shablon")
        return
    text_val = tpl["text"]
    msg = await get_message(message_id)
    if not msg:
        await call.answer("Xabar topilmadi")
        return
    ticket = await get_ticket(msg["ticket_id"])
    if not ticket:
        await call.answer("Ticket topilmadi")
        return
    reply_msg_id = await add_message(ticket["id"], "admin", "text", text_val, None, admin_id=call.from_user.id)
    lang = await get_user_language(ticket["user_id"])
    try:
        await call.bot.send_message(
            ticket["user_id"],
            t("reply_notify", lang),
            reply_markup=view_reply_kb(reply_msg_id)
        )
        await call.answer("Yuborildi ✅")
    except Exception:
        await call.answer("Xatolik yuz berdi")


@admin_router.callback_query(F.data == "adm_stats")
async def adm_stats(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    s = await get_stats()
    lines = [
        "📊 <b>Statistika</b>\n",
        f"👥 Foydalanuvchilar: {s['users']}",
        f"🎫 Jami murojaatlar: {s['tickets_total']}",
        f"💡 Takliflar: {s.get('cat_taklif', 0)}",
        f"❓ Murojaatlar: {s.get('cat_murojaat', 0)}",
        f"📢 Reklamalar: {s.get('cat_reklama', 0)}",
        f"✅ Hal qilingan: {s['resolved']}",
        f"⏳ Kutilayotgan: {s['pending']}",
    ]
    await call.message.edit_text("\n".join(lines), reply_markup=admin_main_kb())
    await call.answer()


@admin_router.callback_query(F.data == "adm_export")
async def adm_export(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    csv_data = await export_csv()
    file = BufferedInputFile(csv_data.encode("utf-8"), filename="anifilm_murojaatlar.csv")
    await call.message.answer_document(file, caption="📤 Barcha murojaatlar eksporti")
    await call.answer()


async def build_settings_view():
    enabled = await get_setting("working_hours_enabled", "1")
    start = await get_setting("working_hours_start", DEFAULT_WORKING_HOURS_START)
    end = await get_setting("working_hours_end", DEFAULT_WORKING_HOURS_END)
    status_label = "yoqilgan ✅" if enabled == "1" else "o'chirilgan ❌"
    limit_msgs, limit_secs, dup_window = await get_flood_settings()
    reminder_minutes = await get_setting("reminder_minutes", "30")
    auto_assign = await get_setting("auto_assign_enabled", "1")
    auto_assign_label = "yoqilgan ✅" if auto_assign == "1" else "o'chirilgan ❌"
    text = (
        f"⚙️ <b>Sozlamalar</b>\n\n"
        f"🕐 Ish vaqti: {status_label}\n"
        f"Boshlanishi: {start} | Tugashi: {end}\n\n"
        f"🚦 Rate-limit: {limit_msgs} xabar / {limit_secs} soniya\n"
        f"Dublikat oynasi: {dup_window} soniya\n\n"
        f"⏰ Eslatma vaqti: {reminder_minutes} daqiqa (javobsiz qolsa)\n\n"
        f"🎯 Avto-taqsimlash: {auto_assign_label}\n\n"
        f"🤖 Gemini AI: {'sozlangan ✅' if GEMINI_API_KEY else 'sozlanmagan ❌ (GEMINI_API_KEY kerak)'}\n\n"
        f"O'zgartirish uchun tugmalardan foydalaning:"
    )
    kb = settings_kb(enabled == "1", auto_assign == "1")
    return text, kb


@admin_router.callback_query(F.data == "adm_settings")
async def adm_settings(call: CallbackQuery):
    text, kb = await build_settings_view()
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer()


@admin_router.callback_query(F.data == "adm_toggle_hours")
async def adm_toggle_hours(call: CallbackQuery):
    enabled = await get_setting("working_hours_enabled", "1")
    await set_setting("working_hours_enabled", "0" if enabled == "1" else "1")
    text, kb = await build_settings_view()
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer("Yangilandi ✅")


@admin_router.callback_query(F.data == "adm_toggle_autoassign")
async def adm_toggle_autoassign(call: CallbackQuery):
    val = await get_setting("auto_assign_enabled", "1")
    await set_setting("auto_assign_enabled", "0" if val == "1" else "1")
    text, kb = await build_settings_view()
    await call.message.edit_text(text, reply_markup=kb)
    await call.answer("Yangilandi ✅")


@admin_router.callback_query(F.data == "adm_sethours")
async def adm_sethours_start(call: CallbackQuery):
    admin_pending[call.from_user.id] = "sethours"
    await call.message.answer(
        "🕐 Ish vaqtini shu formatda kiriting:\n<code>09:00 18:00</code>",
        reply_markup=admin_cancel_kb()
    )
    await call.answer()


@admin_router.callback_query(F.data == "adm_setflood")
async def adm_setflood_start(call: CallbackQuery):
    admin_pending[call.from_user.id] = "setflood"
    await call.message.answer(
        "🚦 Rate-limit qiymatlarini shu formatda kiriting (xabar_soni tekshiruv_soniya dublikat_soniya):\n<code>5 60 30</code>",
        reply_markup=admin_cancel_kb()
    )
    await call.answer()


@admin_router.callback_query(F.data == "adm_setreminder")
async def adm_setreminder_start(call: CallbackQuery):
    admin_pending[call.from_user.id] = "setreminder"
    await call.message.answer(
        "⏰ Eslatma vaqtini daqiqada kiriting:\n<code>30</code>",
        reply_markup=admin_cancel_kb()
    )
    await call.answer()


@admin_router.callback_query(F.data == "adm_search")
async def adm_search_start(call: CallbackQuery):
    admin_pending[call.from_user.id] = "search"
    await call.message.answer("🔍 Qidiruv uchun so'z yoki ismni kiriting:", reply_markup=admin_cancel_kb())
    await call.answer()


@admin_router.callback_query(F.data == "adm_topusers")
async def adm_topusers_cb(call: CallbackQuery):
    top = await get_top_users()
    if not top:
        await call.answer("Hozircha ma'lumot yo'q.", show_alert=True)
        return
    lines = ["🏆 <b>Eng ko'p murojaat qiluvchilar:</b>\n"]
    for i, u in enumerate(top, 1):
        username = f"@{u['username']}" if u["username"] else u["full_name"]
        lines.append(f"{i}. {username} — {u['cnt']} ta murojaat")
    await call.message.answer("\n".join(lines))
    await call.answer()


@admin_router.callback_query(F.data == "adm_backup")
async def adm_backup_cb(call: CallbackQuery):
    try:
        with open(DB_PATH, "rb") as f:
            file = BufferedInputFile(f.read(), filename="anifilm_bot_backup.db")
        await call.message.answer_document(file, caption="🔄 Ma'lumotlar bazasi zaxira nusxasi")
    except Exception as e:
        await call.message.answer(f"Xatolik: {e}")
    await call.answer()


@admin_router.message(F.reply_to_message)
async def handle_admin_reply(message: Message):
    if not is_admin(message.from_user.id):
        return

    forward = await get_ticket_by_admin_forward(message.from_user.id, message.reply_to_message.message_id)
    if not forward:
        return

    ticket_id = forward["ticket_id"]
    ticket = await get_ticket(ticket_id)
    if not ticket:
        await message.answer("Ticket topilmadi (o'chirilgan bo'lishi mumkin).")
        return

    if message.text:
        content_type, text_val, file_id = "text", message.text, None
    elif message.photo:
        content_type, text_val, file_id = "photo", message.caption, message.photo[-1].file_id
    elif message.video:
        content_type, text_val, file_id = "video", message.caption, message.video.file_id
    elif message.document:
        content_type, text_val, file_id = "document", message.caption, message.document.file_id
    else:
        content_type, text_val, file_id = "text", message.text or "", None

    reply_msg_id = await add_message(
        ticket_id, "admin", content_type, text_val, file_id, admin_id=message.from_user.id
    )

    lang = await get_user_language(ticket["user_id"])
    reply_kb = view_reply_kb(reply_msg_id)
    try:
        await message.bot.send_message(
            ticket["user_id"],
            t("reply_notify", lang),
            reply_markup=reply_kb
        )
        await message.answer("✅ Javobingiz foydalanuvchiga yuborildi.")
    except Exception as e:
        await message.answer(f"❌ Yuborib bo'lmadi: {e}")


@admin_router.message(F.text)
async def handle_admin_plain_text(message: Message):
    if not message.text or message.text.startswith("/"):
        return
    pending = admin_pending.get(message.from_user.id)
    if not pending:
        return

    if pending == "broadcast":
        admin_pending.pop(message.from_user.id, None)
        broadcast_pending_text[message.from_user.id] = message.text
        confirm_kb = InlineKeyboardBuilder()
        confirm_kb.button(text="✅ Yuborish", callback_data="adm_broadcast_send", style="success")
        confirm_kb.button(text="❌ Bekor qilish", callback_data="adm_cancel_pending", style="danger")
        confirm_kb.adjust(1)
        await message.answer(
            f"Quyidagi xabar barcha foydalanuvchilarga yuboriladi:\n\n{message.text}\n\nTasdiqlaysizmi?",
            reply_markup=confirm_kb.as_markup()
        )
        return

    if pending == "addchannel":
        raw = message.text.strip()
        if "|" not in raw:
            await message.answer("❌ Format noto'g'ri. Qaytadan kiriting:\n<code>Nomi | https://t.me/link</code>", reply_markup=admin_cancel_kb())
            return
        name, link = (p.strip() for p in raw.split("|", 1))
        if not name or not link:
            await message.answer("❌ Format noto'g'ri. Qaytadan kiriting:\n<code>Nomi | https://t.me/link</code>", reply_markup=admin_cancel_kb())
            return
        admin_pending.pop(message.from_user.id, None)
        await add_channel(name, link)
        await message.answer(f"✅ Kanal qo'shildi: 🟢 {name} — {link}")
        return

    if pending == "addtemplate":
        raw = message.text.strip()
        if "|" not in raw:
            await message.answer("❌ Format noto'g'ri. Qaytadan kiriting:\n<code>Nomi | Matni</code>", reply_markup=admin_cancel_kb())
            return
        label, text_val = (p.strip() for p in raw.split("|", 1))
        if not label or not text_val:
            await message.answer("❌ Format noto'g'ri. Qaytadan kiriting:\n<code>Nomi | Matni</code>", reply_markup=admin_cancel_kb())
            return
        admin_pending.pop(message.from_user.id, None)
        await add_template(label, text_val)
        await message.answer(f"✅ Shablon qo'shildi: {label}")
        return

    if pending == "sethours":
        parts = message.text.split()
        if len(parts) != 2:
            await message.answer("❌ Format noto'g'ri. Qaytadan kiriting:\n<code>09:00 18:00</code>", reply_markup=admin_cancel_kb())
            return
        admin_pending.pop(message.from_user.id, None)
        await set_setting("working_hours_start", parts[0])
        await set_setting("working_hours_end", parts[1])
        await message.answer(f"✅ Ish vaqti: {parts[0]} - {parts[1]}")
        return

    if pending == "setflood":
        parts = message.text.split()
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            await message.answer("❌ Format noto'g'ri. Qaytadan kiriting:\n<code>5 60 30</code>", reply_markup=admin_cancel_kb())
            return
        admin_pending.pop(message.from_user.id, None)
        await set_setting("flood_limit_messages", parts[0])
        await set_setting("flood_limit_seconds", parts[1])
        await set_setting("duplicate_window_seconds", parts[2])
        await message.answer(f"✅ Rate-limit yangilandi: {parts[0]} xabar / {parts[1]} soniya, dublikat: {parts[2]} soniya")
        return

    if pending == "setreminder":
        val = message.text.strip()
        if not val.isdigit():
            await message.answer("❌ Faqat son kiriting. Qaytadan kiriting:\n<code>30</code>", reply_markup=admin_cancel_kb())
            return
        admin_pending.pop(message.from_user.id, None)
        await set_setting("reminder_minutes", val)
        await message.answer(f"✅ Eslatma vaqti: {val} daqiqa")
        return

    if pending == "search":
        admin_pending.pop(message.from_user.id, None)
        results = await search_tickets(message.text.strip())
        if not results:
            await message.answer("Hech narsa topilmadi.")
            return
        lines = ["🔍 <b>Qidiruv natijalari:</b>\n"] + [ticket_summary_line(tt) for tt in results]
        await message.answer("\n".join(lines))
        return


# ======================= XATOLIKLAR =======================

async def global_error_handler(event: ErrorEvent, bot: Bot):
    logging.exception("Botda xatolik yuz berdi", exc_info=event.exception)
    error_text = f"❌ <b>Botda xatolik</b>\n<code>{type(event.exception).__name__}: {str(event.exception)[:500]}</code>"
    for admin_id in ADMIN_IDS:
        try:
            await bot.send_message(admin_id, error_text)
        except Exception:
            continue
    return True


# ======================= ISHGA TUSHIRISH =======================

async def daily_backup_task(bot: Bot):
    while True:
        await asyncio.sleep(24 * 3600)
        try:
            with open(DB_PATH, "rb") as f:
                data = f.read()
            for admin_id in ADMIN_IDS:
                try:
                    file = BufferedInputFile(data, filename="kunlik_backup.db")
                    await bot.send_document(admin_id, file, caption="🔄 Kunlik avtomatik zaxira nusxa")
                except Exception:
                    continue
        except Exception:
            continue


async def weekly_report_task(bot: Bot):
    while True:
        await asyncio.sleep(7 * 24 * 3600)
        try:
            s = await get_stats()
            top = await get_top_users(3)
            lines = [
                "📊 <b>Haftalik hisobot</b>\n",
                f"👥 Foydalanuvchilar: {s['users']}",
                f"🎫 Jami murojaatlar: {s['tickets_total']}",
                f"💡 Takliflar: {s.get('cat_taklif', 0)}",
                f"❓ Murojaatlar: {s.get('cat_murojaat', 0)}",
                f"📢 Reklamalar: {s.get('cat_reklama', 0)}",
                f"✅ Hal qilingan: {s['resolved']}",
                f"⏳ Kutilayotgan: {s['pending']}",
            ]
            if top:
                lines.append("\n🏆 Eng faol foydalanuvchilar:")
                for i, u in enumerate(top, 1):
                    username = f"@{u['username']}" if u["username"] else u["full_name"]
                    lines.append(f"{i}. {username} — {u['cnt']} ta")
            text = "\n".join(lines)
            for admin_id in ADMIN_IDS:
                try:
                    await bot.send_message(admin_id, text)
                except Exception:
                    continue
        except Exception:
            continue


async def reminder_task(bot: Bot):
    while True:
        await asyncio.sleep(5 * 60)
        try:
            minutes = int(await get_setting("reminder_minutes", "30"))
            threshold = int(time.time()) - minutes * 60
            async with aiosqlite.connect(DB_PATH) as db:
                db.row_factory = aiosqlite.Row
                cur = await db.execute("""
                    SELECT t.*, u.username, u.full_name FROM tickets t
                    JOIN users u ON u.user_id = t.user_id
                    WHERE t.status='open'
                """)
                rows = await cur.fetchall()

            for row in rows:
                ticket = dict(row)
                history = await get_ticket_history(ticket["id"])
                if not history:
                    continue
                last = history[-1]
                if last["sender"] != "user":
                    continue
                if last["created_at"] > threshold:
                    continue
                if ticket.get("last_reminder_at") and ticket["last_reminder_at"] > last["created_at"]:
                    continue

                summary_line = ticket_summary_line(ticket)
                for admin_id in ADMIN_IDS:
                    try:
                        await bot.send_message(admin_id, f"⏰ Eslatma: javob kutilmoqda!\n{summary_line}")
                    except Exception:
                        continue

                async with aiosqlite.connect(DB_PATH) as db:
                    await db.execute(
                        "UPDATE tickets SET last_reminder_at=? WHERE id=?", (int(time.time()), ticket["id"])
                    )
                    await db.commit()
        except Exception:
            continue


async def on_startup(bot: Bot):
    await init_db()
    asyncio.create_task(daily_backup_task(bot))
    asyncio.create_task(weekly_report_task(bot))
    asyncio.create_task(reminder_task(bot))
    logging.info("Baza tayyor, bot ishga tushmoqda...")


async def run_bot():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable topilmadi! Render sozlamalarida qo'shing.")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(admin_router)
    dp.include_router(user_router)

    dp.errors.register(global_error_handler)
    dp.startup.register(on_startup)

    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


async def handle_ping(request):
    return web.Response(text="Anifilm Support bot ishlayapti ✅")


async def run_webserver():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    app.router.add_get("/health", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", PORT)
    await site.start()
    logging.info(f"Web-server {PORT}-portda ishga tushdi.")


async def main():
    await asyncio.gather(run_webserver(), run_bot())


if __name__ == "__main__":
    asyncio.run(main())
