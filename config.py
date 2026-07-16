import os

# Bot tokeni (Render'da Environment Variable sifatida BOT_TOKEN nomi bilan qo'yiladi)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Admin(lar) ID raqamlari, vergul bilan ajratilgan bo'lishi mumkin: "5383321037,111111111"
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "5383321037").split(",") if x.strip()]

# Render avtomatik beradigan port
PORT = int(os.getenv("PORT", "10000"))

# Ma'lumotlar bazasi fayli
DB_PATH = os.getenv("DB_PATH", "bot.db")

# Kategoriyalar
CATEGORIES = {
    "taklif": "💡 Taklif",
    "murojaat": "❓ Murojaat",
    "reklama": "📢 Reklama",
}

# Rasmiy kanallar ro'yxati (kerak bo'lsa shu yerdan o'zgartirasiz)
OFFICIAL_CHANNELS = [
    ("Anifilm.uz kanali", "https://t.me/anifilm_uz"),
]

# Flood control: shu vaqt ichida nechta xabar yuborish mumkin
FLOOD_LIMIT_MESSAGES = 5
FLOOD_LIMIT_SECONDS = 60

# Bir xil xabarni qayta yuborishni bloklash oralig'i (soniya)
DUPLICATE_WINDOW_SECONDS = 30

# Oddiy savollarga avtomatik javoblar (kalit so'z: javob)
FAQ_ANSWERS = {
    "ish vaqt": "🕐 Biz har kuni 09:00 dan 18:00 gacha ishlaymiz. Ushbu vaqtdan tashqarida yozgan xabarlaringizga ish vaqti boshlanishi bilan javob beramiz.",
    "qachon javob": "⏳ Odatda xabarlarga bir necha soat ichida javob beramiz. Iltimos, biroz kuting.",
    "reklama narx": "📢 Reklama narxlari va shartlari haqida to'liq ma'lumot uchun 'Reklama' bo'limi orqali murojaat qiling, admin siz bilan bog'lanadi.",
    "kanal manzil": "📢 Rasmiy kanallarimiz ro'yxatini /start menyusidagi '📢 Rasmiy kanallarimiz' tugmasidan ko'rishingiz mumkin.",
}

# Taqiqlangan so'zlar (kichik harflarda, kerak bo'lsa qo'shing)
BANNED_WORDS = []

# Ish vaqti sozlamalari (standart)
DEFAULT_WORKING_HOURS_ENABLED = True
DEFAULT_WORKING_HOURS_START = "09:00"
DEFAULT_WORKING_HOURS_END = "18:00"
