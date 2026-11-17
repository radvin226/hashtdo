# -*- coding: utf-8 -*-
"""
802 بات — نسخه نهایی کامل
کارها از اکانت عادی | پاسخ‌ها از بات
آنتی‌فحش + استیکر + گیف + اسپم + سکوت ۱۰ دقیقه‌ای + کال + پخش
"""

import asyncio
import json
import os
import time
from collections import defaultdict, deque
from pathlib import Path

from rubpy import Client
from rubpy.bot import BotClient
from rubpy.types import Update

from config import *
from swear_words import has_swear
from voice_chat_player import VoiceChatPlayer

Path(DATA_DIR).mkdir(exist_ok=True)
Path(TEMP_DIR).mkdir(exist_ok=True)
Path(MUSIC_DIR).mkdir(exist_ok=True)

# ---------------- داده پایدار ----------------
def load(path, default=None):
    if default is None:
        default = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

owner = load(OWNER_FILE, {})
active_groups = load(ACTIVE_GROUPS_FILE, {})
muted = load(MUTED_FILE, {})  # {group: {user: {"until": ts|0, "reason": "..."}}}

def is_owner(guid: str) -> bool:
    return bool(guid) and owner.get("guid") == str(guid)

def is_active(guid: str) -> bool:
    return active_groups.get(guid, False)

def is_muted(group: str, user: str) -> bool:
    data = muted.get(group, {}).get(str(user))
    if not data:
        return False
    until = data.get("until", 0)
    if until == 0:  # دائمی
        return True
    if time.time() < until:
        return True
    # منقضی شده
    muted[group].pop(str(user), None)
    if not muted[group]:
        muted.pop(group, None)
    save(MUTED_FILE, muted)
    return False

def set_mute(group: str, user: str, seconds: int = 0, reason: str = "فحش"):
    """seconds=0 یعنی دائمی"""
    until = 0 if seconds <= 0 else int(time.time()) + seconds
    muted.setdefault(group, {})[str(user)] = {"until": until, "reason": reason}
    save(MUTED_FILE, muted)

def remove_mute(group: str, user: str):
    if group in muted and str(user) in muted[group]:
        muted[group].pop(str(user), None)
        if not muted[group]:
            muted.pop(group, None)
        save(MUTED_FILE, muted)

# ---------------- اسپم دیتکتور ساده ----------------
spam_tracker = defaultdict(lambda: deque(maxlen=10))

def is_spam(user: str, window=30, limit=5) -> bool:
    now = time.time()
    q = spam_tracker[str(user)]
    q.append(now)
    while q and now - q[0] > window:
        q.popleft()
    return len(q) >= limit

# ---------------- کلاینت‌ها ----------------
account = Client(ACCOUNT_SESSION)
bot = BotClient(BOT_TOKEN)

active_voices = {}

async def bot_reply(chat_id: str, text: str):
    try:
        await bot.send_message(chat_id, text)
    except Exception as e:
        print("خطا بات:", e)

async def notify_owner(text: str):
    if owner.get("guid"):
        try:
            await bot.send_message(owner["guid"], f"📢 **802 بات**\n\n{text}")
        except Exception as e:
            print("خطا نوتیف:", e)

async def get_name(user_guid: str) -> str:
    try:
        info = await account.get_user_info(user_guid)
        return getattr(info, "first_name", None) or user_guid
    except Exception:
        return user_guid

# =========================================================
#                   هندلر اصلی (روی اکانت)
# =========================================================
@account.on_message_updates()
async def handler(update: Update):
    try:
        guid = getattr(update, "object_guid", None)
        if not guid:
            return

        author = getattr(update, "author_guid", None)
        text = (getattr(update, "raw_text", None) or getattr(update, "text", None) or "").strip()
        message_id = getattr(update, "message_id", None)
        reply_id = getattr(update, "reply_message_id", None) or getattr(update, "reply_to_message_id", None)

        is_private = str(guid).startswith("u0")
        is_group = str(guid).startswith("g0")

        is_sticker = bool(getattr(update, "sticker", None) or getattr(getattr(update, "message", None), "sticker", None))
        is_gif = bool(
            getattr(update, "gif", None)
            or getattr(getattr(update, "message", None), "gif", None)
            or "gif" in str(getattr(update, "type", "")).lower()
        )

        # ==================== پیوی ====================
        if is_private:
            if text == "/owner":
                owner["guid"] = str(author)
                save(OWNER_FILE, owner)
                await bot_reply(guid, "✅ شما به عنوان **اونر** ثبت شدید.\nاز این لحظه فقط شما در گروه‌ها فرمان می‌دهید.")
                return

            if text in ["/start", "شروع", "استارت"]:
                await bot_reply(guid,
                    "درخواست شما چیست؟\n"
                    "کامند مورد نظر را بگویید:\n\n"
                    "• جزوه علوم\n"
                    "• جزوه ریاضی\n"
                    "• خروج"
                )
                return

            if "جزوه علوم" in text:
                await bot_reply(guid, "📚 جزوه علوم آماده است.\n(اینجا فایل یا لینک جزوه را قرار دهید)")
                return
            if "جزوه ریاضی" in text:
                await bot_reply(guid, "📐 جزوه ریاضی آماده است.\n(اینجا فایل یا لینک جزوه را قرار دهید)")
                return
            if text == "خروج":
                await bot_reply(guid, "خداحافظ 🌟")
                return

            polite = [
                "چطور می‌تونم کمکتون کنم؟",
                "بله، در خدمتم. لطفاً واضح‌تر بفرمایید.",
                "با احترام، متوجه نشدم. دوباره بفرمایید.",
                "در خدمتم 🌟"
            ]
            await bot_reply(guid, polite[hash(text) % len(polite)])
            return

        # ==================== گروه ====================
        if is_group:

            if text == "فعال":
                if is_owner(author):
                    active_groups[guid] = True
                    save(ACTIVE_GROUPS_FILE, active_groups)
                    await bot_reply(guid, "✅ بات **802** در این گروه فعال شد.")
                    await notify_owner(f"گروه فعال شد:\n`{guid}`")
                return

            if not is_active(guid):
                return

            # اگر کاربر سکوت است → پیامش رو پاک کن
            if is_muted(guid, author) and not is_owner(author):
                try:
                    await account.delete_messages(guid, [message_id])
                except Exception:
                    pass
                return

            # ---------- دستورات فقط اونر ----------
            if is_owner(author):

                if text == "کال":
                    try:
                        if guid in active_voices:
                            try:
                                active_voices[guid].stop()
                            except Exception:
                                pass
                            del active_voices[guid]
                        await account.create_group_voice_chat(guid)
                        await bot_reply(guid, "🔊 ویس‌کال شروع شد.\nروی آهنگ ریپلای بزنید و بنویسید: **پخش**")
                        await notify_owner(f"کال در گروه `{guid}` شروع شد.")
                    except Exception as e:
                        await bot_reply(guid, f"❌ خطا در شروع کال:\n`{e}`")
                    return

                if text == "قطع کال":
                    try:
                        if guid in active_voices:
                            try:
                                active_voices[guid].stop()
                            except Exception:
                                pass
                            del active_voices[guid]
                        try:
                            await account.leave_group_voice_chat(guid)
                        except Exception:
                            pass
                        await bot_reply(guid, "🔇 کال قطع شد.")
                        await notify_owner(f"کال در گروه `{guid}` قطع شد.")
                    except Exception as e:
                        await bot_reply(guid, f"❌ خطا در قطع کال:\n`{e}`")
                    return

                if text == "پخش":
                    if not reply_id:
                        await bot_reply(guid, "لطفاً روی پیام آهنگ ریپلای بزنید و بنویسید: **پخش**")
                        return
                    await bot_reply(guid, "🎵 در حال آماده‌سازی و پخش آهنگ...")
                    try:
                        file_path = await account.download(
                            message_id=reply_id,
                            object_guid=guid,
                            file_name=f"{TEMP_DIR}/music_{guid}.mp3"
                        )
                        if not file_path or not os.path.exists(str(file_path)):
                            await bot_reply(guid, "❌ نتونستم فایل آهنگ را دانلود کنم.")
                            return
                        connection = await account.voice_chat_player(guid, Path(file_path))
                        if connection:
                            active_voices[guid] = connection
                            await bot_reply(guid, "✅ آهنگ در حال پخش است.")
                            await notify_owner(f"آهنگ در گروه `{guid}` پخش شد.")
                        else:
                            await bot_reply(guid, "❌ پخش آهنگ ناموفق بود.")
                    except Exception as e:
                        await bot_reply(guid, f"❌ خطا در پخش:\n`{e}`")
                    return

                if text == "حذف سکوت":
                    if not reply_id:
                        await bot_reply(guid, "روی پیام کاربر ریپلای بزنید و بنویسید: **حذف سکوت**")
                        return
                    try:
                        msgs = await account.get_messages_by_id(guid, [reply_id])
                        target_user = None
                        if msgs and hasattr(msgs, "messages") and msgs.messages:
                            target_user = getattr(msgs.messages[0], "author_object_guid", None)
                        if target_user and is_muted(guid, target_user):
                            try:
                                await account.ban_group_member(guid, target_user, action="Unset")
                            except Exception:
                                pass
                            remove_mute(guid, target_user)
                            name = await get_name(target_user)
                            await bot_reply(guid, f"✅ سکوت کاربر **{name}** برداشته شد.")
                            await notify_owner(f"سکوت کاربر `{target_user}` در گروه `{guid}` برداشته شد.")
                        else:
                            await bot_reply(guid, "این کاربر سکوت نیست یا پیام پیدا نشد.")
                    except Exception as e:
                        await bot_reply(guid, f"❌ خطا در حذف سکوت:\n`{e}`")
                    return

            # ---------- آنتی فحش (دائمی) ----------
            if text and has_swear(text) and not is_owner(author):
                try:
                    await account.delete_messages(guid, [message_id])
                except Exception:
                    pass
                try:
                    await account.ban_group_member(guid, author, action="Set")
                except Exception as e:
                    print("ban error:", e)
                set_mute(guid, author, seconds=0, reason="فحش")
                name = await get_name(author)
                await bot_reply(
                    guid,
                    f"🚫 کاربر **{name}** به دلیل استفاده از کلمات نامناسب سکوت شد.\n"
                    f"برای برداشتن سکوت، اونر باید روی پیامش ریپلای بزنه و بنویسه: **حذف سکوت**"
                )
                await notify_owner(
                    f"🚫 فحش\nگروه: `{guid}`\nکاربر: `{author}` ({name})\nمتن: `{text[:120]}`"
                )
                return

            # ---------- استیکر (۱۰ دقیقه) ----------
            if is_sticker and not is_owner(author):
                try:
                    await account.delete_messages(guid, [message_id])
                except Exception:
                    pass
                try:
                    await account.ban_group_member(guid, author, action="Set")
                except Exception:
                    pass
                set_mute(guid, author, seconds=TEMP_MUTE_SECONDS, reason="استیکر")
                name = await get_name(author)
                await bot_reply(
                    guid,
                    f"🚫 کاربر **{name}** به دلیل ارسال **استیکر** به مدت ۱۰ دقیقه سکوت شد."
                )
                await notify_owner(f"استیکر\nگروه: `{guid}`\nکاربر: `{author}` ({name})")
                return

            # ---------- گیف (۱۰ دقیقه) ----------
            if is_gif and not is_owner(author):
                try:
                    await account.delete_messages(guid, [message_id])
                except Exception:
                    pass
                try:
                    await account.ban_group_member(guid, author, action="Set")
                except Exception:
                    pass
                set_mute(guid, author, seconds=TEMP_MUTE_SECONDS, reason="گیف")
                name = await get_name(author)
                await bot_reply(
                    guid,
                    f"🚫 کاربر **{name}** به دلیل ارسال **گیف** به مدت ۱۰ دقیقه سکوت شد."
                )
                await notify_owner(f"گیف\nگروه: `{guid}`\nکاربر: `{author}` ({name})")
                return

            # ---------- اسپم (۱۰ دقیقه) ----------
            if author and is_spam(author) and not is_owner(author):
                try:
                    await account.delete_messages(guid, [message_id])
                except Exception:
                    pass
                try:
                    await account.ban_group_member(guid, author, action="Set")
                except Exception:
                    pass
                set_mute(guid, author, seconds=TEMP_MUTE_SECONDS, reason="اسپم")
                name = await get_name(author)
                await bot_reply(
                    guid,
                    f"🚫 کاربر **{name}** به دلیل **اسپم** به مدت ۱۰ دقیقه سکوت شد."
                )
                await notify_owner(f"اسپم\nگروه: `{guid}`\nکاربر: `{author}` ({name})")
                return

    except Exception as e:
        print("خطای کلی:", e)


# =========================================================
#                   اجرا
# =========================================================
async def main():
    print("در حال راه‌اندازی بات 802...")

    await account.start()
    print("✅ اکانت عادی آماده است (کارها)")

    await bot.start()
    print("✅ بات آماده است (پاسخ‌ها)")

    account.voice_chat_player = VoiceChatPlayer.voice_chat_player.__get__(account, Client)

    print("✅ سیستم کامل 802 فعال شد")
    print("کارها از اکانت | پاسخ‌ها از بات")
    print("آنتی‌فحش + استیکر + گیف + اسپم + کال + پخش")

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
