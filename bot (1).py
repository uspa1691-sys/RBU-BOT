import os
import sqlite3
import threading
from datetime import datetime
from flask import Flask, request, jsonify
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# =========================================================
# SOZLAMALAR
# =========================================================

# Token endi kodda emas — Fly.io secrets orqali beriladi
BOT_TOKEN = "7873626779:AAFs4bJjzd-7d3JiLP9D7vhARmi-w2KQ7WY"

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN topilmadi! "
        "Fly.io'da: fly secrets set BOT_TOKEN=... "
        "Local'da: export BOT_TOKEN=... yoki .env fayl"
    )

ADMIN_ID = int(os.environ.get("ADMIN_ID", "8537782289"))

# Kanal/guruhlarni shu yerga qo'shasiz
CHANNELS = [
    {
        "id": 1,
        "title": "RBU Official Channel",
        "username": "@YOUR_CHANNEL",
        "link": "https://t.me/YOUR_CHANNEL",
        "reward": 350
    },

    # Yangi kanal misoli:
    # {
    #     "id": 2,
    #     "title": "Gaming Channel",
    #     "username": "@gamingchannel",
    #     "link": "https://t.me/gamingchannel",
    #     "reward": 350
    # }
]

# Fly.io'da doimiy saqlash uchun /data volume ishlatiladi
DB = os.environ.get("DB_PATH", "rbu.db")

app = Flask(__name__)


# =========================================================
# DATABASE
# =========================================================

def db():
    return sqlite3.connect(DB)


def init_db():
    con = db()
    cur = con.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        telegram_id INTEGER PRIMARY KEY,
        username TEXT,
        first_name TEXT,
        balance INTEGER DEFAULT 0,
        earned INTEGER DEFAULT 0,
        spent INTEGER DEFAULT 0,
        games INTEGER DEFAULT 0,
        visits INTEGER DEFAULT 0,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS visits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        ip TEXT,
        user_agent TEXT,
        created_at TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS bonuses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        channel_id INTEGER,
        amount INTEGER,
        created_at TEXT,
        UNIQUE(telegram_id, channel_id)
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        telegram_id INTEGER,
        username TEXT,
        player_id TEXT,
        nickname TEXT,
        uc INTEGER,
        cost INTEGER,
        status TEXT DEFAULT 'PENDING',
        created_at TEXT
    )
    """)

    con.commit()
    con.close()


# =========================================================
# USER
# =========================================================

def save_user(user):
    con = db()
    cur = con.cursor()

    cur.execute("""
    INSERT OR IGNORE INTO users
    (telegram_id, username, first_name, created_at)
    VALUES (?, ?, ?, ?)
    """, (
        user.id,
        user.username or "",
        user.first_name or "",
        datetime.now().isoformat()
    ))

    cur.execute("""
    UPDATE users
    SET username=?, first_name=?
    WHERE telegram_id=?
    """, (
        user.username or "",
        user.first_name or "",
        user.id
    ))

    con.commit()
    con.close()


# =========================================================
# TELEGRAM /START
# =========================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):

    user = update.effective_user
    save_user(user)

    text = (
        "🎮 RBU GAMING\n\n"
        "RBU Gaming botiga xush kelibsiz!\n\n"
        "Quyidagi tugmalar orqali foydalaning:"
    )

    keyboard = [
        [
            InlineKeyboardButton(
                "🌐 RBU Gaming",
                web_app=WebAppInfo(
                    url="https://rayhonasodiqova839-dev.github.io/menyu-bot/"
                )
            )
        ],
        [
            InlineKeyboardButton(
                "📢 Kanallarga obuna",
                callback_data="channels"
            )
        ]
    ]

    await update.message.reply_text(
        text,
        reply_markup=InlineKeyboardMarkup(keyboard)
    )


# =========================================================
# KANALLAR
# =========================================================

async def show_channels(update: Update, context: ContextTypes.DEFAULT_TYPE):

    query = update.callback_query
    await query.answer()

    buttons = []

    for channel in CHANNELS:

        buttons.append([
            InlineKeyboardButton(
                f"📢 {channel['title']}",
                url=channel["link"]
            )
        ])

        buttons.append([
            InlineKeyboardButton(
                "✅ Obunani tekshirish",
                callback_data=f"check:{channel['id']}"
            )
        ])

    await query.message.reply_text(
        "📢 Kanallarga obuna bo'ling.\n\n"
        "Obuna bo'lgandan keyin "
        "«Obunani tekshirish» tugmasini bosing.",
        reply_markup=InlineKeyboardMarkup(buttons)
    )


# =========================================================
# OBUNANI TEKSHIRISH
# =========================================================

async def check_subscription(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query
    await query.answer()

    user = query.from_user

    try:
        channel_id = int(query.data.split(":")[1])
    except Exception:
        return

    channel = None

    for c in CHANNELS:
        if c["id"] == channel_id:
            channel = c
            break

    if not channel:
        await query.message.reply_text(
            "❌ Kanal topilmadi."
        )
        return

    try:

        member = await context.bot.get_chat_member(
            chat_id=channel["username"],
            user_id=user.id
        )

        status = member.status

        subscribed = status in [
            "member",
            "administrator",
            "creator"
        ]

        if not subscribed:

            await query.message.reply_text(
                "❌ Siz hali kanalga obuna bo'lmagansiz.\n\n"
                "Avval kanalga qo'shiling va qaytadan tekshiring."
            )

            return

    except Exception:

        await query.message.reply_text(
            "⚠️ Obunani tekshirishda xatolik.\n\n"
            "Bot kanalga administrator qilib qo'yilganini "
            "tekshiring."
        )

        return

    # =====================================================
    # BONUS ALLAQACHON OLINGANMI?
    # =====================================================

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT id
    FROM bonuses
    WHERE telegram_id=? AND channel_id=?
    """, (
        user.id,
        channel_id
    ))

    exists = cur.fetchone()

    if exists:

        con.close()

        await query.message.reply_text(
            "ℹ️ Bu kanal uchun bonusni avval olgansiz."
        )

        return

    reward = channel["reward"]

    # BONUS
    cur.execute("""
    INSERT INTO bonuses
    (telegram_id, channel_id, amount, created_at)
    VALUES (?, ?, ?, ?)
    """, (
        user.id,
        channel_id,
        reward,
        datetime.now().isoformat()
    ))

    cur.execute("""
    UPDATE users
    SET balance=balance+?,
        earned=earned+?
    WHERE telegram_id=?
    """, (
        reward,
        reward,
        user.id
    ))

    con.commit()
    con.close()

    await query.message.reply_text(
        f"✅ Obuna tasdiqlandi!\n\n"
        f"🎁 Bonus: +{reward:,} RBU\n\n"
        f"💠 RBU balansingiz oshirildi."
    )


# =========================================================
# CALLBACK
# =========================================================

async def callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    query = update.callback_query

    if query.data == "channels":

        await show_channels(update, context)

    elif query.data.startswith("check:"):

        await check_subscription(update, context)


# =========================================================
# ADMIN STATISTIKA
# =========================================================

def get_stats():

    con = db()
    cur = con.cursor()

    cur.execute("SELECT COUNT(*) FROM users")
    users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM visits")
    visits = cur.fetchone()[0]

    today = datetime.now().strftime("%Y-%m-%d")

    cur.execute("""
    SELECT COUNT(*)
    FROM visits
    WHERE created_at LIKE ?
    """, (today + "%",))

    today_visits = cur.fetchone()[0]

    cur.execute("""
    SELECT COALESCE(SUM(amount),0)
    FROM bonuses
    """)

    bonus_total = cur.fetchone()[0]

    cur.execute("""
    SELECT COUNT(*)
    FROM bonuses
    """)

    bonus_count = cur.fetchone()[0]

    cur.execute("""
    SELECT COUNT(*)
    FROM orders
    WHERE status='PENDING'
    """)

    pending = cur.fetchone()[0]

    cur.execute("""
    SELECT COUNT(*)
    FROM orders
    WHERE status='COMPLETED'
    """)

    completed = cur.fetchone()[0]

    con.close()

    return (
        users,
        visits,
        today_visits,
        bonus_total,
        bonus_count,
        pending,
        completed
    )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):

    if update.effective_user.id != ADMIN_ID:

        await update.message.reply_text(
            "⛔ Siz admin emassiz."
        )

        return

    (
        users,
        visits,
        today_visits,
        bonus_total,
        bonus_count,
        pending,
        completed
    ) = get_stats()

    text = f"""
📊 RBU GAMING ADMIN

👥 Jami foydalanuvchilar:
{users:,}

🌐 Jami sayt tashriflari:
{visits:,}

🟢 Bugungi tashriflar:
{today_visits:,}

🎁 Berilgan bonuslar:
{bonus_count:,}

💰 Tarqatilgan bonus:
{bonus_total:,} RBU

🎁 UC ZAKAZLAR

⏳ Pending:
{pending:,}

✅ Completed:
{completed:,}
"""

    await update.message.reply_text(text)


# =========================================================
# ADMIN USERS
# =========================================================

async def users_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if update.effective_user.id != ADMIN_ID:
        return

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT telegram_id, username, balance, earned, games
    FROM users
    ORDER BY created_at DESC
    LIMIT 20
    """)

    rows = cur.fetchall()

    con.close()

    text = "👥 SO'NGGI FOYDALANUVCHILAR\n\n"

    for row in rows:

        tid, username, balance, earned, games = row

        text += (
            f"👤 @{username or 'username yo‘q'}\n"
            f"🆔 {tid}\n"
            f"💰 {balance:,} RBU\n"
            f"🎮 Games: {games}\n\n"
        )

    await update.message.reply_text(text)


# =========================================================
# WEBSITE VISIT API
# =========================================================

@app.route("/api/visit", methods=["POST"])
def visit():

    data = request.get_json(silent=True) or {}

    telegram_id = data.get("telegram_id")

    ip = request.headers.get("X-Forwarded-For")

    if not ip:
        ip = request.remote_addr

    user_agent = request.headers.get(
        "User-Agent",
        ""
    )

    con = db()
    cur = con.cursor()

    cur.execute("""
    INSERT INTO visits
    (telegram_id, ip, user_agent, created_at)
    VALUES (?, ?, ?, ?)
    """, (
        telegram_id,
        ip,
        user_agent,
        datetime.now().isoformat()
    ))

    if telegram_id:

        cur.execute("""
        UPDATE users
        SET visits=visits+1
        WHERE telegram_id=?
        """, (telegram_id,))

    con.commit()
    con.close()

    return jsonify({
        "success": True
    })


# =========================================================
# WEBSITE ORDER API
# =========================================================

@app.route("/api/order", methods=["POST"])
def create_order():

    data = request.get_json(silent=True) or {}

    telegram_id = data.get("telegram_id")
    username = data.get("username", "")
    player_id = data.get("player_id", "")
    nickname = data.get("nickname", "")
    uc = int(data.get("uc", 0))
    cost = int(data.get("cost", 0))

    if not telegram_id:
        return jsonify({
            "success": False,
            "error": "telegram_id kerak"
        }), 400

    if not player_id or not nickname:
        return jsonify({
            "success": False,
            "error": "Player ID va nickname kerak"
        }), 400

    con = db()
    cur = con.cursor()

    cur.execute("""
    SELECT balance
    FROM users
    WHERE telegram_id=?
    """, (telegram_id,))

    row = cur.fetchone()

    if not row:
        con.close()

        return jsonify({
            "success": False,
            "error": "User topilmadi"
        }), 404

    balance = row[0]

    if balance < cost:
        con.close()

        return jsonify({
            "success": False,
            "error": "Balans yetarli emas"
        }), 400

    cur.execute("""
    UPDATE users
    SET balance=balance-?,
        spent=spent+?
    WHERE telegram_id=?
    """, (
        cost,
        cost,
        telegram_id
    ))

    cur.execute("""
    INSERT INTO orders
    (telegram_id, username, player_id, nickname, uc, cost, status, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?)
    """, (
        telegram_id,
        username,
        player_id,
        nickname,
        uc,
        cost,
        datetime.now().isoformat()
    ))

    order_id = cur.lastrowid

    con.commit()
    con.close()

    return jsonify({
        "success": True,
        "order_id": order_id,
        "status": "PENDING"
    })


# =========================================================
# SERVER
# =========================================================

def run_server():

    port = int(os.environ.get("PORT", "8080"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False,
        use_reloader=False
    )


# =========================================================
# BOT
# =========================================================

async def post_init(application):

    print("RBU BOT ISHGA TUSHDI")


def main():

    init_db()

    server_thread = threading.Thread(
        target=run_server,
        daemon=True
    )

    server_thread.start()

    application = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("admin", admin)
    )

    application.add_handler(
        CommandHandler("users", users_command)
    )

    application.add_handler(
        CallbackQueryHandler(callback_handler)
    )

    print("Bot ishga tushmoqda...")

    application.run_polling()


if __name__ == "__main__":
    main()
