# -*- coding: utf-8 -*-
"""802 BOT — Rubika Bot API / token mode only."""
import asyncio
import logging
import re
import sqlite3
import time
import unicodedata
from collections import defaultdict, deque
from pathlib import Path

from rubpy import BotClient

# توکن و شناسه مالک را فقط در همین فایل تنظیم کن.
BOT_TOKEN = "PASTE_RUBIKA_BOT_TOKEN_HERE"
OWNER_ID = "PASTE_OWNER_USER_ID_HERE"

# اختیاری: برای پاسخ هوشمند، کلید API را وارد کن.
OPENAI_API_KEY = ""
AI_MODEL = "gpt-4o-mini"
AI_GROUP_ENABLED = True

DATA_DIR = Path("data")
DB_PATH = DATA_DIR / "802.sqlite3"
SCIENCE_FILE = Path("resources/science.pdf")
MATH_FILE = Path("resources/math.pdf")
TEMP_MUTE_SECONDS = 10 * 60
SPAM_WINDOW_SECONDS = 30
SPAM_LIMIT = 5

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(name)s | %(message)s")
log = logging.getLogger("802")
DATA_DIR.mkdir(parents=True, exist_ok=True)

if BOT_TOKEN == "PASTE_RUBIKA_BOT_TOKEN_HERE" or not BOT_TOKEN.strip():
    raise RuntimeError("توکن ربات را در ابتدای main.py وارد کن.")
if OWNER_ID == "PASTE_OWNER_USER_ID_HERE" or not OWNER_ID.strip():
    raise RuntimeError("شناسه مالک را در OWNER_ID ابتدای main.py وارد کن.")

bot = BotClient(token=BOT_TOKEN, rate_limit=0.5, parse_mode=None)


class Store:
    def __init__(self, path):
        self.db = sqlite3.connect(path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.lock = asyncio.Lock()
        self.db.executescript("""
        CREATE TABLE IF NOT EXISTS groups(chat_id TEXT PRIMARY KEY, active INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS mutes(chat_id TEXT NOT NULL,user_id TEXT NOT NULL,until_ts REAL NOT NULL DEFAULT 0,reason TEXT NOT NULL,PRIMARY KEY(chat_id,user_id));
        CREATE TABLE IF NOT EXISTS warnings(chat_id TEXT NOT NULL,user_id TEXT NOT NULL,count INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(chat_id,user_id));
        """)
        self.db.commit()

    async def active(self, chat):
        row = self.db.execute("SELECT active FROM groups WHERE chat_id=?", (str(chat),)).fetchone()
        return bool(row and row["active"])

    async def set_active(self, chat):
        async with self.lock:
            self.db.execute("INSERT INTO groups(chat_id,active) VALUES(?,1) ON CONFLICT(chat_id) DO UPDATE SET active=1", (str(chat),))
            self.db.commit()

    async def mute(self, chat, user, seconds, reason):
        until = 0 if seconds <= 0 else time.time() + seconds
        async with self.lock:
            self.db.execute("INSERT INTO mutes(chat_id,user_id,until_ts,reason) VALUES(?,?,?,?) ON CONFLICT(chat_id,user_id) DO UPDATE SET until_ts=excluded.until_ts,reason=excluded.reason",
                            (str(chat), str(user), until, reason))
            self.db.commit()

    async def mute_info(self, chat, user):
        row = self.db.execute("SELECT until_ts,reason FROM mutes WHERE chat_id=? AND user_id=?", (str(chat), str(user))).fetchone()
        if not row:
            return None
        until = float(row["until_ts"])
        if until and time.time() >= until:
            await self.unmute(chat, user)
            return None
        return dict(row)

    async def unmute(self, chat, user):
        async with self.lock:
            self.db.execute("DELETE FROM mutes WHERE chat_id=? AND user_id=?", (str(chat), str(user)))
            self.db.commit()

    async def warn(self, chat, user):
        async with self.lock:
            self.db.execute("INSERT INTO warnings(chat_id,user_id,count) VALUES(?,?,1) ON CONFLICT(chat_id,user_id) DO UPDATE SET count=count+1",
                            (str(chat), str(user)))
            row = self.db.execute("SELECT count FROM warnings WHERE chat_id=? AND user_id=?", (str(chat), str(user))).fetchone()
            self.db.commit()
            return int(row["count"])


store = Store(str(DB_PATH))

SWEAR_WORDS = [
    "احمق", "بی شعور", "بی‌شعور", "کص", "کس", "کیر", "کون", "جنده",
    "مادرجنده", "ننه جنده", "کسکش", "کسخل", "گاییدم", "گوه", "عن",
    "خایه", "لاشی", "حرومزاده", "حرامزاده", "خفه شو", "گمشو", "سگ پدر",
    "ننه سگ", "کیری", "جقی", "جق", "کص ننت", "ننت جنده", "مادرت جنده",
    "کیرم", "کونت", "fuck", "fck", "fuk", "shit", "bitch", "asshole",
    "bastard", "motherfucker", "cunt", "dick", "pussy", "cock", "whore",
    "slut", "stfu", "fucker", "shithead", "siktir", "orospu", "amk",
    "amına", "piç", "göt", "sik", "amq",
]
BLOCKED_EMOJIS = ("🖕", "🍆", "🍑", "💦", "👉👌")


def normalize(value):
    value = unicodedata.normalize("NFKC", str(value or "")).lower()
    for old, new in {"ي":"ی", "ى":"ی", "ك":"ک", "ة":"ه", "ۀ":"ه", "أ":"ا", "إ":"ا", "آ":"ا"}.items():
        value = value.replace(old, new)
    value = re.sub(r"[\u064b-\u065f\u0670]", "", value)
    value = re.sub(r"(.)\1{2,}", r"\1\1", value)
    value = re.sub(r"[\W_]+", " ", value, flags=re.UNICODE)
    return re.sub(r"\s+", " ", value).strip()


TERMS = tuple(normalize(word) for word in SWEAR_WORDS)


def has_swear(text):
    clean = f" {normalize(text)} "
    return any(term and f" {term} " in clean for term in TERMS)


def has_blocked_emoji(text):
    return any(item in str(text or "") for item in BLOCKED_EMOJIS)


def getv(obj, *keys, default=None):
    for key in keys:
        value = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, None)
        if value is not None:
            return value
    return default


def chat_id(update):
    return str(getv(update, "chat_id", default="") or "")


def sender_id(message):
    return str(getv(message, "sender_id", default="") or "")


def message_id(message):
    return getv(message, "message_id")


def reply_id(message):
    return str(getv(message, "reply_to_message_id", default="") or "")


def is_private(chat):
    return chat.startswith("u0")


def is_group(chat):
    return chat.startswith(("g0", "c0"))


async def send(chat, text, reply_to=None):
    kwargs = {"reply_to_message_id": str(reply_to)} if reply_to else {}
    return await bot.send_message(str(chat), str(text), **kwargs)


async def report_owner(text):
    try:
        await send(OWNER_ID, "📣 گزارش 802 BOT\n\n" + text)
    except Exception:
        log.exception("ارسال گزارش به PV مالک ناموفق بود؛ مالک باید ابتدا /start بزند.")


async def delete_message(update, chat, mid):
    if not mid:
        return False
    try:
        await update.delete(chat_id=str(chat), message_id=str(mid))
        return True
    except Exception:
        log.exception("حذف پیام ناموفق بود: %s", mid)
        return False


async def send_note(chat, path, title):
    if not path.exists():
        await send(chat, f"فایل «{title}» هنوز در پوشه resources قرار نگرفته است.")
        return
    await bot.send_file(str(chat), file=str(path), type="File", text=title)


def media_kind(message):
    sticker = getv(message, "sticker")
    file_obj = getv(message, "file")
    file_type = str(getv(file_obj, "type", default="") or "").lower()
    file_name = str(getv(file_obj, "file_name", default="") or "").lower()
    if sticker:
        return "استیکر"
    if "gif" in file_type or file_name.endswith(".gif"):
        return "GIF"
    return ""


spam_times = defaultdict(lambda: deque(maxlen=SPAM_LIMIT + 2))


def is_spam(chat, user):
    now = time.time()
    q = spam_times[(str(chat), str(user))]
    q.append(now)
    while q and now - q[0] > SPAM_WINDOW_SECONDS:
        q.popleft()
    return len(q) >= SPAM_LIMIT


async def ai_reply(chat, prompt, group=False):
    if not OPENAI_API_KEY:
        await send(chat, "در خدمتم. لطفاً سؤال را واضح‌تر مطرح کنید.")
        return
    try:
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=OPENAI_API_KEY)
        result = await client.chat.completions.create(
            model=AI_MODEL,
            messages=[
                {"role":"system","content":"تو دستیار فارسی‌زبان 802 هستی؛ مؤدب، امن، کوتاه و مفید پاسخ بده."},
                {"role":"user","content":prompt},
            ],
            max_tokens=220,
        )
        await send(chat, (result.choices[0].message.content or "در خدمتم.")[:2500])
    except Exception:
        log.exception("AI failed")
        await send(chat, "فعلاً پاسخ‌گوی هوشمند با خطا روبه‌رو شده است.")


async def handle_private(update, message):
    chat, user = chat_id(update), sender_id(message)
    text = str(getv(message, "text", default="") or "").strip()
    if text == "/start":
        await send(chat, "درود! من 802 هستم.\n\n📘 جزوه علوم\n📗 جزوه ریاضی\n🚪 خروج\n\nشناسه شما: " + user)
    elif text == "/owner":
        await send(chat, "✅ مالک اصلی تأیید شد." if user == OWNER_ID else "⛔ شما مالک ثبت‌شده نیستید.\nشناسه شما: " + user)
    elif text == "جزوه علوم":
        await send_note(chat, SCIENCE_FILE, "جزوه علوم")
    elif text == "جزوه ریاضی":
        await send_note(chat, MATH_FILE, "جزوه ریاضی")
    elif text in ("خروج", "/exit"):
        await send(chat, "از منوی جزوه خارج شدید.")
    elif text and not text.startswith("/"):
        await ai_reply(chat, text)


# نگهداری فرستنده پیام‌ها برای دستورات ریپلای
replied_senders = {}


async def owner_command(update, message, chat, user, text):
    if user != OWNER_ID:
        return False
    if text == "فعال":
        await store.set_active(chat)
        await send(chat, "✅ 802 در این گروه فعال شد.")
        await report_owner(f"گروه فعال شد: {chat}")
        return True
    if text in ("راهنما", "/help"):
        await send(chat, "راهنمای مالک:\nفعال — فعال‌سازی گروه\nراهنما — راهنما\n(ریپلای) اخطار — ثبت اخطار\n(ریپلای) حذف سکوت — رفع محدودیت داخلی")
        return True
    target_mid = reply_id(message)
    if text == "اخطار":
        target = replied_senders.get((chat, target_mid))
        if not target:
            await send(chat, "روی پیام کاربر ریپلای کن؛ پیام باید پس از روشن‌شدن ربات دریافت شده باشد.")
            return True
        count = await store.warn(chat, target)
        await send(chat, f"⚠️ اخطار شماره {count} برای کاربر {target} ثبت شد.")
        await report_owner(f"اخطار شماره {count}\nگروه: {chat}\nکاربر: {target}")
        return True
    if text == "حذف سکوت":
        target = replied_senders.get((chat, target_mid))
        if not target:
            await send(chat, "روی پیام کاربر ریپلای کن؛ پیام باید پس از روشن‌شدن ربات دریافت شده باشد.")
            return True
        await store.unmute(chat, target)
        await send(chat, f"🔊 محدودیت داخلی کاربر {target} برداشته شد.")
        await report_owner(f"رفع محدودیت\nگروه: {chat}\nکاربر: {target}")
        return True
    return False


async def handle_group(update, message):
    chat, user = chat_id(update), sender_id(message)
    mid = message_id(message)
    text = str(getv(message, "text", default="") or "").strip()
    if not chat or not user:
        return
    if mid:
        replied_senders[(chat, str(mid))] = user
        if len(replied_senders) > 5000:
            replied_senders.clear()

    if await owner_command(update, message, chat, user, text):
        return
    if not await store.active(chat) or user == OWNER_ID:
        return

    if await store.mute_info(chat, user):
        await delete_message(update, chat, mid)
        return

    reason, duration = None, 0
    if has_swear(text) or has_blocked_emoji(text):
        reason = "کلمات یا ایموجی نامناسب"
    else:
        kind = media_kind(message)
        if kind:
            reason, duration = f"ارسال {kind}", TEMP_MUTE_SECONDS
        elif is_spam(chat, user):
            reason, duration = "ارسال پیام‌های پشت‌سرهم", TEMP_MUTE_SECONDS

    if reason:
        deleted = await delete_message(update, chat, mid)
        await store.mute(chat, user, duration, reason)
        duration_text = "تا رفع توسط مالک" if duration == 0 else "۱۰ دقیقه"
        await send(chat, f"⚠️ پیام کاربر {user} به دلیل {reason} شناسایی شد. محدودیت داخلی: {duration_text}.")
        await report_owner(
            f"🚨 تخلف شناسایی شد\nگروه: {chat}\nکاربر: {user}\nدلیل: {reason}\n"
            f"متن: {text[:350] or '[رسانه]'}\nحذف پیام: {'موفق' if deleted else 'ناموفق/بدون مجوز'}"
        )
        return

    if AI_GROUP_ENABLED and text and (text.lower().startswith(("802", "۸۰۲", "@802")) or "?" in text or "؟" in text):
        await ai_reply(chat, text, group=True)


@bot.on_update()
async def on_update(client, update):
    try:
        message = getv(update, "new_message")
        if message is None:
            return
        chat = chat_id(update)
        if is_private(chat):
            await handle_private(update, message)
        elif is_group(chat):
            await handle_group(update, message)
    except Exception:
        log.exception("خطا در پردازش آپدیت")


@bot.on_start()
async def on_start(client):
    log.info("802 BOT started in token mode.")
    try:
        info = await client.get_me()
        log.info("Bot: %s", getv(info, "bot_title", "username", default="unknown"))
    except Exception:
        log.exception("get_me failed")


async def main():
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
