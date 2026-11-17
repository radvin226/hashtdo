import os
from dotenv import load_dotenv

load_dotenv()

# توکن بات (از BotFather روبیکا) - فقط برای پاسخ‌ها
BOT_TOKEN = os.getenv("BOT_TOKEN")

# سشن اکانت کاربری (همه کارهای سنگین از این اکانت انجام می‌شود)
ACCOUNT_SESSION = os.getenv("ACCOUNT_SESSION", "account802")

DATA_DIR = "data"
TEMP_DIR = "temp"
MUSIC_DIR = "music"

OWNER_FILE = f"{DATA_DIR}/owner.json"
ACTIVE_GROUPS_FILE = f"{DATA_DIR}/active_groups.json"
MUTED_FILE = f"{DATA_DIR}/muted.json"

# مدت سکوت موقت (استیکر / گیف / اسپم) به ثانیه
TEMP_MUTE_SECONDS = 10 * 60  # ۱۰ دقیقه
