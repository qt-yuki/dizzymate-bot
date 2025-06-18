# ---------------------------------------------------
# TELEGRAM AURA BOT - SQLite3 Version
# ---------------------------------------------------

import os
import logging
import random
import asyncio
import json
import sqlite3
from datetime import datetime, date, time, timedelta
from contextlib import contextmanager

import pytz
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    BotCommand
)
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ─── Imports for Dummy HTTP Server ──────────────────────────────────────────
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Bot configuration
BOT_TOKEN = os.getenv("BOT_TOKEN", "your_bot_token_here")

# Channel and group links for /start command
UPDATES_CHANNEL = os.getenv("UPDATES_CHANNEL", "https://t.me/your_channel")
SUPPORT_GROUP = os.getenv("SUPPORT_GROUP", "https://t.me/your_support_group")
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot_username")

# Aura points configuration
AURA_POINTS = {
    'gay': -100,
    'couple': 100,
    'simp': -100,
    'toxic': -100,
    'cringe': -100,
    'respect': 500,
    'sus': -100,
    'ghost': -200,  # Special night command with higher penalty
}

# Command messages
COMMAND_MESSAGES = {
    'gay': [
        "🏳️‍🌈 Today's Gay of the Day is {user}! 🌈✨",
        "🏳️‍🌈 Congratulations {user}, you're the fabulous Gay of the Day! 💅✨",
        "🌈 {user} has been crowned the Gay of the Day! 🏳️‍🌈👑"
    ],
    'couple': [
        "💕 Today's adorable couple is {user1} and {user2}! 💑✨",
        "❤️ Love is in the air! {user1} and {user2} are today's couple! 💕🥰",
        "👫 {user1} and {user2} make the perfect couple today! 💖✨"
    ],
    'simp': [
        "🥺 {user} is today's biggest simp! 💸👑",
        "😍 Behold the ultimate simp of the day: {user}! 🥺💕",
        "👑 {user} has achieved maximum simp level today! 🥺✨"
    ],
    'toxic': [
        "☠️ {user} is spreading toxic vibes today! 🤢💀",
        "🧪 Warning: {user} is today's most toxic member! ☠️⚠️",
        "💀 {user} wins the toxic award of the day! 🧪☠️"
    ],
    'cringe': [
        "😬 {user} is today's cringe master! 🤡💀",
        "🤢 Maximum cringe level achieved by {user}! 😬🤡",
        "💀 {user} made everyone cringe today! 😬✨"
    ],
    'respect': [
        "🫡 Infinite respect for {user}! 👑✨",
        "🙏 {user} deserves all the respect today! 🫡💫",
        "👑 Mad respect for {user}! 🙏✨"
    ],
    'sus': [
        "📮 {user} is acting pretty sus today! 👀🔍",
        "🤔 {user} looking sus af! 📮👀",
        "👀 Emergency meeting! {user} is sus! 📮🚨"
    ],
    'ghost': [
        "👻 {user} is tonight's spooky ghost! 🌙💀",
        "🌙 {user} haunts the darkness tonight! 👻⚰️",
        "💀 {user} emerges from the shadows! 👻🌑"
    ]
}

# Bangladesh timezone for ghost command
BANGLADESH_TZ = 'Asia/Dhaka'

# Member data collection settings
COLLECT_MEMBERS_ON_JOIN = True
COLLECT_MEMBERS_ON_MESSAGE = True
MAX_MEMBERS_PER_BATCH = 200  # Telegram API limit

# Database file path
DATABASE_PATH = os.getenv("DATABASE_PATH", "aura_bot.db")

# ---------------------------------------------------
# DATABASE LAYER
# ---------------------------------------------------

# Thread-local storage for database connections
local_data = threading.local()

@contextmanager
def get_db_connection():
    """Get a thread-local SQLite3 connection."""
    if not hasattr(local_data, 'conn'):
        local_data.conn = sqlite3.connect(DATABASE_PATH, check_same_thread=False)
        local_data.conn.row_factory = sqlite3.Row
    
    try:
        yield local_data.conn
    except Exception as e:
        local_data.conn.rollback()
        raise e

def init_database():
    """Initialize the database with required tables."""
    with get_db_connection() as conn:
        cursor = conn.cursor()

        # Users table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                aura_points INTEGER DEFAULT 0,
                is_bot INTEGER DEFAULT 0,
                language_code TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                message_count INTEGER DEFAULT 0
            );
        """)

        # Chat members table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                status TEXT DEFAULT 'member',
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(chat_id, user_id),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        """)

        # Command usage tracking table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS command_usage (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                command TEXT,
                used_date DATE,
                last_announcement TIMESTAMP,
                UNIQUE(user_id, chat_id, command, used_date),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        """)

        # Daily selections table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_selections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                command TEXT,
                selected_user_id INTEGER,
                selected_user_id_2 INTEGER,
                selection_date DATE,
                selection_data TEXT,
                UNIQUE(chat_id, command, selection_date)
            );
        """)

        conn.commit()
        logger.info("Database initialized successfully")

def add_or_update_user(user_id, username=None, first_name=None, last_name=None, is_bot=False, language_code=None):
    """Add or update user information with enhanced data collection."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        
        # Check if user exists
        cursor.execute("SELECT aura_points, message_count FROM users WHERE user_id = ?", (user_id,))
        existing_user = cursor.fetchone()
        
        if existing_user:
            # Update existing user
            cursor.execute("""
                UPDATE users SET
                    username = ?,
                    first_name = ?,
                    last_name = ?,
                    is_bot = ?,
                    language_code = ?,
                    message_count = message_count + 1,
                    last_seen = CURRENT_TIMESTAMP
                WHERE user_id = ?
            """, (username, first_name, last_name, is_bot, language_code, user_id))
        else:
            # Insert new user
            cursor.execute("""
                INSERT INTO users (
                    user_id, username, first_name, last_name, is_bot, language_code,
                    aura_points, message_count, last_seen
                )
                VALUES (?, ?, ?, ?, ?, ?, 0, 1, CURRENT_TIMESTAMP)
            """, (user_id, username, first_name, last_name, is_bot, language_code))
        
        conn.commit()

def add_chat_member(chat_id, user_id, status='member'):
    """Add or update chat member information."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT OR REPLACE INTO chat_members (
                chat_id, user_id, status, last_active
            )
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        """, (chat_id, user_id, status))
        conn.commit()

def update_member_activity(chat_id, user_id):
    """Update member's last activity timestamp."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE chat_members
            SET last_active = CURRENT_TIMESTAMP
            WHERE chat_id = ? AND user_id = ?
        """, (chat_id, user_id))
        
        if cursor.rowcount == 0:
            add_chat_member(chat_id, user_id)
        
        conn.commit()

def update_aura_points(user_id, points):
    """Update user's aura points."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users SET aura_points = aura_points + ? WHERE user_id = ?
        """, (points, user_id))
        conn.commit()

def can_use_command(user_id, chat_id, command):
    """Check if user can use a command (daily and hourly limits)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        today = date.today().isoformat()
        cursor.execute("""
            SELECT last_announcement FROM command_usage
            WHERE user_id = ? AND chat_id = ? AND command = ? AND used_date = ?
        """, (user_id, chat_id, command, today))
        row = cursor.fetchone()
        
        if row:
            last_ann = row['last_announcement']
            if last_ann:
                last_time = datetime.fromisoformat(last_ann)
                if (datetime.now() - last_time).total_seconds() < 3600:
                    return False, 'hourly_limit'
            return False, 'daily_limit'
        return True, 'allowed'

def mark_command_used(user_id, chat_id, command):
    """Mark command usage for the day."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        today = date.today().isoformat()
        now = datetime.now().isoformat()
        cursor.execute("""
            INSERT OR REPLACE INTO command_usage (
                user_id, chat_id, command, used_date, last_announcement
            )
            VALUES (?, ?, ?, ?, ?)
        """, (user_id, chat_id, command, today, now))
        conn.commit()

def get_leaderboard(chat_id, limit=10):
    """Get aura leaderboard for a chat."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.user_id, u.username, u.first_name, u.last_name, u.aura_points
            FROM users u
            JOIN chat_members cm ON cm.user_id = u.user_id
            WHERE cm.chat_id = ? AND u.is_bot = 0
            ORDER BY u.aura_points DESC
            LIMIT ?
        """, (chat_id, limit))
        return cursor.fetchall()

def get_chat_users(chat_id):
    """Get all users in a chat."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT u.user_id, u.username, u.first_name, u.last_name
            FROM users u
            JOIN chat_members cm ON cm.user_id = u.user_id
            WHERE cm.chat_id = ? 
              AND cm.status IN ('member','administrator','creator') 
              AND u.is_bot = 0
        """, (chat_id,))
        return cursor.fetchall()

def get_active_chat_members(chat_id):
    """Get active chat members (last 30 days)."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        thirty_days_ago = (datetime.now() - timedelta(days=30)).isoformat()
        cursor.execute("""
            SELECT u.user_id, u.username, u.first_name, u.last_name
            FROM users u
            JOIN chat_members cm ON cm.user_id = u.user_id
            WHERE cm.chat_id = ? 
              AND cm.last_active >= ?
              AND cm.status IN ('member','administrator','creator')
              AND u.is_bot = 0
        """, (chat_id, thirty_days_ago))
        return cursor.fetchall()

def save_daily_selection(chat_id, command, user_id, user_id_2=None, selection_data=None):
    """Save daily selection for a command."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        today = date.today().isoformat()
        data_json = json.dumps(selection_data) if selection_data else None
        cursor.execute("""
            INSERT OR REPLACE INTO daily_selections (
                chat_id, command, selected_user_id, selected_user_id_2, selection_date, selection_data
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (chat_id, command, user_id, user_id_2, today, data_json))
        conn.commit()

def get_daily_selection(chat_id, command):
    """Get daily selection for a command."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        today = date.today().isoformat()
        cursor.execute("""
            SELECT selected_user_id, selected_user_id_2, selection_data
            FROM daily_selections
            WHERE chat_id = ? AND command = ? AND selection_date = ?
        """, (chat_id, command, today))
        row = cursor.fetchone()
        
        if row:
            return {
                'user_id': row['selected_user_id'],
                'user_id_2': row['selected_user_id_2'],
                'data': json.loads(row['selection_data']) if row['selection_data'] else None
            }
        return None

def get_chat_member_count(chat_id):
    """Get count of chat members."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM chat_members
            WHERE chat_id = ? 
              AND status IN ('member','administrator','creator')
        """, (chat_id,))
        return cursor.fetchone()['count']

def cleanup_old_data():
    """Clean up old data from database."""
    with get_db_connection() as conn:
        cursor = conn.cursor()
        seven_days_ago = (datetime.now() - timedelta(days=7)).isoformat()
        cursor.execute("""
            DELETE FROM command_usage
            WHERE last_announcement < ?
        """, (seven_days_ago,))
        conn.commit()

# ---------------------------------------------------
# MENTION HELPERS
# ---------------------------------------------------

def _build_name(first_name: str | None, last_name: str | None) -> str:
    """Return 'First' or 'First Last' – falls back to 'User' if missing."""
    if first_name:
        return f"{first_name}{f' {last_name}' if last_name else ''}"
    return "User"

def get_user_mention_html(user) -> str:
    """Clickable mention that always shows the person's name, never @username."""
    display = _build_name(user.first_name, getattr(user, 'last_name', None))
    return f'<a href="tg://user?id={user.id}">{sanitize_html(display)}</a>'

def get_user_mention_html_from_data(
    user_id: int,
    username: str | None,
    first_name: str | None,
    last_name: str | None
) -> str:
    """Clickable mention using stored data, prioritizing first/last name."""
    display = sanitize_html(_build_name(first_name, last_name))
    return f'<a href="tg://user?id={user_id}">{display}</a>'

def format_user_display_name(username: str | None, first_name: str | None, last_name: str | None) -> str:
    """Utility to format a user's display name."""
    return _build_name(first_name, last_name)

# ---------------------------------------------------
# TIME UTILS FOR GHOST COMMAND
# ---------------------------------------------------

def is_night_time_in_bangladesh() -> bool:
    """Check if it's night time in Bangladesh (6 PM to 6 AM)."""
    bd_tz = pytz.timezone(BANGLADESH_TZ)
    bd_time = datetime.now(bd_tz).time()
    night_start = time(18, 0)  # 6 PM
    night_end = time(6, 0)     # 6 AM
    return bd_time >= night_start or bd_time <= night_end

def get_time_until_night() -> tuple[int, int]:
    """Get time remaining until night time in Bangladesh."""
    bd_tz = pytz.timezone(BANGLADESH_TZ)
    bd_now = datetime.now(bd_tz)
    bd_time = bd_now.time()
    if bd_time < time(18, 0):
        next_night = bd_now.replace(hour=18, minute=0, second=0, microsecond=0)
    else:
        next_night = bd_now.replace(hour=18, minute=0, second=0, microsecond=0) + timedelta(days=1)
    time_diff = next_night - bd_now
    hours = int(time_diff.total_seconds() // 3600)
    minutes = int((time_diff.total_seconds() % 3600) // 60)
    return hours, minutes

# ---------------------------------------------------
# RANDOM USER SELECTION
# ---------------------------------------------------

def select_random_users(users, count=1, exclude=None):
    """Select random users from a list."""
    if exclude is None:
        exclude = []
    available_users = [user for user in users if user['user_id'] not in exclude]
    if len(available_users) < count:
        return available_users
    return random.sample(available_users, count)

def select_random_users_seeded(users, count=1, seed=None, exclude=None):
    """Select random users with a seed for consistent daily selection."""
    if exclude is None:
        exclude = []
    available_users = [user for user in users if user['user_id'] not in exclude]
    if len(available_users) < count:
        return available_users
    if seed:
        random.seed(seed)
    selected = random.sample(available_users, count)
    random.seed()
    return selected

# ---------------------------------------------------
# LEADERBOARD FORMATTING
# ---------------------------------------------------

def format_aura_leaderboard(leaderboard_data, chat_title=None):
    """Format aura leaderboard message."""
    if not leaderboard_data:
        return "📊 <b>Aura Leaderboard</b> 📊\n\n❌ No data available yet! Use some commands to get started! 🚀"

    title = "📊 <b>Aura Leaderboard</b>"
    if chat_title:
        title += f" - <b>{chat_title}</b>"
    title += " 📊\n\n"

    leaderboard_text = title
    medals = ["🥇", "🥈", "🥉"]

    for i, user in enumerate(leaderboard_data):
        position = i + 1
        user_mention = get_user_mention_html_from_data(
            user["user_id"], user["username"], user["first_name"], user["last_name"]
        )
        aura = user["aura_points"]
        if position <= 3:
            medal = medals[position - 1]
            leaderboard_text += f"{medal} {user_mention}: <b>{aura}</b> aura\n"
        else:
            leaderboard_text += f"🏅 {user_mention}: <b>{aura}</b> aura\n"

    leaderboard_text += "\n💡 Use commands to gain or lose aura points!"
    return leaderboard_text

# ---------------------------------------------------
# OTHER HELPERS
# ---------------------------------------------------

def extract_user_info(user):
    """Extract user information from Telegram user object."""
    return {
        'user_id': user.id,
        'username': user.username,
        'first_name': user.first_name,
        'last_name': getattr(user, 'last_name', None),
        'is_bot': user.is_bot,
        'language_code': user.language_code
    }

def sanitize_html(text: str) -> str:
    """Sanitize HTML text."""
    import html
    return html.escape(text)

# ---------------------------------------------------
# HANDLER FUNCTIONS
# ---------------------------------------------------

async def typing_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send typing action before responding."""
    if update.effective_chat:
        await context.bot.send_chat_action(
            chat_id=update.effective_chat.id,
            action=ChatAction.TYPING
        )

async def collect_group_members(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Collect group members data when possible."""
    if not update.effective_chat or update.effective_chat.type in ['private']:
        return
    
    chat_id = update.effective_chat.id
    
    try:
        # Try to get chat member count
        member_count = await context.bot.get_chat_member_count(chat_id)
        logger.info(f"Chat {chat_id} has {member_count} members")
    except Exception as e:
        logger.warning(f"Could not get member count for chat {chat_id}: {e}")

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle new chat members."""
    if not update.message or not update.message.new_chat_members:
        return
    
    chat_id = update.effective_chat.id
    
    for new_member in update.message.new_chat_members:
        if not new_member.is_bot:
            user_info = extract_user_info(new_member)
            add_or_update_user(**user_info)
            add_chat_member(chat_id, new_member.id, 'member')
            logger.info(f"New member {new_member.first_name} joined chat {chat_id}")

async def handle_member_left(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle member leaving chat."""
    if not update.message or not update.message.left_chat_member:
        return
    
    chat_id = update.effective_chat.id
    left_member = update.message.left_chat_member
    
    if not left_member.is_bot:
        add_chat_member(chat_id, left_member.id, 'left')
        logger.info(f"Member {left_member.first_name} left chat {chat_id}")

async def track_message_activity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Track user message activity for better member data collection."""
    if not update.effective_user or not update.effective_chat:
        return
    
    if update.effective_chat.type in ['private']:
        return
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    if not user.is_bot:
        user_info = extract_user_info(user)
        add_or_update_user(**user_info)
        update_member_activity(chat_id, user.id)

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /start command."""
    user = update.effective_user
    if not user:
        return

    await typing_action(update, context)

    # Add user to database
    user_info = extract_user_info(user)
    add_or_update_user(**user_info)

    start_message = f"""
🎉 <b>Welcome to Aura Bot!</b> 🎉

Hello {get_user_mention_html(user)}! 👋

🌟 <b>What can I do?</b>
• Use fun commands to assign daily titles  
• Track aura points for group activities  
• Show leaderboards and statistics

🎮 <b>Available Commands:</b>  
/gay - Find today's Gay of the Day 🏳️‍🌈  
/couple - Discover today's perfect couple 💕  
/simp - Crown the biggest simp 🥺  
/toxic - Identify the toxic member ☠️  
/cringe - Find the cringe master 😬  
/respect - Show ultimate respect 🫡  
/sus - Spot suspicious behavior 📮  
/ghost - Nighttime spooky selection 👻  
/aura - View the aura leaderboard 📊

💫 <b>How it works:</b>  
Commands can only be used once per day per user in each group.  
Some commands give positive aura points, others negative!

Have fun and may your aura be strong! ✨
    """

    keyboard = [
        [
            InlineKeyboardButton("Updates", url=UPDATES_CHANNEL),
            InlineKeyboardButton("Support", url=SUPPORT_GROUP)
        ],
        [
            InlineKeyboardButton("Add Me To Your Group", url=f"https://t.me/{BOT_USERNAME}?startgroup=true")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text(
        start_message,
        parse_mode=ParseMode.HTML,
        reply_markup=reply_markup
    )

async def gay_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /gay command."""
    await handle_single_user_command(update, context, 'gay')

async def couple_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /couple command."""
    await handle_couple_command(update, context)

async def simp_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /simp command."""
    await handle_single_user_command(update, context, 'simp')

async def toxic_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /toxic command."""
    await handle_single_user_command(update, context, 'toxic')

async def cringe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /cringe command."""
    await handle_single_user_command(update, context, 'cringe')

async def respect_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /respect command."""
    await handle_single_user_command(update, context, 'respect')

async def sus_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sus command."""
    await handle_single_user_command(update, context, 'sus')

async def handle_single_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE, command: str):
    """Handle commands that select a single user."""
    if not update.effective_user or not update.effective_chat:
        return
    
    # Only work in groups
    if update.effective_chat.type == 'private':
        await update.message.reply_text(
            "❌ This command only works in groups! Add me to a group to use aura commands."
        )
        return
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    user_id = user.id
    
    await typing_action(update, context)
    
    # Add user to database
    user_info = extract_user_info(user)
    add_or_update_user(**user_info)
    update_member_activity(chat_id, user_id)
    
    # Check if user can use command
    can_use, reason = can_use_command(user_id, chat_id, command)
    
    if not can_use:
        if reason == 'hourly_limit':
            await update.message.reply_text(
                f"⏰ Hold up! You need to wait an hour before using /{command} again!"
            )
        else:
            await update.message.reply_text(
                f"⏰ You've already used /{command} today! Come back tomorrow for a new selection!"
            )
        return
    
    # Check if we already have today's selection
    existing_selection = get_daily_selection(chat_id, command)
    if existing_selection:
        # Get user data for the existing selection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT username, first_name, last_name
                FROM users WHERE user_id = ?
            """, (existing_selection['user_id'],))
            selected_user_data = cursor.fetchone()
        
        if selected_user_data:
            selected_user_mention = get_user_mention_html_from_data(
                existing_selection['user_id'],
                selected_user_data['username'],
                selected_user_data['first_name'],
                selected_user_data['last_name']
            )
            
            # Choose random message
            message_template = random.choice(COMMAND_MESSAGES[command])
            final_message = message_template.format(user=selected_user_mention)
            
            await update.message.reply_text(final_message, parse_mode=ParseMode.HTML)
            mark_command_used(user_id, chat_id, command)
            return
    
    # Get active chat members
    active_members = get_active_chat_members(chat_id)
    
    if len(active_members) < 1:
        await update.message.reply_text(
            "❌ Not enough active members in this chat to use this command!"
        )
        return
    
    # Select random user using seeded selection for consistency
    seed = f"{chat_id}_{command}_{date.today().isoformat()}"
    selected_users = select_random_users_seeded(active_members, 1, seed)
    
    if not selected_users:
        await update.message.reply_text(
            "❌ Could not select a user. Try again later!"
        )
        return
    
    selected_user = selected_users[0]
    
    # Save selection
    save_daily_selection(chat_id, command, selected_user['user_id'])
    
    # Update aura points
    aura_change = AURA_POINTS[command]
    update_aura_points(selected_user['user_id'], aura_change)
    
    # Create mention
    selected_user_mention = get_user_mention_html_from_data(
        selected_user['user_id'],
        selected_user['username'],
        selected_user['first_name'],
        selected_user['last_name']
    )
    
    # Choose random message and send
    message_template = random.choice(COMMAND_MESSAGES[command])
    final_message = message_template.format(user=selected_user_mention)
    
    # Add aura change info
    if aura_change > 0:
        final_message += f"\n\n✨ <b>+{aura_change} aura points!</b>"
    else:
        final_message += f"\n\n💔 <b>{aura_change} aura points!</b>"
    
    await update.message.reply_text(final_message, parse_mode=ParseMode.HTML)
    mark_command_used(user_id, chat_id, command)

async def handle_couple_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /couple command specifically."""
    if not update.effective_user or not update.effective_chat:
        return
    
    # Only work in groups
    if update.effective_chat.type == 'private':
        await update.message.reply_text(
            "❌ This command only works in groups! Add me to a group to use aura commands."
        )
        return
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    user_id = user.id
    command = 'couple'
    
    await typing_action(update, context)
    
    # Add user to database
    user_info = extract_user_info(user)
    add_or_update_user(**user_info)
    update_member_activity(chat_id, user_id)
    
    # Check if user can use command
    can_use, reason = can_use_command(user_id, chat_id, command)
    
    if not can_use:
        if reason == 'hourly_limit':
            await update.message.reply_text(
                f"⏰ Hold up! You need to wait an hour before using /{command} again!"
            )
        else:
            await update.message.reply_text(
                f"⏰ You've already used /{command} today! Come back tomorrow for a new selection!"
            )
        return
    
    # Check if we already have today's selection
    existing_selection = get_daily_selection(chat_id, command)
    if existing_selection:
        # Get user data for both users
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT username, first_name, last_name
                FROM users WHERE user_id = ?
            """, (existing_selection['user_id'],))
            user1_data = cursor.fetchone()
            
            cursor.execute("""
                SELECT username, first_name, last_name
                FROM users WHERE user_id = ?
            """, (existing_selection['user_id_2'],))
            user2_data = cursor.fetchone()
        
        if user1_data and user2_data:
            user1_mention = get_user_mention_html_from_data(
                existing_selection['user_id'],
                user1_data['username'],
                user1_data['first_name'],
                user1_data['last_name']
            )
            user2_mention = get_user_mention_html_from_data(
                existing_selection['user_id_2'],
                user2_data['username'],
                user2_data['first_name'],
                user2_data['last_name']
            )
            
            # Choose random message
            message_template = random.choice(COMMAND_MESSAGES[command])
            final_message = message_template.format(user1=user1_mention, user2=user2_mention)
            
            await update.message.reply_text(final_message, parse_mode=ParseMode.HTML)
            mark_command_used(user_id, chat_id, command)
            return
    
    # Get active chat members
    active_members = get_active_chat_members(chat_id)
    
    if len(active_members) < 2:
        await update.message.reply_text(
            "❌ Not enough active members in this chat to form a couple!"
        )
        return
    
    # Select 2 random users using seeded selection for consistency
    seed = f"{chat_id}_{command}_{date.today().isoformat()}"
    selected_users = select_random_users_seeded(active_members, 2, seed)
    
    if len(selected_users) < 2:
        await update.message.reply_text(
            "❌ Could not select a couple. Try again later!"
        )
        return
    
    user1, user2 = selected_users
    
    # Save selection
    save_daily_selection(chat_id, command, user1['user_id'], user2['user_id'])
    
    # Update aura points for both users
    aura_change = AURA_POINTS[command]
    update_aura_points(user1['user_id'], aura_change)
    update_aura_points(user2['user_id'], aura_change)
    
    # Create mentions
    user1_mention = get_user_mention_html_from_data(
        user1['user_id'], user1['username'], user1['first_name'], user1['last_name']
    )
    user2_mention = get_user_mention_html_from_data(
        user2['user_id'], user2['username'], user2['first_name'], user2['last_name']
    )
    
    # Choose random message and send
    message_template = random.choice(COMMAND_MESSAGES[command])
    final_message = message_template.format(user1=user1_mention, user2=user2_mention)
    
    # Add aura change info
    final_message += f"\n\n✨ <b>Both get +{aura_change} aura points!</b>"
    
    await update.message.reply_text(final_message, parse_mode=ParseMode.HTML)
    mark_command_used(user_id, chat_id, command)

async def ghost_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /ghost command - only works at night in Bangladesh time."""
    if not update.effective_user or not update.effective_chat:
        return
    
    # Only work in groups
    if update.effective_chat.type == 'private':
        await update.message.reply_text(
            "❌ This command only works in groups! Add me to a group to use aura commands."
        )
        return
    
    user = update.effective_user
    chat_id = update.effective_chat.id
    user_id = user.id
    command = 'ghost'
    
    await typing_action(update, context)
    
    # Check if it's night time in Bangladesh
    if not is_night_time_in_bangladesh():
        hours, minutes = get_time_until_night()
        await update.message.reply_text(
            f"🌅 The ghost command only works during night time in Bangladesh (6 PM - 6 AM)!\n"
            f"⏰ Come back in {hours}h {minutes}m when the darkness falls... 👻"
        )
        return
    
    # Add user to database
    user_info = extract_user_info(user)
    add_or_update_user(**user_info)
    update_member_activity(chat_id, user_id)
    
    # Check if user can use command
    can_use, reason = can_use_command(user_id, chat_id, command)
    
    if not can_use:
        if reason == 'hourly_limit':
            await update.message.reply_text(
                f"⏰ The spirits need time to rest! Wait an hour before summoning again..."
            )
        else:
            await update.message.reply_text(
                f"👻 You've already summoned a ghost today! The spirits will return tomorrow..."
            )
        return
    
    # Check if we already have today's selection
    existing_selection = get_daily_selection(chat_id, command)
    if existing_selection:
        # Get user data for the existing selection
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT username, first_name, last_name
                FROM users WHERE user_id = ?
            """, (existing_selection['user_id'],))
            selected_user_data = cursor.fetchone()
        
        if selected_user_data:
            selected_user_mention = get_user_mention_html_from_data(
                existing_selection['user_id'],
                selected_user_data['username'],
                selected_user_data['first_name'],
                selected_user_data['last_name']
            )
            
            # Choose random message
            message_template = random.choice(COMMAND_MESSAGES[command])
            final_message = message_template.format(user=selected_user_mention)
            
            await update.message.reply_text(final_message, parse_mode=ParseMode.HTML)
            mark_command_used(user_id, chat_id, command)
            return
    
    # Get active chat members
    active_members = get_active_chat_members(chat_id)
    
    if len(active_members) < 1:
        await update.message.reply_text(
            "❌ Not enough active members in this chat for the spirits to haunt!"
        )
        return
    
    # Select random user using seeded selection for consistency
    seed = f"{chat_id}_{command}_{date.today().isoformat()}"
    selected_users = select_random_users_seeded(active_members, 1, seed)
    
    if not selected_users:
        await update.message.reply_text(
            "❌ The spirits couldn't find anyone to haunt. Try again later!"
        )
        return
    
    selected_user = selected_users[0]
    
    # Save selection
    save_daily_selection(chat_id, command, selected_user['user_id'])
    
    # Update aura points
    aura_change = AURA_POINTS[command]
    update_aura_points(selected_user['user_id'], aura_change)
    
    # Create mention
    selected_user_mention = get_user_mention_html_from_data(
        selected_user['user_id'],
        selected_user['username'],
        selected_user['first_name'],
        selected_user['last_name']
    )
    
    # Choose random message and send
    message_template = random.choice(COMMAND_MESSAGES[command])
    final_message = message_template.format(user=selected_user_mention)
    
    # Add aura change info
    final_message += f"\n\n💀 <b>{aura_change} aura points! The spirits are not pleased...</b>"
    
    await update.message.reply_text(final_message, parse_mode=ParseMode.HTML)
    mark_command_used(user_id, chat_id, command)

async def aura_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /aura command - show leaderboard."""
    if not update.effective_chat:
        return
    
    # Only work in groups
    if update.effective_chat.type == 'private':
        await update.message.reply_text(
            "❌ Aura leaderboard only works in groups! Add me to a group to see rankings."
        )
        return
    
    chat_id = update.effective_chat.id
    
    await typing_action(update, context)
    
    # Get leaderboard
    leaderboard_data = get_leaderboard(chat_id, 10)
    
    # Get chat title if available
    chat_title = getattr(update.effective_chat, 'title', None)
    
    # Format and send leaderboard
    leaderboard_message = format_aura_leaderboard(leaderboard_data, chat_title)
    
    await update.message.reply_text(
        leaderboard_message,
        parse_mode=ParseMode.HTML
    )

async def cleanup_expired_data(context: ContextTypes.DEFAULT_TYPE):
    """Cleanup expired data - runs periodically."""
    try:
        cleanup_old_data()
        logger.info("Database cleanup completed")
    except Exception as e:
        logger.error(f"Database cleanup failed: {e}")

def setup_periodic_jobs(application):
    """Setup periodic background jobs."""
    try:
        job_queue = application.job_queue
        if job_queue:
            # Run database cleanup every 24 hours
            job_queue.run_repeating(
                cleanup_expired_data,
                interval=timedelta(hours=24),
                first=timedelta(minutes=1)
            )
            logger.info("Periodic jobs setup successfully")
        else:
            logger.warning("JobQueue not available. Periodic cleanup disabled.")
    except Exception as e:
        logger.warning(f"Could not setup periodic jobs: {e}")

async def on_startup(application: Application) -> None:
    """
    Run once when the bot starts. Registers commands in Telegram's "/" menu.
    """
    commands = [
        BotCommand("start", "Get started with Aura Bot"),
        BotCommand("gay", "Find today's Gay of the Day"),
        BotCommand("couple", "Discover today's perfect couple"),
        BotCommand("simp", "Crown the biggest simp"),
        BotCommand("toxic", "Identify the toxic member"),
        BotCommand("cringe", "Find the cringe master"),
        BotCommand("respect", "Show ultimate respect"),
        BotCommand("sus", "Spot suspicious behavior"),
        BotCommand("ghost", "Nighttime spooky selection"),
        BotCommand("aura", "View the aura leaderboard"),
    ]
    
    await application.bot.set_my_commands(commands)
    logger.info("Bot commands registered successfully")

 # ─── Dummy HTTP Server to Keep Render Happy ─────────────────────────────────
class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"AFK bot is alive!")

    def do_HEAD(self):
        self.send_response(200)
        self.end_headers()

def start_dummy_server():
    port = int(os.environ.get("PORT", 10000))  # Render injects this
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    print(f"Dummy server listening on port {port}")
    server.serve_forever()

def main():
    """Start the bot."""
    # Initialize database
    init_database()
    
    # Create application
    application = Application.builder().token(BOT_TOKEN).build()
    
    # Add handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("gay", gay_command))
    application.add_handler(CommandHandler("couple", couple_command))
    application.add_handler(CommandHandler("simp", simp_command))
    application.add_handler(CommandHandler("toxic", toxic_command))
    application.add_handler(CommandHandler("cringe", cringe_command))
    application.add_handler(CommandHandler("respect", respect_command))
    application.add_handler(CommandHandler("sus", sus_command))
    application.add_handler(CommandHandler("ghost", ghost_command))
    application.add_handler(CommandHandler("aura", aura_command))
    
    # Add member tracking handlers
    application.add_handler(MessageHandler(
        filters.StatusUpdate.NEW_CHAT_MEMBERS, 
        handle_new_member
    ))
    application.add_handler(MessageHandler(
        filters.StatusUpdate.LEFT_CHAT_MEMBER, 
        handle_member_left
    ))
    
    # Track all messages for activity
    application.add_handler(MessageHandler(
        filters.ALL & ~filters.COMMAND,
        track_message_activity
    ))
    
    # Setup periodic jobs
    setup_periodic_jobs(application)
    
    # Register startup hook
    application.post_init = on_startup
    
    # Start the bot
    logger.info("Starting Telegram Aura Bot...")
    application.run_polling(drop_pending_updates=True)

if __name__ == '__main__':
    # Start dummy HTTP server (needed for Render health check)
    threading.Thread(target=start_dummy_server, daemon=True).start()
    main()