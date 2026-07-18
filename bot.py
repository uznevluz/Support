import os
import time
import json
import csv
import io
import logging
import asyncio

import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, Router, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder

logging.basicConfig(level=logging.INFO)

# ======================= SOZLAMALAR =======================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "5383321037").split(",") if x.strip()]
PORT = int(os.getenv("PORT", "10000"))
DB_PATH = os.getenv("DB_PATH", "bot.db")

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

        try:
            await db.execute("ALTER TABLE messages ADD COLUMN rating INTEGER")
            await db.commit()
        except Exception:
            pass

        defaults = {
            "working_hours_enabled": "1" if DEFAULT_WORKING_HOURS_ENABLED else "0",
            "working_hours_start": DEFAULT_WORKING_HOURS_START,
            "working_hours_end": DEFAULT_WORKING_HOURS_END,
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


async def is_blocked(user_id):
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT is_blocked FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        return bool(row and row[0])


async def set_blocked(user_id, blocked):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE users SET is_blocked=? WHERE user_id=?", (1 if blocked else 0, user_id))
        await db.commit()


async def check_flood(user_id):
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT window_start, window_count FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        if not row:
            return True
        window_start, window_count = row
        if now - window_start > FLOOD_LIMIT_SECONDS:
            await db.execute("UPDATE users SET window_start=?, window_count=1 WHERE user_id=?", (now, user_id))
            await db.commit()
            return True
        if window_count >= FLOOD_LIMIT_MESSAGES:
            return False
        await db.execute("UPDATE users SET window_count=window_count+1 WHERE user_id=?", (user_id,))
        await db.commit()
        return True


async def check_duplicate(user_id, text):
    if not text:
        return False
    now = int(time.time())
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("SELECT last_text, last_text_time FROM users WHERE user_id=?", (user_id,))
        row = await cur.fetchone()
        is_dup = False
        if row and row[0] == text and (now - (row[1] or 0)) < DUPLICATE_WINDOW_SECONDS:
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

def main_menu_kb():
    b = InlineKeyboardBuilder()
    b.button(text="💡 Taklif", callback_data="cat:taklif")
    b.button(text="❓ Murojaat", callback_data="cat:murojaat", style="primary")
    b.button(text="📢 Reklama", callback_data="cat:reklama")
    b.button(text="📢 Rasmiy kanallarimiz", callback_data="channels", style="success")
    b.button(text="📄 Mening murojaatlarim", callback_data="my_tickets")
    b.adjust(1)
    return b.as_markup()


QUICK_REPLIES = {
    "thanks": "🙏 Rahmat, xabaringiz uchun!",
    "review": "🔍 Ko'rib chiqmoqdamiz, tez orada to'liq javob beramiz.",
    "done": "✅ Muammo hal qilindi. Boshqa savol bo'lsa, yozishingiz mumkin.",
}


def quick_reply_kb(message_id):
    b = InlineKeyboardBuilder()
    b.button(text="🙏 Rahmat", callback_data=f"qreply:{message_id}:thanks", style="success")
    b.button(text="🔍 Ko'rib chiqamiz", callback_data=f"qreply:{message_id}:review", style="primary")
    b.button(text="✅ Hal qilindi", callback_data=f"qreply:{message_id}:done", style="success")
    b.adjust(1)
    return b.as_markup()


def rating_kb(message_id):
    b = InlineKeyboardBuilder()
    for i in range(1, 6):
        b.button(text="⭐" * i, callback_data=f"rate:{message_id}:{i}")
    b.adjust(5)
    return b.as_markup()


async def channels_kb():
    channels = await get_channels()
    b = InlineKeyboardBuilder()
    for name, link in channels:
        b.button(text=name, url=link, style="success")
    b.button(text="⬅️ Ortga", callback_data="back_to_menu")
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
    b.button(text="📋 Barcha xabarlar", callback_data="adm_list:all")
    b.button(text="💡 Takliflar", callback_data="adm_list:taklif")
    b.button(text="❓ Murojaatlar", callback_data="adm_list:murojaat", style="primary")
    b.button(text="📢 Reklamalar", callback_data="adm_list:reklama")
    b.button(text="🔵 O'qilmaganlar", callback_data="adm_list:unread", style="danger")
    b.button(text="📊 Statistika", callback_data="adm_stats")
    b.button(text="📤 Eksport (CSV)", callback_data="adm_export")
    b.button(text="🚫 Bloklangan foydalanuvchilar", callback_data="adm_blocked", style="danger")
    b.button(text="📢 Kanallarni boshqarish", callback_data="adm_channels", style="success")
    b.button(text="⚙️ Sozlamalar", callback_data="adm_settings")
    b.adjust(1)
    return b.as_markup()


def ticket_admin_kb(ticket):
    tid = ticket["id"]
    b = InlineKeyboardBuilder()
    b.button(text="👤 Foydalanuvchi tarixi", callback_data=f"adm_history:{ticket['user_id']}")
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
    b.button(text="⬅️ Ortga", callback_data="adm_back")
    b.adjust(1)
    return b.as_markup()


def settings_kb():
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Ortga", callback_data="adm_back")
    b.adjust(1)
    return b.as_markup()


# ======================= FOYDALANUVCHI QISMI =======================

user_router = Router()

WELCOME_TEXT = (
    "📢 <b>Taklif, Murojaat va Reklama</b>\n\n"
    "Assalomu alaykum!\n\n"
    "Anifilm.uz jamoasi sizning har bir fikr va taklifingizni qadrlaydi.\n\n"
    "💡 Takliflaringiz orqali saytimizni yanada rivojlantirishga yordam bera olasiz.\n"
    "❓ Savol yoki murojaatlaringiz bo'lsa, administrator bilan bog'laning.\n"
    "📢 Reklama, hamkorlik yoki biznes takliflari bo'yicha ham murojaat qilishingiz mumkin.\n\n"
    "📝 Quyidagi bo'limlardan birini tanlang."
)

CATEGORY_PROMPT = {
    "taklif": "💡 Taklifingizni yozib qoldiring (matn, rasm yoki video yuborishingiz mumkin).",
    "murojaat": "❓ Murojaatingizni yozib qoldiring (matn, rasm yoki video yuborishingiz mumkin).",
    "reklama": "📢 Reklama/hamkorlik taklifingizni yozib qoldiring (matn, rasm yoki video yuborishingiz mumkin).",
}

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
    await message.answer(WELCOME_TEXT, reply_markup=main_menu_kb())


@user_router.callback_query(F.data == "back_to_menu")
async def back_to_menu(call: CallbackQuery):
    await call.message.edit_text(WELCOME_TEXT, reply_markup=main_menu_kb())
    await call.answer()


@user_router.callback_query(F.data == "channels")
async def show_channels(call: CallbackQuery):
    text = "📢 <b>Rasmiy kanallarimiz:</b>\n\nQuyidagi tugmalar orqali kanallarimizga o'ting."
    await call.message.edit_text(text, reply_markup=await channels_kb())
    await call.answer()


@user_router.callback_query(F.data == "my_tickets")
async def my_tickets(call: CallbackQuery):
    tickets = await get_user_tickets(call.from_user.id)
    if not tickets:
        text = "📄 Sizda hali murojaatlar yo'q."
    else:
        lines = ["📄 <b>Mening murojaatlarim:</b>\n"]
        for t in tickets:
            tag_mark = "✅" if t["tag"] == "hal qilindi" else "⏳"
            cat = CATEGORIES.get(t["category"], t["category"])
            lines.append(f"{tag_mark} #{t['id']} — {cat}")
        text = "\n".join(lines)
    b = InlineKeyboardBuilder()
    b.button(text="⬅️ Ortga", callback_data="back_to_menu")
    b.adjust(1)
    await call.message.edit_text(text, reply_markup=b.as_markup())
    await call.answer()


@user_router.callback_query(F.data.startswith("cat:"))
async def choose_category(call: CallbackQuery):
    category = call.data.split(":")[1]
    user_pending_category[call.from_user.id] = category
    await call.message.answer(CATEGORY_PROMPT[category])
    await call.answer()


@user_router.message(F.text | F.photo | F.video | F.document)
async def handle_user_message(message: Message):
    user = message.from_user
    if user.id in ADMIN_IDS:
        return

    await get_or_create_user(user.id, user.username, user.full_name)

    if await is_blocked(user.id):
        await message.answer("🚫 Siz botdan foydalanish huquqidan mahrum qilingansiz.")
        return

    if not await check_flood(user.id):
        await message.answer("⏳ Siz juda tez-tez xabar yuboryapsiz. Iltimos, biroz kuting.")
        return

    text = message.text or message.caption

    if contains_banned_words(text):
        await message.answer("⚠️ Xabaringizda taqiqlangan so'zlar aniqlandi. Iltimos, xabaringizni tahrirlab qayta yuboring.")
        return

    if text and await check_duplicate(user.id, text):
        await message.answer("📵 Siz shu xabarni allaqachon yubordingiz. Iltimos, kuting, tez orada javob beramiz.")
        return

    faq_answer = match_faq(text)

    category = user_pending_category.pop(user.id, None)
    ticket = await get_open_ticket(user.id)

    if category:
        ticket_id = await create_ticket(user.id, category)
        ticket = await get_ticket(ticket_id)
    elif ticket:
        ticket_id = ticket["id"]
    else:
        await message.answer("Iltimos, avval bo'lim tanlang:", reply_markup=main_menu_kb())
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

    for admin_id in ADMIN_IDS:
        try:
            await message.bot.send_message(
                admin_id, header, reply_markup=claim_kb(ticket_id), disable_notification=silent
            )
            await message.bot.send_message(
                admin_id,
                f"📩 <b>Yangi xabar:</b>\n<i>{preview}</i>\n\nTo'liq ko'rish uchun tugmani bosing.",
                reply_markup=view_msg_kb(msg_id),
                disable_notification=silent
            )
        except Exception:
            continue

    if faq_answer:
        await message.answer(faq_answer)
    else:
        confirm = "✅ Xabaringiz qabul qilindi, tez orada javob beramiz."
        if not working:
            confirm += "\n\n🕐 Hozir ish vaqtidan tashqari, shuning uchun javob berish biroz kechikishi mumkin."
        await message.answer(confirm)


@user_router.callback_query(F.data.startswith("reveal_reply:"))
async def user_reveal_reply(call: CallbackQuery):
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
        await call.message.edit_text("✅ Javob ochildi (yuqorida).")
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
                "Javobdan mamnunmisiz? Bahoni tanlang:",
                reply_markup=rating_kb(message_id)
            )
        except Exception:
            pass
    await call.answer()


@user_router.callback_query(F.data.startswith("rate:"))
async def user_rate(call: CallbackQuery):
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
        await call.message.edit_text(f"Rahmat! Siz {score}/5 baho berdingiz. ⭐")
    except Exception:
        pass
    await call.answer()


# ======================= ADMIN QISMI =======================

admin_router = Router()


def is_admin(user_id):
    return user_id in ADMIN_IDS


def ticket_summary_line(t):
    unread_mark = "🔵" if t.get("unread", 0) > 0 else "🟢"
    pin_mark = "📌 " if t.get("pinned") else ""
    tag_mark = "✅" if t.get("tag") == "hal qilindi" else "⏳"
    username = f"@{t['username']}" if t.get("username") else t.get("full_name", "?")
    return f"{pin_mark}{unread_mark} {tag_mark} #{t['id']} — {username} ({CATEGORIES.get(t['category'], t['category'])})"


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

    text = "📋 <b>Xabarlar ro'yxati</b>\n\n" + "\n".join(ticket_summary_line(t) for t in tickets)
    text += "\n\nTicket'ni ochish uchun: /ticket ID"
    await call.message.edit_text(text, reply_markup=admin_main_kb())
    await call.answer()


@admin_router.message(Command("ticket"))
async def open_ticket(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Foydalanish: /ticket 5")
        return
    ticket_id = int(parts[1])
    ticket = await get_ticket(ticket_id)
    if not ticket:
        await message.answer("Bunday ticket topilmadi.")
        return
    history = await get_ticket_history(ticket_id)
    lines = [f"🎫 <b>Ticket #{ticket_id}</b> | {CATEGORIES.get(ticket['category'], ticket['category'])} | {ticket['tag']}\n"]
    for m in history:
        sender = "👤 Foydalanuvchi" if m["sender"] == "user" else "🛠 Admin"
        content_label = m["text"] if m["text"] else f"[{m['content_type']}]"
        lines.append(f"{sender}: {content_label}")
    await message.answer("\n".join(lines), reply_markup=ticket_admin_kb(ticket))


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
    for t in tickets:
        lines.append(ticket_summary_line(t))
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


@admin_router.message(Command("unblock"))
async def unblock_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) < 2 or not parts[1].isdigit():
        await message.answer("Foydalanish: /unblock 123456789")
        return
    await set_blocked(int(parts[1]), False)
    await message.answer("✅ Blokdan chiqarildi.")


@admin_router.callback_query(F.data == "adm_blocked")
async def adm_blocked_list(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    await call.message.answer("🚫 Bloklangan foydalanuvchini blokdan chiqarish uchun:\n/unblock USER_ID")
    await call.answer()


@admin_router.callback_query(F.data == "adm_channels")
async def adm_channels(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    channels = await get_channels()
    if channels:
        lines = "\n".join(f"🟢 {name} — {link}" for name, link in channels)
    else:
        lines = "Hozircha kanal qo'shilmagan."
    text = (
        f"📢 <b>Rasmiy kanallar</b>\n\n{lines}\n\n"
        f"➕ Qo'shish: <code>/addchannel Nomi | https://t.me/link</code>\n"
        f"🗑 O'chirish uchun pastdagi tugmani bosing."
    )
    await call.message.edit_text(text, reply_markup=channels_manage_kb(channels))
    await call.answer()


@admin_router.callback_query(F.data.startswith("adm_delchannel:"))
async def adm_delchannel(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    idx = int(call.data.split(":")[1])
    ok = await remove_channel(idx)
    channels = await get_channels()
    if ok:
        await call.answer("Kanal o'chirildi ✅")
    else:
        await call.answer("Topilmadi")
    lines = "\n".join(f"🟢 {name} — {link}" for name, link in channels) if channels else "Hozircha kanal qo'shilmagan."
    text = (
        f"📢 <b>Rasmiy kanallar</b>\n\n{lines}\n\n"
        f"➕ Qo'shish: <code>/addchannel Nomi | https://t.me/link</code>\n"
        f"🗑 O'chirish uchun pastdagi tugmani bosing."
    )
    await call.message.edit_text(text, reply_markup=channels_manage_kb(channels))


@admin_router.message(Command("addchannel"))
async def addchannel_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    raw = message.text.replace("/addchannel", "", 1).strip()
    if "|" not in raw:
        await message.answer("Foydalanish: /addchannel Nomi | https://t.me/link")
        return
    name, link = raw.split("|", 1)
    name, link = name.strip(), link.strip()
    if not name or not link:
        await message.answer("Foydalanish: /addchannel Nomi | https://t.me/link")
        return
    await add_channel(name, link)
    await message.answer(f"✅ Kanal qo'shildi: 🟢 {name} — {link}")


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
                reply_markup=quick_reply_kb(message_id)
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
    text_val = QUICK_REPLIES.get(key)
    if not text_val:
        await call.answer("Noma'lum shablon")
        return
    msg = await get_message(message_id)
    if not msg:
        await call.answer("Xabar topilmadi")
        return
    ticket = await get_ticket(msg["ticket_id"])
    if not ticket:
        await call.answer("Ticket topilmadi")
        return
    reply_msg_id = await add_message(ticket["id"], "admin", "text", text_val, None, admin_id=call.from_user.id)
    try:
        await call.bot.send_message(
            ticket["user_id"],
            "📩 Sizga javob keldi. Ko'rish uchun tugmani bosing.",
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


@admin_router.callback_query(F.data == "adm_settings")
async def adm_settings(call: CallbackQuery):
    if not is_admin(call.from_user.id):
        return await call.answer()
    enabled = await get_setting("working_hours_enabled", "1")
    start = await get_setting("working_hours_start", DEFAULT_WORKING_HOURS_START)
    end = await get_setting("working_hours_end", DEFAULT_WORKING_HOURS_END)
    status_label = "yoqilgan" if enabled == "1" else "o'chirilgan"
    text = (
        f"⚙️ <b>Sozlamalar</b>\n\n"
        f"🕐 Ish vaqti: {status_label}\n"
        f"Boshlanishi: {start}\nTugashi: {end}\n\n"
        f"O'zgartirish uchun: /sethours 09:00 18:00\n"
        f"Ish vaqtini o'chirish: /hoursoff\nYoqish: /hourson"
    )
    await call.message.edit_text(text, reply_markup=settings_kb())
    await call.answer()


@admin_router.message(Command("sethours"))
async def set_hours_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    parts = message.text.split()
    if len(parts) != 3:
        await message.answer("Foydalanish: /sethours 09:00 18:00")
        return
    await set_setting("working_hours_start", parts[1])
    await set_setting("working_hours_end", parts[2])
    await message.answer(f"✅ Ish vaqti: {parts[1]} - {parts[2]}")


@admin_router.message(Command("hoursoff"))
async def hours_off(message: Message):
    if not is_admin(message.from_user.id):
        return
    await set_setting("working_hours_enabled", "0")
    await message.answer("✅ Ish vaqti tekshiruvi o'chirildi.")


@admin_router.message(Command("hourson"))
async def hours_on(message: Message):
    if not is_admin(message.from_user.id):
        return
    await set_setting("working_hours_enabled", "1")
    await message.answer("✅ Ish vaqti tekshiruvi yoqildi.")


@admin_router.message(Command("search"))
async def search_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    query_text = message.text.replace("/search", "", 1).strip()
    if not query_text:
        await message.answer("Foydalanish: /search so'z_yoki_ism")
        return
    results = await search_tickets(query_text)
    if not results:
        await message.answer("Hech narsa topilmadi.")
        return
    lines = ["🔍 <b>Qidiruv natijalari:</b>\n"] + [ticket_summary_line(t) for t in results]
    await message.answer("\n".join(lines))


@admin_router.message(Command("topusers"))
async def top_users_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    top = await get_top_users()
    if not top:
        await message.answer("Hozircha ma'lumot yo'q.")
        return
    lines = ["🏆 <b>Eng ko'p murojaat qiluvchilar:</b>\n"]
    for i, u in enumerate(top, 1):
        username = f"@{u['username']}" if u["username"] else u["full_name"]
        lines.append(f"{i}. {username} — {u['cnt']} ta murojaat")
    await message.answer("\n".join(lines))


@admin_router.message(Command("backup"))
async def backup_cmd(message: Message):
    if not is_admin(message.from_user.id):
        return
    try:
        with open(DB_PATH, "rb") as f:
            file = BufferedInputFile(f.read(), filename="anifilm_bot_backup.db")
        await message.answer_document(file, caption="🔄 Ma'lumotlar bazasi zaxira nusxasi")
    except Exception as e:
        await message.answer(f"Xatolik: {e}")


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

    reply_kb = view_reply_kb(reply_msg_id)
    try:
        await message.bot.send_message(
            ticket["user_id"],
            "📩 Sizga javob keldi. Ko'rish uchun tugmani bosing.",
            reply_markup=reply_kb
        )
        await message.answer("✅ Javobingiz foydalanuvchiga yuborildi.")
    except Exception as e:
        await message.answer(f"❌ Yuborib bo'lmadi: {e}")


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


async def on_startup(bot: Bot):
    await init_db()
    asyncio.create_task(daily_backup_task(bot))
    asyncio.create_task(weekly_report_task(bot))
    logging.info("Baza tayyor, bot ishga tushmoqda...")


async def run_bot():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable topilmadi! Render sozlamalarida qo'shing.")

    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    dp.include_router(admin_router)
    dp.include_router(user_router)

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
