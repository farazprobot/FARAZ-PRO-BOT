import os
import re
import sys
import time
import json
import asyncio
from datetime import datetime, timezone, timedelta

from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    ChatPermissions,
)
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    ChatMemberHandler,
    MessageHandler,
    filters,
)

BOT_TOKEN = os.environ["BOT_TOKEN"]


class _RealUserFilter(filters.MessageFilter):
    """Passes only messages sent by real, non-bot human users."""

    def filter(self, message):
        return message.from_user is not None and not message.from_user.is_bot


REAL_USER = _RealUserFilter()
# Owner identified by username (case-insensitive, @ stripped)
OWNER_USERNAME = os.environ.get("OWNER_USERNAME", "").lstrip("@").lower().strip()

CHANNEL_ID = -1002400598751
CHANNEL_LINK = "https://t.me/+i7HqaczkTtJmODc1"

IST = timezone(timedelta(hours=5, minutes=30))

known_chats: set[int] = set()

# Chats where night mode auto-lock/unlock is active.
# If empty → applies to ALL known chats (default).
# If non-empty → only those chats are locked/unlocked on schedule.
night_mode_chats: set[int] = set()

LOCK_HOUR = 1
LOCK_MINUTE = 0
UNLOCK_HOUR = 7
UNLOCK_MINUTE = 30

night_mode_enabled = True
anti_slang_enabled = True  # master switch

# Per-group anti-slang toggles (like night_mode_chats).
# If a group is in anti_slang_chats → bad words are deleted there.
# If a group is also in anti_slang_warn_chats → warnings/mute are issued there.
# If empty → anti-slang applies to NO groups.
anti_slang_chats: set[int] = set()
anti_slang_warn_chats: set[int] = set()

# Owner DM panel state machine — tracks what text input the bot is waiting for
panel_state: dict[int, str] = {}

# When True, the bot also forwards each event to the owner's DM in real-time
activity_log_enabled: bool = False

# In-panel logs (newest events kept in memory, not persisted across restarts)
activity_log: list[dict] = []   # moderation events  {"ts": "HH:MM", "msg": str}
dm_log:       list[dict] = []   # DM interactions     {"ts": "HH:MM", "msg": str}
MAX_LOG_SIZE  = 100
LOGS_PER_PAGE = 8

BAD_WORDS: set[str] = {
    "madarchod",
    "mc",
    "behenchod",
    "bc",
    "chutiya",
    "chutiye",
    "bhosdike",
    "bhosdika",
    "gaandu",
    "gandu",
    "lodu",
    "loda",
    "lundura",
    "randi",
    "saali",
    "sala",
    "haramzada",
    "haramzadi",
    "kamina",
    "kamine",
    "kutte",
    "kutta",
    "suar",
    "harami",
    "besharam",
    "ullu",
    "bakwaas",
    "maa ki aankh",
    "teri maa",
    "teri ma",
    "bhosad",
    "bhosdi",
    "chod",
    "chodna",
    "chodne",
    "chudai",
    "chudi",
    "lauda",
    "lavda",
    "jhatu",
    "jhat",
    "gand",
    "gaand",
    "gaandu",
    "madhar",
    "madar",
    "bhadwa",
    "bhadwe",
    "chakka",
    "hijra",
    "hijde",
    "child porn",
    "childporn",
    "cp",
    "csam",
    "kiddie porn",
    "pedo",
    "pedophile",
    "loli",
    "shota",
    "terrorist",
    "terrorism",
    "jihad",
    "isis",
    "isil",
    "al qaeda",
    "al-qaeda",
    "taliban",
    "boko haram",
    "bomb blast",
    "suicide bomb",
    "suicide bomber",
    "kill all",
    "death threat",
    "i will kill",
    "i will bomb",
    "drug dealer",
    "drug trafficking",
    "buy drugs",
    "sell drugs",
    "cocaine",
    "heroin",
    "meth",
    "methamphetamine",
    "crack cocaine",
    "hitman",
    "hire killer",
    "contract kill",
    "hack",
    "hacking",
    "ddos",
    "phishing",
    "ransomware",
    "money laundering",
    "black money",
    "fuck",
    "fucker",
    "fucking",
    "fuk",
    "f**k",
    "f***",
    "shit",
    "sh*t",
    "bitch",
    "bastard",
    "asshole",
    "ass",
    "dick",
    "cock",
    "pussy",
    "whore",
    "slut",
    "cunt",
    "motherfucker",
    "mf",
    "wtf",
    "stfu",
    # More Hindi / Hinglish slang
    "teri maa ki",
    "teri behen ki",
    "behen ke lode",
    "bkl",
    "bklol",
    "chut",
    "choot",
    "mkc",
    "bhk",
    "lund",
    "lund maro",
    "randi ka bacha",
    "haramkhor",
    "kutti",
    "kutiya",
    "teri gaand",
    "gaand mara",
    "gaand marao",
    "maderchod",
    "bhosdiwale",
    "bhosdiwali",
    "chutmarike",
    "chutmarika",
    "lawde",
    "lawda",
    "bhenchod",
    "bhnchd",
    "mchd",
    "gandu hai",
    "gadha",
    "gadhe",
    "ullu ka pattha",
    "teri aukat",
    "aukat nahi",
    "nikamma",
    "nikammi",
    "kamiine",
    "kameeni",
    "besharm",
    "nalayak",
    "saale",
    "saali",
    "saala kutta",
    "kamine log",
    "chod de",
    "chod diya",
    "chodoge",
    # English slang / abbreviations
    "fck",
    "fk",
    "fuk u",
    "fvck",
    "phuck",
    "b1tch",
    "b!tch",
    "a$$",
    "a**",
    "sh!t",
    "d!ck",
    "c0ck",
    "p*ssy",
    "wh0re",
    "gtfo",
    "kys",
    "kms",
    "kys yourself",
    "retard",
    "retarded",
    "spastic",
    "piss off",
    "piss on",
    "jackass",
    "dumbass",
    "son of a bitch",
    "sob",
    "moron",
    "idiot",
    "stupid ass",
    "dumb fuck",
    "dumbfuck",
    "shut the fuck up",
    "get fucked",
    "go fuck yourself",
    "eat shit",
    "suck my",
    "lick my",
    # Threats / abuse
    "i will rape",
    "i will kill you",
    "i will hurt you",
    "ill kill",
    "ill hurt",
    "gonna kill",
    "gonna rape",
    "rape",
    "raping",
    "rapist",
}

DEFAULT_BAD_WORDS: frozenset[str] = frozenset(BAD_WORDS)

user_warnings: dict[tuple[int, int], int] = {}
MAX_WARNINGS = 3

spam_tracker: dict[tuple[int, int], list[float]] = {}
SPAM_MSG_LIMIT = 5
SPAM_TIME_WINDOW = 5
SPAM_MUTE_DURATION = 600

whitelisted: dict[int, set[int]] = {}

# Per-group anti-edit toggle (same pattern as anti_slang_chats / night_mode_chats).
# If a group is in anti_edit_chats → edited messages are deleted there.
# If not in the set → anti-edit is OFF for that group.
anti_edit_chats: set[int] = set()

verification_targets: dict[tuple[int, int], int] = {}

STATE_FILE = "bot/state.json"


def _write_state():
    """Blocking file write — always called via run_in_executor to avoid blocking the event loop."""
    data = {
        "known_chats": list(known_chats),
        "night_mode_enabled": night_mode_enabled,
        "anti_slang_enabled": anti_slang_enabled,
        "lock_hour": LOCK_HOUR,
        "lock_minute": LOCK_MINUTE,
        "unlock_hour": UNLOCK_HOUR,
        "unlock_minute": UNLOCK_MINUTE,
        "user_warnings": [[cid, uid, cnt] for (cid, uid), cnt in user_warnings.items()],
        "whitelisted": {str(cid): list(uids) for cid, uids in whitelisted.items()},
        "custom_bad_words": list(BAD_WORDS - DEFAULT_BAD_WORDS),
        "anti_edit_chats": list(anti_edit_chats),
        "activity_log_enabled": activity_log_enabled,
        "night_mode_chats": list(night_mode_chats),
        "anti_slang_chats": list(anti_slang_chats),
        "anti_slang_warn_chats": list(anti_slang_warn_chats),
    }
    try:
        state_dir = os.path.dirname(STATE_FILE)
        if state_dir:
            os.makedirs(state_dir, exist_ok=True)
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"[State] Failed to save: {e}")


def save_state():
    """Schedule a non-blocking state save in the thread pool."""
    loop = asyncio.get_event_loop()
    loop.run_in_executor(None, _write_state)


def load_state():
    global night_mode_enabled, anti_slang_enabled
    global LOCK_HOUR, LOCK_MINUTE, UNLOCK_HOUR, UNLOCK_MINUTE, night_mode_chats
    global anti_slang_chats, anti_slang_warn_chats, anti_edit_chats, activity_log_enabled
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        known_chats.update(data.get("known_chats", []))
        night_mode_enabled = data.get("night_mode_enabled", True)
        anti_slang_enabled = data.get("anti_slang_enabled", True)
        LOCK_HOUR = data.get("lock_hour", LOCK_HOUR)
        LOCK_MINUTE = data.get("lock_minute", LOCK_MINUTE)
        UNLOCK_HOUR = data.get("unlock_hour", UNLOCK_HOUR)
        UNLOCK_MINUTE = data.get("unlock_minute", UNLOCK_MINUTE)
        for cid, uid, cnt in data.get("user_warnings", []):
            user_warnings[(cid, uid)] = cnt
        for cid_str, uids in data.get("whitelisted", {}).items():
            whitelisted[int(cid_str)] = set(uids)
        for word in data.get("custom_bad_words", []):
            BAD_WORDS.add(word)
        # legacy key kept for backward compat (no-op now)
        _ = data.get("edit_delete_excluded", [])
        night_mode_chats.update(data.get("night_mode_chats", []))
        anti_slang_chats.update(data.get("anti_slang_chats", []))
        anti_slang_warn_chats.update(data.get("anti_slang_warn_chats", []))
        anti_edit_chats.update(data.get("anti_edit_chats", []))
        activity_log_enabled = data.get("activity_log_enabled", False)
        print(
            f"[State] Loaded — {len(known_chats)} groups, night_mode={night_mode_enabled}, "
            f"night_mode_chats={len(night_mode_chats)}"
        )
    except FileNotFoundError:
        print("[State] No saved state found, starting fresh.")
    except Exception as e:
        print(f"[State] Failed to load: {e}")


async def require_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    # Auto-register the group whenever any command is used in it
    if update.effective_chat.type in ("group", "supergroup") and chat_id not in known_chats:
        known_chats.add(chat_id)
        save_state()
        print(f"[Group] Auto-registered via command: {chat_id}")
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
    except Exception:
        return False
    if member.status in ("administrator", "creator"):
        return True
    try:
        if update.message:
            await update.message.delete()
    except Exception:
        pass
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{update.effective_user.mention_html()}, ❌ Only admins can use bot commands.",
            parse_mode="HTML",
        )
    except Exception:
        pass
    return False


def seconds_until(hour: int, minute: int = 0) -> float:
    now = datetime.now(IST)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def locked_permissions(locked: bool) -> ChatPermissions:
    if not locked:
        return ChatPermissions(
            can_send_messages=True,
            can_send_other_messages=True,
            can_send_audios=True,
            can_send_documents=True,
            can_send_photos=True,
            can_send_videos=True,
            can_send_video_notes=True,
            can_send_voice_notes=True,
            can_send_polls=True,
        )
    return ChatPermissions(
        can_send_messages=True,
        can_send_other_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
    )


def full_mute_permissions() -> ChatPermissions:
    return ChatPermissions(
        can_send_messages=False,
        can_send_other_messages=False,
        can_send_audios=False,
        can_send_documents=False,
        can_send_photos=False,
        can_send_videos=False,
        can_send_video_notes=False,
        can_send_voice_notes=False,
        can_send_polls=False,
    )


def log_to_dm(text: str):
    """Record a DM interaction in the DM log."""
    ts = datetime.now(IST).strftime("%H:%M")
    dm_log.append({"ts": ts, "msg": text})
    if len(dm_log) > MAX_LOG_SIZE:
        dm_log.pop(0)


async def log_to_owner(bot, text: str):
    """Record a moderation event in the group log; forward to owner DM if live notify is on."""
    # Always append to the browsable in-panel log
    ts = datetime.now(IST).strftime("%H:%M")
    activity_log.append({"ts": ts, "msg": text})
    if len(activity_log) > MAX_LOG_SIZE:
        activity_log.pop(0)
    # Forward to DM only when live-notify is enabled
    if not activity_log_enabled or not OWNER_USERNAME:
        return
    try:
        await bot.send_message(
            chat_id=f"@{OWNER_USERNAME}",
            text=text,
            parse_mode="HTML",
        )
    except Exception:
        pass


async def set_all_chats_locked(bot, locked: bool, silent: bool = False):
    permissions = locked_permissions(locked=locked)
    status = "🔒 LOCKED" if locked else "🔓 UNLOCKED"
    # Only lock/unlock groups that are explicitly toggled ON in /nightgroup.
    target_chats = list(night_mode_chats)
    # Messages (Good Night / Good Morning) ONLY go to explicitly configured night-mode chats.
    message_chats = set(night_mode_chats)
    lock_t = (
        f"{LOCK_HOUR:02d}:{LOCK_MINUTE:02d} AM"
        if LOCK_HOUR < 12
        else f"{LOCK_HOUR:02d}:{LOCK_MINUTE:02d} PM"
    )
    unlock_t = (
        f"{UNLOCK_HOUR:02d}:{UNLOCK_MINUTE:02d} AM"
        if UNLOCK_HOUR < 12
        else f"{UNLOCK_HOUR:02d}:{UNLOCK_MINUTE:02d} PM"
    )
    msg = (
        f"🌙 GOOD NIGHT!\nNight mode is activated until {unlock_t} IST."
        if locked
        else f"☀️ GOOD MORNING!\nNight mode is deactivated until {lock_t} IST."
    )
    for chat_id in target_chats:
        try:
            await bot.set_chat_permissions(chat_id=chat_id, permissions=permissions)
            if not silent and chat_id in message_chats:
                await bot.send_message(chat_id=chat_id, text=msg)
            print(f"[Night Mode] Chat {chat_id} {status}")
            emoji = "🌙" if locked else "☀️"
            action = "Night mode activated" if locked else "Night mode deactivated"
            asyncio.create_task(log_to_owner(
                bot,
                f"{emoji} <b>{action}</b>\n"
                f"🤖 Bot: {'Locked chat (text only)' if locked else 'Unlocked chat (all media)'}\n"
                f"💬 Chat: <code>{chat_id}</code>",
            ))
        except Exception as e:
            print(f"[Night Mode] Failed for {chat_id}: {e}")


async def night_mode_scheduler(bot):
    while True:
        try:
            now = datetime.now(IST)
            now_mins = now.hour * 60 + now.minute
            lock_mins = LOCK_HOUR * 60 + LOCK_MINUTE
            unlock_mins = UNLOCK_HOUR * 60 + UNLOCK_MINUTE
            lock_label = f"{LOCK_HOUR:02d}:{LOCK_MINUTE:02d}"
            unlock_label = f"{UNLOCK_HOUR:02d}:{UNLOCK_MINUTE:02d}"
            # Handle both same-day (e.g. 01:00–07:30) and
            # overnight (e.g. 23:00–07:30) lock windows correctly.
            if lock_mins < unlock_mins:
                is_night_now = lock_mins <= now_mins < unlock_mins
            else:  # crosses midnight
                is_night_now = now_mins >= lock_mins or now_mins < unlock_mins
            if is_night_now:
                secs = seconds_until(UNLOCK_HOUR, UNLOCK_MINUTE)
                print(
                    f"[Night Mode] Currently night time — chats already locked. Unlock in {secs / 60:.0f} min."
                )
                if night_mode_enabled:
                    await set_all_chats_locked(bot, locked=True, silent=True)
                await asyncio.sleep(secs)
                print(f"[Night Mode] {unlock_label} IST — unlocking chats.")
                if night_mode_enabled:
                    await set_all_chats_locked(bot, locked=False)
            else:
                secs = seconds_until(LOCK_HOUR, LOCK_MINUTE)
                print(f"[Night Mode] Next lock in {secs / 60:.0f} min.")
                await asyncio.sleep(secs)
                print(f"[Night Mode] {lock_label} IST — locking chats.")
                if night_mode_enabled:
                    await set_all_chats_locked(bot, locked=True)
                await asyncio.sleep(seconds_until(UNLOCK_HOUR, UNLOCK_MINUTE))
                print(f"[Night Mode] {unlock_label} IST — unlocking chats.")
                if night_mode_enabled:
                    await set_all_chats_locked(bot, locked=False)
        except asyncio.CancelledError:
            raise
        except Exception as e:
            print(f"[Night Mode] Scheduler error: {e} — retrying in 60s.")
            await asyncio.sleep(60)


async def nightmode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global night_mode_enabled
    if not await require_admin(update, context):
        return
    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        status = "🟢 ON" if night_mode_enabled else "🔴 OFF"
        await update.message.reply_text(
            f"🌙 Night Mode is currently {status}\n\nUsage:\n"
            f"/nightmode on — enable auto lock\n"
            f"/nightmode off — disable auto lock"
        )
        return
    if args[0].lower() == "off":
        night_mode_enabled = False
        save_state()
        await update.message.reply_text(
            "🔴 Night Mode disabled. Chat will not auto-lock at 1am."
        )
    else:
        night_mode_enabled = True
        save_state()
        await update.message.reply_text(
            "🟢 Night Mode enabled. Chat will auto-lock at 1am and unlock at 7:30am IST."
        )


async def check_member(bot, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ["member", "administrator", "creator"]
    except Exception as e:
        print(f"[ChannelCheck] Could not verify user {user_id}: {e}")
        # Return True on error so we don't falsely mute the whole group
        # if the bot loses access to the channel temporarily
        return True


def contains_bad_word(text: str) -> str | None:
    if not text:
        return None
    lower = text.lower()
    for word in BAD_WORDS:
        if " " in word:
            # Multi-word phrases: plain substring match is fine
            if word in lower:
                return word
        else:
            # Single words: require word boundary to avoid false positives
            # e.g. "ass" should NOT match "class" or "assassin"
            if re.search(r"\b" + re.escape(word) + r"\b", lower):
                return word
    return None


async def check_on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.effective_user:
        return
    if not update.message:
        return
    if update.message.sender_chat:
        return
    if update.effective_user.is_bot:
        return
    # Only act in groups
    if update.effective_chat.type not in ("group", "supergroup"):
        return

    user = update.effective_user
    user_id = user.id
    chat_id = update.effective_chat.id

    if chat_id not in known_chats:
        known_chats.add(chat_id)
        save_state()

    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        is_admin = member.status in ("administrator", "creator")
    except Exception:
        is_admin = False

    if user_id in whitelisted.get(chat_id, set()):
        return

    if not is_admin:
        key = (chat_id, user_id)
        now_ts = time.time()
        timestamps = spam_tracker.get(key, [])
        timestamps = [t for t in timestamps if now_ts - t < SPAM_TIME_WINDOW]
        timestamps.append(now_ts)
        spam_tracker[key] = timestamps

        if len(timestamps) >= SPAM_MSG_LIMIT:
            spam_tracker[key] = []
            try:
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=full_mute_permissions(),
                    until_date=int(now_ts) + SPAM_MUTE_DURATION,
                )
            except Exception:
                pass
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"🚫 {user.mention_html()} has been muted for <b>10 minutes</b> for spamming!",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            group_title = update.effective_chat.title or str(chat_id)
            asyncio.create_task(log_to_owner(
                context.bot,
                f"🚫 <b>Spam Detected</b>\n"
                f"👤 User: {user.mention_html()}\n"
                f"🤖 Bot: Muted for 10 minutes\n"
                f"💬 Group: {group_title}",
            ))
            return

    # Check both plain text AND media captions for bad words
    message_text = update.message.text or update.message.caption or ""
    if anti_slang_enabled and chat_id in anti_slang_chats and not is_admin and contains_bad_word(message_text):
        try:
            await update.message.delete()
        except Exception:
            pass
        group_title = update.effective_chat.title or str(chat_id)
        asyncio.create_task(log_to_owner(
            context.bot,
            f"🗑️ <b>Bad Word Detected</b>\n"
            f"👤 User: {user.mention_html()}\n"
            f"🤖 Bot: Message deleted\n"
            f"💬 Group: {group_title}",
        ))
        if chat_id not in anti_slang_warn_chats:
            return
        warn_key = (chat_id, user_id)
        user_warnings[warn_key] = user_warnings.get(warn_key, 0) + 1
        count = user_warnings[warn_key]
        remaining = MAX_WARNINGS - count
        if count >= MAX_WARNINGS:
            try:
                await context.bot.restrict_chat_member(
                    chat_id=chat_id,
                    user_id=user_id,
                    permissions=full_mute_permissions(),
                    until_date=int(time.time()) + 3600,
                )
            except Exception:
                pass
            user_warnings[warn_key] = 0
            save_state()
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=f"⛔ {user.mention_html()} has been muted for 1 hour!\n📊 Warnings: <b>3/3</b> (limit reached)",
                    parse_mode="HTML",
                )
            except Exception:
                pass
            asyncio.create_task(log_to_owner(
                context.bot,
                f"🔇 <b>Bad Word — Muted</b>\n"
                f"👤 User: {user.mention_html()}\n"
                f"📊 Warnings: 3/3 (limit reached)\n"
                f"🤖 Bot: Muted for 1 hour\n"
                f"💬 Group: {group_title}",
            ))
        else:
            save_state()
            try:
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⚠️ {user.mention_html()} bad language detected and message deleted!\n"
                        f"📊 Warnings: <b>{count}/{MAX_WARNINGS}</b> — {remaining} warning(s) left before mute."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass
            asyncio.create_task(log_to_owner(
                context.bot,
                f"⚠️ <b>Bad Word — Warning</b>\n"
                f"👤 User: {user.mention_html()}\n"
                f"📊 Warnings: {count}/{MAX_WARNINGS}\n"
                f"🤖 Bot: Message deleted + warned\n"
                f"💬 Group: {group_title}",
            ))
        return

    if is_admin:
        return

    if not await check_member(context.bot, user_id):
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=full_mute_permissions(),
                until_date=int(time.time()) + 300,
            )
        except Exception:
            pass
        try:
            await update.message.delete()
        except Exception:
            pass

        keyboard = [
            [InlineKeyboardButton("JOIN OUR CHANNEL ❤️‍🩹", url=CHANNEL_LINK)],
            [InlineKeyboardButton("UNMUTE ME I HAVE JOINED ✅", callback_data="check")],
        ]
        try:
            sent = await context.bot.send_message(
                chat_id=chat_id,
                text=(
                    f"{user.mention_html()}, you must join our channel to chat here 📱\n\n"
                    f"Action: Muted 🔇 for 5 minutes"
                ),
                reply_markup=InlineKeyboardMarkup(keyboard),
                parse_mode="HTML",
            )
        except Exception:
            return
        vkey = (chat_id, sent.message_id)
        verification_targets[vkey] = user_id

        async def auto_delete():
            await asyncio.sleep(300)
            try:
                await sent.delete()
            except Exception:
                pass
            verification_targets.pop(vkey, None)

        asyncio.create_task(auto_delete())


async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.message or not query.from_user:
        return

    user_id = query.from_user.id
    chat_id = query.message.chat.id

    try:
        clicker_member = await context.bot.get_chat_member(chat_id, user_id)
        if clicker_member.status in ("administrator", "creator"):
            await query.answer("❌ This button is not for you!", show_alert=True)
            return
    except Exception:
        pass

    vkey = (chat_id, query.message.message_id)
    intended_user = verification_targets.get(vkey)

    # If intended_user is None the bot restarted and lost state — only the
    # channel-member check below still applies, but block wrong-user presses
    # when we DO know who the button was for.
    if intended_user is not None and user_id != intended_user:
        await query.answer("❌ This button is not for you!", show_alert=True)
        return
    # After restart verification_targets is empty; prevent any random user from
    # claiming an orphaned button on behalf of the muted person.
    if intended_user is None and not await check_member(context.bot, user_id):
        await query.answer("YOU HAVE NOT JOINED THE CHANNEL ❌")
        return

    if await check_member(context.bot, user_id):
        try:
            await context.bot.restrict_chat_member(
                chat_id=chat_id,
                user_id=user_id,
                permissions=locked_permissions(locked=False),
            )
        except Exception:
            pass
        try:
            await query.message.delete()
        except Exception:
            pass
        verification_targets.pop(vkey, None)
        await query.answer("Verified! You can chat now ✅")
        try:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"{query.from_user.mention_html()} YOU HAVE VERIFIED AND UNMUTE!\nWELCOME TO THE CHAT ❤️‍🩹",
                parse_mode="HTML",
            )
        except Exception:
            pass
    else:
        await query.answer("YOU HAVE NOT JOINED THE CHANNEL ❌")


async def handle_edited_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.edited_message
    if not message:
        return
    # Only act in groups
    if message.chat.type not in ("group", "supergroup"):
        return
    # Skip channel-linked posts (sender_chat is set when a channel posts/edits in a linked group)
    if message.sender_chat:
        return
    user = message.from_user
    # Skip non-real users: bots, anonymous admins, service accounts
    if not user or user.is_bot:
        return
    chat_id = message.chat.id
    # Only act in groups explicitly toggled ON in /editgroup
    if chat_id not in anti_edit_chats:
        return
    # Skip admins/creators
    try:
        member = await context.bot.get_chat_member(chat_id, user.id)
        if member.status in ("administrator", "creator"):
            return
    except Exception:
        return
    # Skip whitelisted users
    if user.id in whitelisted.get(chat_id, set()):
        return
    try:
        await message.delete()
    except Exception:
        pass
    group_title = message.chat.title or str(chat_id)
    asyncio.create_task(log_to_owner(
        context.bot,
        f"✏️ <b>Message Edited</b>\n"
        f"👤 User: {user.mention_html()}\n"
        f"🤖 Bot: Deleted edited message\n"
        f"💬 Group: {group_title}",
    ))
    try:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"{user.mention_html()} your message has been deleted because it contained edited content ❌",
            parse_mode="HTML",
        )
    except Exception:
        pass


async def warnings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await require_admin(update, context):
        return

    if context.args and context.args[0].lower() == "reset":
        if not update.message.reply_to_message:
            await update.message.reply_text(
                "↩️ Reply to a user's message and type /warnings reset to clear their warnings."
            )
            return
        target = update.message.reply_to_message.from_user
        if not target or target.is_bot:
            await update.message.reply_text("❌ Cannot manage warnings for that user.")
            return
        key = (chat_id, target.id)
        user_warnings.pop(key, None)
        save_state()
        await update.message.reply_text(
            f"✅ Warnings cleared for {target.mention_html()}.", parse_mode="HTML"
        )
        group_title = update.effective_chat.title or str(chat_id)
        admin = update.effective_user
        asyncio.create_task(log_to_owner(
            context.bot,
            f"🔄 <b>Warnings Reset</b>\n"
            f"👮 Admin: {admin.mention_html()}\n"
            f"👤 User: {target.mention_html()}\n"
            f"🤖 Bot: Warnings cleared (0/3)\n"
            f"💬 Group: {group_title}",
        ))
        return

    warned = {
        uid: count
        for (cid, uid), count in user_warnings.items()
        if cid == chat_id and count > 0
    }
    if not warned:
        await update.message.reply_text("✅ No warnings in this chat.")
        return

    lines = ["⚠️ <b>Active Warnings</b>\n"]
    for uid, count in warned.items():
        try:
            m = await context.bot.get_chat_member(chat_id, uid)
            name = m.user.mention_html()
        except Exception:
            name = f"User {uid}"
        lines.append(f"{name} — 📊 {count}/{MAX_WARNINGS} warnings")

    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def whitelist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    if not await require_admin(update, context):
        return

    if not context.args:
        wl = whitelisted.get(chat_id, set())
        if not wl:
            await update.message.reply_text("📋 No whitelisted users in this chat.")
            return
        lines = ["📋 <b>Whitelisted Users</b>\n"]
        for uid in wl:
            try:
                m = await context.bot.get_chat_member(chat_id, uid)
                lines.append(f"• {m.user.mention_html()}")
            except Exception:
                lines.append(f"• User {uid}")
        await update.message.reply_text("\n".join(lines), parse_mode="HTML")
        return

    action = context.args[0].lower()
    if action not in ("add", "remove"):
        await update.message.reply_text(
            "Usage:\n"
            "/whitelist — list whitelisted users\n"
            "/whitelist add @username — whitelist by mention\n"
            "/whitelist remove @username — remove by mention\n"
            "/whitelist add — reply to a user to whitelist them\n"
            "/whitelist remove — reply to a user to remove from whitelist"
        )
        return

    # --- Resolve target user ---
    target = None
    target_name = None

    # 1) Prefer reply
    if update.message.reply_to_message:
        target_user = update.message.reply_to_message.from_user
        if not target_user or target_user.is_bot:
            await update.message.reply_text("❌ Cannot whitelist that user.")
            return
        target = target_user.id
        target_name = target_user.mention_html()

    # 2) @mention in command args
    if target is None:
        # Check entities for a text_mention (user with no username)
        for entity in update.message.entities or []:
            if entity.type == "text_mention" and entity.user:
                target = entity.user.id
                target_name = entity.user.mention_html()
                break

        # Check args for @username string
        if target is None and len(context.args) >= 2:
            raw = context.args[1].lstrip("@")
            try:
                member = await context.bot.get_chat_member(chat_id, f"@{raw}")
                target = member.user.id
                target_name = member.user.mention_html()
            except Exception:
                await update.message.reply_text(
                    f"❌ Could not find user <code>@{raw}</code> in this group.",
                    parse_mode="HTML",
                )
                return

    if target is None:
        await update.message.reply_text(
            f"↩️ Reply to a message or mention a user:\n"
            f"<code>/whitelist {action} @username</code>",
            parse_mode="HTML",
        )
        return

    if chat_id not in whitelisted:
        whitelisted[chat_id] = set()

    group_title = update.effective_chat.title or str(chat_id)
    admin = update.effective_user
    if action == "add":
        whitelisted[chat_id].add(target)
        save_state()
        await update.message.reply_text(
            f"✅ {target_name} has been whitelisted. They are now exempt from all protections.",
            parse_mode="HTML",
        )
        asyncio.create_task(log_to_owner(
            context.bot,
            f"📋 <b>Whitelisted</b>\n"
            f"👮 Admin: {admin.mention_html()}\n"
            f"👤 User: {target_name}\n"
            f"🤖 Bot: Exempt from all protections\n"
            f"💬 Group: {group_title}",
        ))
    else:
        whitelisted[chat_id].discard(target)
        save_state()
        await update.message.reply_text(
            f"✅ {target_name} has been removed from the whitelist.",
            parse_mode="HTML",
        )
        asyncio.create_task(log_to_owner(
            context.bot,
            f"📋 <b>Whitelist Removed</b>\n"
            f"👮 Admin: {admin.mention_html()}\n"
            f"👤 User: {target_name}\n"
            f"🤖 Bot: Protections re-enabled\n"
            f"💬 Group: {group_title}",
        ))


async def addword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /addword <word>")
        return
    word = " ".join(context.args).lower().strip()
    BAD_WORDS.add(word)
    save_state()
    await update.message.reply_text(
        f'✅ Added "<code>{word}</code>" to the bad words list.', parse_mode="HTML"
    )
    group_title = update.effective_chat.title or str(update.effective_chat.id)
    admin = update.effective_user
    asyncio.create_task(log_to_owner(
        context.bot,
        f"🚫 <b>Bad Word Added</b>\n"
        f"👮 Admin: {admin.mention_html()}\n"
        f"📝 Word: <code>{word}</code>\n"
        f"🤖 Bot: Word added to filter\n"
        f"💬 Group: {group_title}",
    ))


async def removeword_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not context.args:
        await update.message.reply_text("Usage: /removeword <word>")
        return
    word = " ".join(context.args).lower().strip()
    if word in BAD_WORDS:
        BAD_WORDS.discard(word)
        save_state()
        await update.message.reply_text(
            f'✅ Removed "<code>{word}</code>" from the bad words list.',
            parse_mode="HTML",
        )
        group_title = update.effective_chat.title or str(update.effective_chat.id)
        admin = update.effective_user
        asyncio.create_task(log_to_owner(
            context.bot,
            f"🚫 <b>Bad Word Removed</b>\n"
            f"👮 Admin: {admin.mention_html()}\n"
            f"📝 Word: <code>{word}</code>\n"
            f"🤖 Bot: Word removed from filter\n"
            f"💬 Group: {group_title}",
        ))
    else:
        await update.message.reply_text(
            f'⚠️ "<code>{word}</code>" is not in the bad words list.', parse_mode="HTML"
        )


async def antiedit_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Group admin: /antiedit on|off — toggle edited-message deletion for this chat."""
    chat_id = update.effective_chat.id
    # /antiedit is now managed via /editgroup owner DM panel
    await update.message.reply_text(
        "✏️ Anti-edit is now managed per group from the owner DM panel.\n"
        "Ask the owner to use <code>/editgroup</code> to toggle it for this group.",
        parse_mode="HTML",
    )


async def listwords_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    custom = BAD_WORDS - DEFAULT_BAD_WORDS
    if not custom:
        await update.message.reply_text("📋 No custom bad words added yet.")
        return
    lines = ["📋 <b>Custom Bad Words</b>\n"] + [
        f"• <code>{w}</code>" for w in sorted(custom)
    ]
    await update.message.reply_text("\n".join(lines), parse_mode="HTML")


async def mute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Reply to a user's message to mute them.")
        return
    target = update.message.reply_to_message.from_user
    if not target or target.is_bot:
        await update.message.reply_text("❌ Cannot mute that user.")
        return
    chat_id = update.effective_chat.id

    # Prevent muting admins/creators
    try:
        target_member = await context.bot.get_chat_member(chat_id, target.id)
        if target_member.status in ("administrator", "creator"):
            await update.message.reply_text("❌ Cannot mute an admin or group creator.")
            return
    except Exception:
        pass

    duration = 3600  # default 60 minutes
    if context.args:
        try:
            duration = int(context.args[0]) * 60
        except ValueError:
            await update.message.reply_text(
                "⚠️ Invalid duration. Usage: /mute [minutes]"
            )
            return

    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target.id,
            permissions=full_mute_permissions(),
            until_date=int(time.time()) + duration,
        )
        await update.message.reply_text(
            f"🔇 {target.mention_html()} has been muted for {duration // 60} minute(s).",
            parse_mode="HTML",
        )
        admin = update.effective_user
        group_title = update.effective_chat.title or str(chat_id)
        asyncio.create_task(log_to_owner(
            context.bot,
            f"🔇 <b>Admin Mute</b>\n"
            f"👮 Admin: {admin.mention_html()}\n"
            f"👤 User: {target.mention_html()}\n"
            f"🤖 Bot: Muted for {duration // 60} minute(s)\n"
            f"💬 Group: {group_title}",
        ))
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to mute: {e}")


async def unmute_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("↩️ Reply to a user's message to unmute them.")
        return
    target = update.message.reply_to_message.from_user
    if not target or target.is_bot:
        await update.message.reply_text("❌ Cannot unmute that user.")
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.restrict_chat_member(
            chat_id=chat_id,
            user_id=target.id,
            permissions=locked_permissions(locked=False),
        )
        await update.message.reply_text(
            f"🔊 {target.mention_html()} has been unmuted.",
            parse_mode="HTML",
        )
        group_title = update.effective_chat.title or str(chat_id)
        admin = update.effective_user
        asyncio.create_task(log_to_owner(
            context.bot,
            f"🔊 <b>Admin Unmute</b>\n"
            f"👮 Admin: {admin.mention_html()}\n"
            f"👤 User: {target.mention_html()}\n"
            f"🤖 Bot: Unmuted (all permissions restored)\n"
            f"💬 Group: {group_title}",
        ))
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to unmute: {e}")


async def lock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat_id, permissions=locked_permissions(locked=True)
        )
        await update.message.reply_text("🔒 Chat locked. Only text messages allowed.")
        admin = update.effective_user
        group_title = update.effective_chat.title or str(chat_id)
        asyncio.create_task(log_to_owner(
            context.bot,
            f"🔒 <b>Chat Locked</b>\n"
            f"👮 Admin: {admin.mention_html()}\n"
            f"🤖 Bot: Locked chat (text only)\n"
            f"💬 Group: {group_title}",
        ))
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to lock chat: {e}")


async def unlock_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await require_admin(update, context):
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.set_chat_permissions(
            chat_id=chat_id, permissions=locked_permissions(locked=False)
        )
        await update.message.reply_text("🔓 Chat unlocked. All media allowed.")
        admin = update.effective_user
        group_title = update.effective_chat.title or str(chat_id)
        asyncio.create_task(log_to_owner(
            context.bot,
            f"🔓 <b>Chat Unlocked</b>\n"
            f"👮 Admin: {admin.mention_html()}\n"
            f"🤖 Bot: Unlocked chat (all media)\n"
            f"💬 Group: {group_title}",
        ))
    except Exception as e:
        await update.message.reply_text(f"❌ Failed to unlock chat: {e}")


async def custom_bot_info_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Shows the bot customization service page."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("📩 Contact @FARAZXBACKUP", url="https://t.me/FARAZXBACKUP")],
        [InlineKeyboardButton("🔙 Back", callback_data="start_back")],
    ]
    await query.edit_message_text(
        "🤖 <b>PROFESSIONAL BOT CUSTOMIZATION</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n\n"
        "Want a powerful Telegram bot built specifically for <b>your</b> group or business?\n\n"
        "✅ <b>What you get:</b>\n"
        "┣ 🌙 Night Mode & Auto-Lock\n"
        "┣ 🛡️ Anti-Spam & Anti-Slang\n"
        "┣ ✏️ Anti-Edit Protection\n"
        "┣ ⚠️ Warning & Mute System\n"
        "┣ 📋 Bad Word Filter\n"
        "┣ 📡 Activity & DM Logs\n"
        "┣ 🎛️ Full Owner Control Panel\n"
        "┣ 📢 Broadcast to All Groups\n"
        "┣ 🔐 Whitelist & Permissions\n"
        "┗ ⚙️ Any custom feature you need\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "💼 <b>Fast delivery · Affordable · Fully private</b>\n\n"
        "📩 DM <b>@FARAZXBACKUP</b> to get started!",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def start_back_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Returns the user to the /start message from the custom bot info page."""
    query = update.callback_query
    await query.answer()
    keyboard = [
        [InlineKeyboardButton("JOIN OUR CHANNEL ❤️‍🩹", url=CHANNEL_LINK)],
        [InlineKeyboardButton("━━━━ 🔽 SERVICES 🔽 ━━━━", callback_data="pnl_noop")],
        [
            InlineKeyboardButton("📢 Main Channel", url="https://t.me/+i7HqaczkTtJmODc1"),
            InlineKeyboardButton("💬 Group Chat", url="https://t.me/BGMIPOPULARITYSELLING00"),
        ],
        [
            InlineKeyboardButton("🤝 Escrow", url="https://t.me/ESCROWXHUB"),
            InlineKeyboardButton("🆘 Help", url="https://t.me/FARAZUMAR"),
        ],
        [InlineKeyboardButton("🤖 Want a Customized Bot Like This?", callback_data="custom_bot_info")],
    ]
    await query.edit_message_text(
        "👋 <b>Group Moderation Bot</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "<b>Features</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🌙 Night Mode\n"
        "🚫 Bad Word Filter\n"
        "🛡️ Anti-Spam\n"
        "📱 Channel Verification Gate\n"
        "✏️ Edited Message Deletion\n"
        "💾 Persistent Data\n\n"
        "📢 Must join our channel to chat in the group!\n\n"
        "⚡ <b>POWERED BY @FARAZUMAR</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Owner in DM → open control panel directly
    if is_owner_dm(update):
        log_to_dm(f"🚀 <b>Owner used /start</b>\n👤 @{OWNER_USERNAME}\n🤖 Bot: Control panel opened")
        text, markup = await _build_main_panel()
        await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")
        return

    keyboard = [
        [InlineKeyboardButton("JOIN OUR CHANNEL ❤️‍🩹", url=CHANNEL_LINK)],
        [InlineKeyboardButton("━━━━ 🔽 SERVICES 🔽 ━━━━", callback_data="pnl_noop")],
        [
            InlineKeyboardButton("📢 Main Channel", url="https://t.me/+i7HqaczkTtJmODc1"),
            InlineKeyboardButton("💬 Group Chat", url="https://t.me/BGMIPOPULARITYSELLING00"),
        ],
        [
            InlineKeyboardButton("🤝 Escrow", url="https://t.me/ESCROWXHUB"),
            InlineKeyboardButton("🆘 Help", url="https://t.me/FARAZUMAR"),
        ],
        [InlineKeyboardButton("🤖 Want a Customized Bot Like This?", callback_data="custom_bot_info")],
    ]
    await update.message.reply_text(
        "👋 <b>Group Moderation Bot</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "<b>Features</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🌙 Night Mode\n"
        "🚫 Bad Word Filter\n"
        "🛡️ Anti-Spam\n"
        "📱 Channel Verification Gate\n"
        "✏️ Edited Message Deletion\n"
        "💾 Persistent Data\n\n"
        "📢 Must join our channel to chat in the group!\n\n"
        "⚡ <b>POWERED BY @FARAZUMAR</b>",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="HTML",
    )


def is_owner(update: Update) -> bool:
    """Returns True if the message is from the owner (by username)."""
    if not update.effective_user:
        return False
    uname = (update.effective_user.username or "").lower()
    return bool(OWNER_USERNAME) and uname == OWNER_USERNAME


def is_owner_dm(update: Update) -> bool:
    """Returns True if the message is from the owner in a private chat."""
    if not update.effective_chat:
        return False
    return is_owner(update) and update.effective_chat.type == "private"


async def owner_dm_required(update: Update) -> bool:
    """
    Checks if the update is an owner DM.
    If in private chat but NOT the owner — sends a restriction notice.
    Returns True if allowed, False otherwise.
    """
    if is_owner_dm(update):
        return True
    if update.effective_chat and update.effective_chat.type == "private":
        await update.message.reply_text(
            "🚫 <b>Access Restricted</b>\n\n"
            "This command is reserved for the bot owner only.\n\n"
            "⚡ <b>POWERED BY @FARAZUMAR</b>",
            parse_mode="HTML",
        )
    return False


async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat = update.effective_chat

    # Allow from DM if owner
    if chat.type == "private":
        if not await owner_dm_required(update):
            return
        total_warnings = sum(cnt for cnt in user_warnings.values())
        total_wl = sum(len(v) for v in whitelisted.values())
        custom_words = len(BAD_WORDS - DEFAULT_BAD_WORDS)
        nm_status = "🟢 ON" if night_mode_enabled else "🔴 OFF"
        lock_t = f"{LOCK_HOUR:02d}:{LOCK_MINUTE:02d}"
        unlock_t = f"{UNLOCK_HOUR:02d}:{UNLOCK_MINUTE:02d}"
        await update.message.reply_text(
            "📊 <b>Bot Status (Owner View)</b>\n\n"
            f"🌙 Night Mode: <b>{nm_status}</b>\n"
            f"🔒 Lock time: <b>{lock_t} IST</b>\n"
            f"🔓 Unlock time: <b>{unlock_t} IST</b>\n"
            f"🛡️ Anti-Slang: <b>{'🟢 ON' if anti_slang_enabled else '🔴 OFF'}</b>\n"
            f"🏠 Groups monitored: <b>{len(known_chats)}</b>\n"
            f"⚠️ Total warnings: <b>{total_warnings}</b>\n"
            f"📋 Total whitelisted: <b>{total_wl}</b>\n"
            f"🚫 Custom bad words: <b>{custom_words}</b>\n"
            f"📖 Total bad words: <b>{len(BAD_WORDS)}</b>\n\n"
            "⚡ <b>POWERED BY @FARAZUMAR</b>",
            parse_mode="HTML",
        )
        return

    # In group — creator only
    try:
        member = await context.bot.get_chat_member(chat.id, user_id)
    except Exception:
        return
    if member.status != "creator":
        try:
            await update.message.delete()
        except Exception:
            pass
        return

    total_warnings = sum(
        cnt for (cid, uid), cnt in user_warnings.items() if cid == chat.id
    )
    wl_count = len(whitelisted.get(chat.id, set()))
    custom_words = len(BAD_WORDS - DEFAULT_BAD_WORDS)
    nm_status = "🟢 ON" if night_mode_enabled else "🔴 OFF"

    await update.message.reply_text(
        "📊 <b>Bot Status</b>\n\n"
        f"🌙 Night Mode: <b>{nm_status}</b>\n"
        f"🛡️ Anti-Slang: <b>{'🟢 ON' if anti_slang_enabled else '🔴 OFF'}</b>\n"
        f"🏠 Groups monitored: <b>{len(known_chats)}</b>\n"
        f"⚠️ Active warnings: <b>{total_warnings}</b>\n"
        f"📋 Whitelisted users: <b>{wl_count}</b>\n"
        f"🚫 Custom bad words: <b>{custom_words}</b>\n"
        f"📖 Total bad words: <b>{len(BAD_WORDS)}</b>\n\n"
        "⚡ <b>POWERED BY @FARAZUMAR</b>",
        parse_mode="HTML",
    )


async def owner_nightmode_dm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner-only /nightmode from DM."""
    global night_mode_enabled
    if not await owner_dm_required(update):
        return

    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        status = "🟢 ON" if night_mode_enabled else "🔴 OFF"
        await update.message.reply_text(
            f"🌙 Night Mode is currently {status}\n\n"
            "Usage:\n/nightmode on\n/nightmode off"
        )
        return

    if args[0].lower() == "off":
        night_mode_enabled = False
        save_state()
        await update.message.reply_text("🔴 Night Mode disabled across all groups.")
    else:
        night_mode_enabled = True
        save_state()
        await update.message.reply_text("🟢 Night Mode enabled across all groups.")


async def settime_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner DM only: /settime lock HH:MM  or  /settime unlock HH:MM"""
    global LOCK_HOUR, LOCK_MINUTE, UNLOCK_HOUR, UNLOCK_MINUTE
    if not await owner_dm_required(update):
        return

    if not context.args or len(context.args) < 2:
        await update.message.reply_text(
            "Usage:\n"
            "/settime lock HH:MM\n"
            "/settime unlock HH:MM\n\n"
            f"Current lock: <b>{LOCK_HOUR:02d}:{LOCK_MINUTE:02d} IST</b>\n"
            f"Current unlock: <b>{UNLOCK_HOUR:02d}:{UNLOCK_MINUTE:02d} IST</b>",
            parse_mode="HTML",
        )
        return

    which = context.args[0].lower()
    if which not in ("lock", "unlock"):
        await update.message.reply_text(
            "❌ Use 'lock' or 'unlock'.\nExample: /settime lock 23:00"
        )
        return

    try:
        h, m = map(int, context.args[1].split(":"))
        if not (0 <= h <= 23 and 0 <= m <= 59):
            raise ValueError
    except ValueError:
        await update.message.reply_text(
            "❌ Invalid time. Use HH:MM format (e.g. 01:00)."
        )
        return

    if which == "lock":
        LOCK_HOUR, LOCK_MINUTE = h, m
        save_state()
        await update.message.reply_text(
            f"🔒 Lock time updated to <b>{h:02d}:{m:02d} IST</b>.",
            parse_mode="HTML",
        )
    else:
        UNLOCK_HOUR, UNLOCK_MINUTE = h, m
        save_state()
        await update.message.reply_text(
            f"🔓 Unlock time updated to <b>{h:02d}:{m:02d} IST</b>.",
            parse_mode="HTML",
        )


async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner DM only: /broadcast <message> — sends to all known groups."""
    if not await owner_dm_required(update):
        return

    if not context.args:
        await update.message.reply_text(
            "Usage: /broadcast <message>\n\n"
            f"Will send to <b>{len(known_chats)}</b> group(s).",
            parse_mode="HTML",
        )
        return

    text = " ".join(context.args)
    success, failed = 0, 0
    for chat_id in list(known_chats):
        try:
            await context.bot.send_message(chat_id=chat_id, text=text)
            success += 1
        except Exception:
            failed += 1

    await update.message.reply_text(
        f"📢 Broadcast complete.\n✅ Sent: <b>{success}</b> · ❌ Failed: <b>{failed}</b>",
        parse_mode="HTML",
    )


async def myid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Anyone can use this in DM to get their Telegram user ID."""
    uid = update.effective_user.id
    await update.message.reply_text(
        f"🆔 Your Telegram User ID: <code>{uid}</code>",
        parse_mode="HTML",
    )


async def commands_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner DM only: shows all available commands."""
    if not await owner_dm_required(update):
        return

    await update.message.reply_text(
        "📋 <b>All Bot Commands</b>\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "👑 <b>Owner DM Only</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "<code>/panel</code> — 🎛️ full control panel (all settings in one place)\n"
        "<code>/status</code> — full bot stats\n"
        "<code>/nightmode on|off</code> — toggle night mode\n"
        "<code>/nightgroup</code> — manage which groups get night mode\n"
        "<code>/slanggroup</code> — manage anti-slang & warn per group\n"
        "<code>/editgroup</code> — manage anti-edit per group\n"
        "<code>/settime lock HH:MM</code> — change auto-lock time\n"
        "<code>/settime unlock HH:MM</code> — change auto-unlock time\n"
        "<code>/broadcast message</code> — send to all groups\n"
        "<code>/commands</code> — show this list\n"
        "<code>/restart</code> — restart the bot\n"
        "<code>/antislang on|off</code> — toggle bad-word filter\n"
        "<code>/myid</code> — get your Telegram ID\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🔧 <b>Admin (Group)</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "<code>/nightmode on|off</code> — toggle night mode\n"
        "<code>/lock</code> — lock chat (text only)\n"
        "<code>/unlock</code> — unlock chat\n"
        "<code>/mute [minutes]</code> — mute a user (reply)\n"
        "<code>/unmute</code> — unmute a user (reply)\n"
        "<code>/warnings</code> — list active warnings\n"
        "<code>/warnings reset</code> — clear warnings (reply)\n"
        "<code>/whitelist</code> — list whitelisted users\n"
        "<code>/whitelist add</code> — exempt a user (reply)\n"
        "<code>/whitelist remove</code> — remove exemption (reply)\n"
        "<code>/addword word</code> — add bad word\n"
        "<code>/removeword word</code> — remove bad word\n"
        "<code>/listwords</code> — list custom bad words\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "👤 <b>Creator (Group)</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "<code>/status</code> — group-level bot stats\n\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🌐 <b>Everyone</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "<code>/start</code> — bot info + channel link\n"
        "<code>/myid</code> — get your Telegram ID\n\n"
        "⚡ <b>POWERED BY @FARAZUMAR</b>",
        parse_mode="HTML",
    )


async def restart_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner DM only: restarts the bot."""
    if not await owner_dm_required(update):
        return
    await update.message.reply_text(
        "🔄 Restarting bot... I'll be back in a few seconds."
    )
    await asyncio.sleep(1)
    os.execv(sys.executable, [sys.executable] + sys.argv)


async def antislang_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner DM only: /antislang on|off — toggle the bad-word filter."""
    global anti_slang_enabled
    if not await owner_dm_required(update):
        return
    args = context.args
    if not args or args[0].lower() not in ("on", "off"):
        status = "🟢 ON" if anti_slang_enabled else "🔴 OFF"
        await update.message.reply_text(
            f"🛡️ Anti-Slang filter is currently <b>{status}</b>\n"
            "Usage: /antislang on|off",
            parse_mode="HTML",
        )
        return
    anti_slang_enabled = args[0].lower() == "on"
    save_state()
    status = "🟢 ON" if anti_slang_enabled else "🔴 OFF"
    await update.message.reply_text(
        f"🛡️ Anti-Slang filter turned <b>{status}</b>.",
        parse_mode="HTML",
    )




async def _build_nightgroup_panel(bot) -> tuple[str, InlineKeyboardMarkup]:
    """Build the text + keyboard for the night-group management panel."""
    if not known_chats:
        text = (
            "🌙 <b>Night Mode Group Manager</b>\n\n"
            "No groups are known yet.\n\n"
            "To add your existing groups manually, send:\n"
            "<code>/addgroup &lt;chat_id&gt;</code>\n\n"
            "To find a group's chat ID, forward any message from that group to @userinfobot, "
            "or add @RawDataBot to the group and send any message.\n\n"
            "New groups will also be detected automatically once any member sends a message."
        )
        return text, InlineKeyboardMarkup([
            [InlineKeyboardButton("🔄 Refresh", callback_data="ng_refresh")],
            [InlineKeyboardButton("🔙 Main Panel", callback_data="pnl_home")],
        ])

    enabled_count = len(night_mode_chats)
    nm_label = f"🌙 Master: {'🟢 ON  →  tap to turn OFF' if night_mode_enabled else '🔴 OFF  →  tap to turn ON'}"
    header = (
        "🌙 <b>Night Mode Group Manager</b>\n"
        f"Lock: <b>{LOCK_HOUR:02d}:{LOCK_MINUTE:02d}</b> · "
        f"Unlock: <b>{UNLOCK_HOUR:02d}:{UNLOCK_MINUTE:02d} IST</b>\n\n"
        "Tap a group to toggle night mode on/off for it.\n"
        f"<b>{enabled_count}</b> group(s) scheduled\n"
    )

    rows = [[InlineKeyboardButton(nm_label, callback_data="pnl_nm_toggle")]]
    for cid in sorted(known_chats):
        try:
            chat = await bot.get_chat(cid)
            title = (chat.title or str(cid))[:32]
        except Exception:
            title = str(cid)

        active = cid in night_mode_chats
        label = f"{'✅' if active else '❌'} {title}"
        rows.append([InlineKeyboardButton(label, callback_data=f"ng_toggle:{cid}")])

    rows.append([InlineKeyboardButton("🔄 Refresh", callback_data="ng_refresh")])
    rows.append([InlineKeyboardButton("🔙 Main Panel", callback_data="pnl_home")])
    return header, InlineKeyboardMarkup(rows)


async def nightgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner DM only: /nightgroup — interactive panel to manage which groups get night mode."""
    if not await owner_dm_required(update):
        return
    text, markup = await _build_nightgroup_panel(context.bot)
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def nightgroup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles ng_toggle:<chat_id> and ng_refresh button presses from the owner DM panel."""
    query = update.callback_query
    if not query or not query.from_user:
        return

    # Only the owner may interact
    uname = (query.from_user.username or "").lower()
    if not OWNER_USERNAME or uname != OWNER_USERNAME:
        await query.answer("❌ Only the bot owner can use this.", show_alert=True)
        return

    data = query.data or ""

    if data == "ng_refresh":
        await query.answer("Refreshed ✅")
        text, markup = await _build_nightgroup_panel(context.bot)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass
        return

    if data.startswith("ng_toggle:"):
        raw_id = data.split(":", 1)[1]
        try:
            cid = int(raw_id)
        except ValueError:
            await query.answer("Invalid group ID.", show_alert=True)
            return

        if cid in night_mode_chats:
            night_mode_chats.discard(cid)
            state = "OFF ❌"
        else:
            night_mode_chats.add(cid)
            state = "ON ✅"

        save_state()
        await query.answer(f"Night mode {state}")
        log_to_dm(f"🌙 <b>Owner toggled Night Mode per group</b>\n🏘️ Group ID: <code>{cid}</code>\n🤖 Bot: Night Mode {state}")
        text, markup = await _build_nightgroup_panel(context.bot)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass


async def _build_slanggroup_panel(bot) -> tuple[str, InlineKeyboardMarkup]:
    """Build the text + keyboard for the per-group anti-slang management panel."""
    if not known_chats:
        text = (
            "🛡️ <b>Anti-Slang Group Manager</b>\n\n"
            "No groups are known yet.\n\n"
            "Use <code>/addgroup &lt;chat_id&gt;</code> to add one manually, "
            "or have any member send a message in a group the bot is in."
        )
        return text, InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="sg_refresh")]])

    as_count = len(anti_slang_chats)
    header = (
        "🛡️ <b>Anti-Slang Group Manager</b>\n\n"
        "Toggle <b>Anti-Slang</b> (delete bad words) and <b>Warn</b> (issue warnings + mute) per group.\n"
        f"Anti-Slang active in <b>{as_count}</b> group(s).\n"
    )

    as_master_label = f"🛡️ Master Filter: {'🟢 ON  →  tap to turn OFF' if anti_slang_enabled else '🔴 OFF  →  tap to turn ON'}"
    rows = [
        [InlineKeyboardButton(as_master_label, callback_data="pnl_as_toggle")],
    ]
    for cid in sorted(known_chats):
        try:
            chat = await bot.get_chat(cid)
            title = (chat.title or str(cid))[:28]
        except Exception:
            title = str(cid)

        as_on = cid in anti_slang_chats
        warn_on = cid in anti_slang_warn_chats
        rows.append([
            InlineKeyboardButton(
                f"{'✅' if as_on else '❌'} 🛡️ {title}",
                callback_data=f"sg_as:{cid}"
            ),
            InlineKeyboardButton(
                f"⚠️ Warn {'✅' if warn_on else '❌'}",
                callback_data=f"sg_warn:{cid}"
            ),
        ])

    rows.append([InlineKeyboardButton("🔄 Refresh", callback_data="sg_refresh")])
    rows.append([InlineKeyboardButton("🔙 Main Panel", callback_data="pnl_home")])
    return header, InlineKeyboardMarkup(rows)


async def slanggroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner DM only: /slanggroup — interactive panel to manage per-group anti-slang."""
    if not await owner_dm_required(update):
        return
    text, markup = await _build_slanggroup_panel(context.bot)
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def slanggroup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles sg_as:<id>, sg_warn:<id>, and sg_refresh button presses."""
    query = update.callback_query
    if not query or not query.from_user:
        return

    uname = (query.from_user.username or "").lower()
    if not OWNER_USERNAME or uname != OWNER_USERNAME:
        await query.answer("❌ Only the bot owner can use this.", show_alert=True)
        return

    data = query.data or ""

    if data == "sg_refresh":
        await query.answer("Refreshed ✅")
        text, markup = await _build_slanggroup_panel(context.bot)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass
        return

    if data.startswith("sg_as:") or data.startswith("sg_warn:"):
        kind, raw_id = data.split(":", 1)
        try:
            cid = int(raw_id)
        except ValueError:
            await query.answer("Invalid group ID.", show_alert=True)
            return

        if kind == "sg_as":
            if cid in anti_slang_chats:
                anti_slang_chats.discard(cid)
                anti_slang_warn_chats.discard(cid)  # warn only valid when anti-slang ON
                state = "Anti-Slang OFF ❌"
            else:
                anti_slang_chats.add(cid)
                state = "Anti-Slang ON ✅"
        else:  # sg_warn
            if cid not in anti_slang_chats:
                await query.answer("⚠️ Enable Anti-Slang for this group first.", show_alert=True)
                return
            if cid in anti_slang_warn_chats:
                anti_slang_warn_chats.discard(cid)
                state = "Warn OFF ❌"
            else:
                anti_slang_warn_chats.add(cid)
                state = "Warn ON ✅"

        save_state()
        await query.answer(state)
        log_to_dm(f"🛡️ <b>Owner toggled per-group setting</b>\n🏘️ Group ID: <code>{cid}</code>\n🤖 Bot: {state}")
        text, markup = await _build_slanggroup_panel(context.bot)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass


async def _build_editgroup_panel(bot) -> tuple[str, InlineKeyboardMarkup]:
    """Build the text + keyboard for the per-group anti-edit management panel."""
    if not known_chats:
        text = (
            "✏️ <b>Anti-Edit Group Manager</b>\n\n"
            "No groups are known yet.\n\n"
            "Use <code>/addgroup &lt;chat_id&gt;</code> to add one manually."
        )
        return text, InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Refresh", callback_data="ae_refresh")]])

    ae_count = len(anti_edit_chats)
    header = (
        "✏️ <b>Anti-Edit Group Manager</b>\n\n"
        "Toggle anti-edit (delete edited messages) per group.\n"
        f"Active in <b>{ae_count}</b> group(s).\n"
    )

    rows = []
    for cid in sorted(known_chats):
        try:
            chat = await bot.get_chat(cid)
            title = (chat.title or str(cid))[:32]
        except Exception:
            title = str(cid)

        active = cid in anti_edit_chats
        label = f"{'✅' if active else '❌'} ✏️ {title}"
        rows.append([InlineKeyboardButton(label, callback_data=f"ae_toggle:{cid}")])

    rows.append([InlineKeyboardButton("🔄 Refresh", callback_data="ae_refresh")])
    rows.append([InlineKeyboardButton("🔙 Main Panel", callback_data="pnl_home")])
    return header, InlineKeyboardMarkup(rows)


async def editgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner DM only: /editgroup — interactive panel to manage per-group anti-edit."""
    if not await owner_dm_required(update):
        return
    text, markup = await _build_editgroup_panel(context.bot)
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def editgroup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles ae_toggle:<chat_id> and ae_refresh button presses."""
    query = update.callback_query
    if not query or not query.from_user:
        return

    uname = (query.from_user.username or "").lower()
    if not OWNER_USERNAME or uname != OWNER_USERNAME:
        await query.answer("❌ Only the bot owner can use this.", show_alert=True)
        return

    data = query.data or ""

    if data == "ae_refresh":
        await query.answer("Refreshed ✅")
        text, markup = await _build_editgroup_panel(context.bot)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass
        return

    if data.startswith("ae_toggle:"):
        raw_id = data.split(":", 1)[1]
        try:
            cid = int(raw_id)
        except ValueError:
            await query.answer("Invalid group ID.", show_alert=True)
            return

        if cid in anti_edit_chats:
            anti_edit_chats.discard(cid)
            state = "Anti-Edit OFF ❌"
        else:
            anti_edit_chats.add(cid)
            state = "Anti-Edit ON ✅"

        save_state()
        await query.answer(state)
        log_to_dm(f"✏️ <b>Owner toggled Anti-Edit per group</b>\n🏘️ Group ID: <code>{cid}</code>\n🤖 Bot: {state}")
        text, markup = await _build_editgroup_panel(context.bot)
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass


def _build_logs_hub() -> tuple[str, InlineKeyboardMarkup]:
    """Logs hub — entry point showing both log categories."""
    notify_label = "🔔 Live Notify: 🟢 ON" if activity_log_enabled else "🔕 Live Notify: 🔴 OFF"
    text = (
        "📡 <b>LOGS HUB</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🏘️ Group events: <b>{len(activity_log)}</b>\n"
        f"💬 DM interactions: <b>{len(dm_log)}</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "Choose a section to browse:"
    )
    keyboard = [
        [InlineKeyboardButton(notify_label, callback_data="pnl_log_notify")],
        [
            InlineKeyboardButton(f"🏘️ Group Log ({len(activity_log)})", callback_data="pnl_grplog"),
            InlineKeyboardButton(f"💬 DM Log ({len(dm_log)})", callback_data="pnl_dmlog"),
        ],
        [InlineKeyboardButton("🔙 Main Panel", callback_data="pnl_home")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def _build_paginated_log(
    entries_source: list[dict],
    title: str,
    page: int,
    prev_cb: str,
    next_cb: str,
    clear_cb: str,
    back_cb: str,
) -> tuple[str, InlineKeyboardMarkup]:
    """Generic paginated log viewer used by both mod log and DM log."""
    entries = list(reversed(entries_source))  # newest first
    total = len(entries)
    total_pages = max(1, (total + LOGS_PER_PAGE - 1) // LOGS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    slice_ = entries[page * LOGS_PER_PAGE : (page + 1) * LOGS_PER_PAGE]

    if not slice_:
        body = "Nothing recorded yet."
    else:
        lines = []
        for e in slice_:
            plain = re.sub(r"<[^>]+>", "", e["msg"]).replace("\n", " · ")
            lines.append(f"[{e['ts']}] {plain}")
        body = "\n".join(lines)

    text = (
        f"{title}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"{body}\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"Page {page + 1}/{total_pages}  ·  {total} entry/entries"
    )
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton("◀ Prev", callback_data=f"{prev_cb}{page - 1}"))
    nav.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="pnl_noop"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("Next ▶", callback_data=f"{next_cb}{page + 1}"))

    keyboard: list[list[InlineKeyboardButton]] = []
    if nav:
        keyboard.append(nav)
    keyboard.append([InlineKeyboardButton("🗑️ Clear", callback_data=clear_cb)])
    keyboard.append([InlineKeyboardButton("🔙 Logs Hub", callback_data=back_cb)])
    return text, InlineKeyboardMarkup(keyboard)


def _build_group_log_panel(page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    return _build_paginated_log(
        activity_log, "🏘️ <b>GROUP LOG</b>", page,
        "pnl_grplog_p", "pnl_grplog_p", "pnl_grplog_clear", "pnl_logs",
    )


def _build_dm_log_panel(page: int = 0) -> tuple[str, InlineKeyboardMarkup]:
    return _build_paginated_log(
        dm_log, "💬 <b>DM INTERACTIONS</b>", page,
        "pnl_dmlog_p", "pnl_dmlog_p", "pnl_dmlog_clear", "pnl_logs",
    )


async def _build_main_panel() -> tuple[str, InlineKeyboardMarkup]:
    nm = "🟢 ON" if night_mode_enabled else "🔴 OFF"
    log_status = "🟢 ON" if activity_log_enabled else "🔴 OFF"
    total_warnings = sum(user_warnings.values())
    total_wl = sum(len(v) for v in whitelisted.values())
    custom_words = len(BAD_WORDS - DEFAULT_BAD_WORDS)
    text = (
        "🤖 <b>BOT CONTROL PANEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🌙 Night Mode: <b>{nm}</b>  ·  {len(night_mode_chats)} grp(s)\n"
        f"🛡️ Anti-Slang: <b>{'🟢' if anti_slang_enabled else '🔴'}</b>  ·  {len(anti_slang_chats)} grp(s)  ·  ⚠️ Warn: {len(anti_slang_warn_chats)} grp(s)\n"
        f"✏️ Anti-Edit: {len(anti_edit_chats)} grp(s)  ·  👥 Groups: <b>{len(known_chats)}</b>\n"
        f"🕐 Lock <b>{LOCK_HOUR:02d}:{LOCK_MINUTE:02d}</b> · Unlock <b>{UNLOCK_HOUR:02d}:{UNLOCK_MINUTE:02d} IST</b>\n"
        f"📡 Activity Log: <b>{log_status}</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "📊 <b>Stats</b>\n"
        f"⚠️ Slang Warn: <b>{'🟢 ON' if anti_slang_warn_chats else '🔴 OFF'}</b>  ·  {len(anti_slang_warn_chats)} grp(s)\n"
        f"🔢 Active warnings: <b>{total_warnings}</b>\n"
        f"📋 Whitelisted users: <b>{total_wl}</b>\n"
        f"🚫 Custom bad words: <b>{custom_words}</b>  ·  Total: <b>{len(BAD_WORDS)}</b>\n"
        f"🏘️ Group log: <b>{len(activity_log)}</b>  ·  💬 DM log: <b>{len(dm_log)}</b>\n"
        "━━━━━━━━━━━━━━━━━━━"
    )
    keyboard = [
        [
            InlineKeyboardButton("🌙 Night Mode", callback_data="pnl_night"),
            InlineKeyboardButton("🛡️ Anti-Slang", callback_data="pnl_slang"),
        ],
        [
            InlineKeyboardButton("✏️ Anti-Edit", callback_data="pnl_edit"),
            InlineKeyboardButton("📋 Bad Words", callback_data="pnl_words"),
        ],
        [
            InlineKeyboardButton("⏰ Timings", callback_data="pnl_time"),
            InlineKeyboardButton("📊 Stats", callback_data="pnl_stats"),
        ],
        [
            InlineKeyboardButton("👥 Groups", callback_data="pnl_grps"),
            InlineKeyboardButton("📢 Broadcast", callback_data="pnl_bcast"),
        ],
        [InlineKeyboardButton(f"📡 Logs  🏘️{len(activity_log)} grp · 💬{len(dm_log)} DM", callback_data="pnl_logs")],
        [InlineKeyboardButton("🔴 Restart Bot", callback_data="pnl_restart")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="pnl_home")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def _build_timings_panel() -> tuple[str, InlineKeyboardMarkup]:
    text = (
        "⏰ <b>TIMINGS</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🔒 Night Lock: <b>{LOCK_HOUR:02d}:{LOCK_MINUTE:02d} IST</b>\n"
        f"🔓 Morning Unlock: <b>{UNLOCK_HOUR:02d}:{UNLOCK_MINUTE:02d} IST</b>\n\n"
        "Use − / + to adjust. Hours ±1, Minutes ±15."
    )
    keyboard = [
        [InlineKeyboardButton(f"── 🔒 Lock: {LOCK_HOUR:02d}:{LOCK_MINUTE:02d} ──", callback_data="pnl_noop")],
        [
            InlineKeyboardButton("−1h", callback_data="pnl_t_lh-"),
            InlineKeyboardButton("+1h", callback_data="pnl_t_lh+"),
            InlineKeyboardButton("−15m", callback_data="pnl_t_lm-"),
            InlineKeyboardButton("+15m", callback_data="pnl_t_lm+"),
        ],
        [InlineKeyboardButton(f"── 🔓 Unlock: {UNLOCK_HOUR:02d}:{UNLOCK_MINUTE:02d} ──", callback_data="pnl_noop")],
        [
            InlineKeyboardButton("−1h", callback_data="pnl_t_uh-"),
            InlineKeyboardButton("+1h", callback_data="pnl_t_uh+"),
            InlineKeyboardButton("−15m", callback_data="pnl_t_um-"),
            InlineKeyboardButton("+15m", callback_data="pnl_t_um+"),
        ],
        [InlineKeyboardButton("🔙 Main Panel", callback_data="pnl_home")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


def _build_badwords_panel() -> tuple[str, InlineKeyboardMarkup]:
    custom = sorted(BAD_WORDS - DEFAULT_BAD_WORDS)
    text = (
        "📋 <b>BAD WORDS</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"Built-in words: <b>{len(DEFAULT_BAD_WORDS)}</b>\n"
        f"Custom words: <b>{len(custom)}</b>\n\n"
        + ("Tap ❌ Remove to delete a custom word:\n" if custom else "No custom words added yet.\n")
    )
    rows = []
    for i, word in enumerate(custom):
        rows.append([
            InlineKeyboardButton(f"📝 {word}", callback_data="pnl_noop"),
            InlineKeyboardButton("❌ Remove", callback_data=f"pnl_w_rm:{i}"),
        ])
    rows.append([InlineKeyboardButton("➕ Add Word", callback_data="pnl_w_add")])
    rows.append([InlineKeyboardButton("🔙 Main Panel", callback_data="pnl_home")])
    return text, InlineKeyboardMarkup(rows)


async def _build_groups_panel(bot) -> tuple[str, InlineKeyboardMarkup]:
    lines = [f"👥 <b>GROUPS</b>\n━━━━━━━━━━━━━━━━━━━\nKnown: <b>{len(known_chats)}</b>\n"]
    for cid in sorted(known_chats):
        try:
            chat = await bot.get_chat(cid)
            title = chat.title or str(cid)
        except Exception:
            title = str(cid)
        lines.append(f"• {title}  <code>{cid}</code>")
    text = "\n".join(lines)
    keyboard = [
        [InlineKeyboardButton("➕ Add Group by ID", callback_data="pnl_grp_add")],
        [InlineKeyboardButton("🔄 Refresh", callback_data="pnl_grps")],
        [InlineKeyboardButton("🔙 Main Panel", callback_data="pnl_home")],
    ]
    return text, InlineKeyboardMarkup(keyboard)


async def _build_stats_panel(bot=None) -> tuple[str, InlineKeyboardMarkup]:
    total_warnings = sum(user_warnings.values())
    total_wl = sum(len(v) for v in whitelisted.values())
    custom_words = len(BAD_WORDS - DEFAULT_BAD_WORDS)
    nm = "🟢 ON" if night_mode_enabled else "🔴 OFF"
    slang = "🟢 ON" if anti_slang_enabled else "🔴 OFF"
    warn_status = "🟢 ON" if anti_slang_warn_chats else "🔴 OFF"

    # Build per-group breakdown
    group_lines = []
    for cid in sorted(known_chats):
        # Try to get group name
        name = str(cid)
        if bot:
            try:
                chat = await bot.get_chat(cid)
                name = chat.title or str(cid)
            except Exception:
                pass
        night   = "🟢" if cid in night_mode_chats else "🔴"
        slang_g = "🟢" if cid in anti_slang_chats else "🔴"
        warn_g  = "🟢" if cid in anti_slang_warn_chats else "🔴"
        edit_g  = "🟢" if cid in anti_edit_chats else "🔴"
        warns   = sum(v for (c, u), v in user_warnings.items() if c == cid)
        group_lines.append(
            f"<b>{name}</b>\n"
            f"  🌙{night} 🛡️{slang_g} ⚠️{warn_g} ✏️{edit_g}  |  🔢 Warns: {warns}"
        )

    groups_block = "\n".join(group_lines) if group_lines else "No groups registered yet."

    text = (
        "📊 <b>BOT STATS</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"🌙 Night Mode: <b>{nm}</b>  ·  {len(night_mode_chats)} grp(s)\n"
        f"🛡️ Anti-Slang: <b>{slang}</b>  ·  {len(anti_slang_chats)} grp(s)\n"
        f"⚠️ Slang Warn: <b>{warn_status}</b>  ·  {len(anti_slang_warn_chats)} grp(s)\n"
        f"✏️ Anti-Edit: <b>{len(anti_edit_chats)}</b> grp(s)  ·  👥 Total groups: <b>{len(known_chats)}</b>\n"
        f"🔢 Active warnings: <b>{total_warnings}</b>  ·  📋 Whitelisted: <b>{total_wl}</b>\n"
        f"🚫 Custom words: <b>{custom_words}</b>  ·  📖 Total: <b>{len(BAD_WORDS)}</b>\n"
        f"🕐 Lock <b>{LOCK_HOUR:02d}:{LOCK_MINUTE:02d}</b> · Unlock <b>{UNLOCK_HOUR:02d}:{UNLOCK_MINUTE:02d} IST</b>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "🏘️ <b>Per-Group Status</b>\n"
        "<i>🌙Night  🛡️Slang  ⚠️Warn  ✏️Edit</i>\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        f"{groups_block}"
    )
    keyboard = [[InlineKeyboardButton("🔙 Main Panel", callback_data="pnl_home")]]
    return text, InlineKeyboardMarkup(keyboard)


async def dm_logger(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log every DM message from non-owner users into the activity log."""
    if not update.message or not update.effective_user:
        return
    user = update.effective_user
    # Skip owner — their DM actions are already tracked via panel
    if OWNER_USERNAME and (user.username or "").lower() == OWNER_USERNAME.lower():
        return
    content = update.message.text or update.message.caption or ""
    if not content and update.message.sticker:
        content = f"[Sticker: {update.message.sticker.emoji or ''}]"
    elif not content and update.message.photo:
        content = "[Photo]"
    elif not content and update.message.video:
        content = "[Video]"
    elif not content and update.message.document:
        content = "[File]"
    elif not content and update.message.voice:
        content = "[Voice]"
    elif not content:
        content = "[Media]"
    preview = (content[:80] + "…") if len(content) > 80 else content
    name = user.full_name or "Unknown"
    uname = f"@{user.username}" if user.username else f"ID:{user.id}"
    # Write to the dedicated DM log (not the moderation log)
    ts = datetime.now(IST).strftime("%H:%M")
    entry = {"ts": ts, "msg": f"💬 <b>DM from {uname}</b>\n👤 {name}\n📝 {preview}"}
    dm_log.append(entry)
    if len(dm_log) > MAX_LOG_SIZE:
        dm_log.pop(0)
    # Ping owner in DM if live notify is on — send directly, not via log_to_owner (which would pollute group log)
    if activity_log_enabled and OWNER_USERNAME:
        async def _send_dm_notify(bot, msg):
            try:
                await bot.send_message(chat_id=f"@{OWNER_USERNAME}", text=msg, parse_mode="HTML")
            except Exception:
                pass
        asyncio.create_task(_send_dm_notify(context.bot, entry["msg"]))


async def panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner DM only: /panel — open the main control panel."""
    if not await owner_dm_required(update):
        return
    log_to_dm(f"🎛️ <b>Owner opened /panel</b>\n👤 @{OWNER_USERNAME}")
    text, markup = await _build_main_panel()
    await update.message.reply_text(text, reply_markup=markup, parse_mode="HTML")


async def panel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles all pnl_* callbacks for the owner control panel."""
    global LOCK_HOUR, LOCK_MINUTE, UNLOCK_HOUR, UNLOCK_MINUTE, night_mode_enabled
    query = update.callback_query
    if not query or not query.from_user:
        return

    data = query.data or ""

    # No-op buttons (display-only labels) — allowed for everyone, no owner check
    if data == "pnl_noop":
        await query.answer("👇 Services are shown below", show_alert=False)
        return

    uname = (query.from_user.username or "").lower()
    if not OWNER_USERNAME or uname != OWNER_USERNAME:
        await query.answer("❌ Only the bot owner can use this.", show_alert=True)
        return

    uid = query.from_user.id

    async def edit(text, markup):
        try:
            await query.edit_message_text(text, reply_markup=markup, parse_mode="HTML")
        except Exception:
            pass

    # Main panel / back
    if data == "pnl_home":
        await query.answer()
        text, markup = await _build_main_panel()
        await edit(text, markup)
        return

    # Stats
    if data == "pnl_stats":
        await query.answer()
        text, markup = await _build_stats_panel(bot=context.bot)
        await edit(text, markup)
        return

    # Night Mode section
    if data == "pnl_night":
        await query.answer()
        text, markup = await _build_nightgroup_panel(context.bot)
        await edit(text, markup)
        return

    if data == "pnl_nm_toggle":
        night_mode_enabled = not night_mode_enabled
        save_state()
        status = "ON 🟢" if night_mode_enabled else "OFF 🔴"
        await query.answer(f"Night Mode {status}")
        log_to_dm(f"🌙 <b>Owner toggled Night Mode</b>\n🤖 Bot: Night Mode {status}")
        text, markup = await _build_nightgroup_panel(context.bot)
        await edit(text, markup)
        return

    # Anti-Slang section
    if data == "pnl_slang":
        await query.answer()
        text, markup = await _build_slanggroup_panel(context.bot)
        await edit(text, markup)
        return

    # Anti-Edit section
    if data == "pnl_edit":
        await query.answer()
        text, markup = await _build_editgroup_panel(context.bot)
        await edit(text, markup)
        return

    # Bad Words section
    if data == "pnl_words":
        await query.answer()
        text, markup = _build_badwords_panel()
        await edit(text, markup)
        return

    if data == "pnl_w_add":
        panel_state[uid] = "addword"
        await query.answer()
        await edit(
            "📋 <b>ADD BAD WORD</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Type the word you want to add and send it now.",
            InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pnl_cancel")]])
        )
        return

    if data.startswith("pnl_w_rm:"):
        idx_str = data.split(":", 1)[1]
        try:
            idx = int(idx_str)
        except ValueError:
            await query.answer("Invalid.", show_alert=True)
            return
        custom = sorted(BAD_WORDS - DEFAULT_BAD_WORDS)
        if 0 <= idx < len(custom):
            word = custom[idx]
            BAD_WORDS.discard(word)
            save_state()
            await query.answer(f"Removed: {word} ✅")
            log_to_dm(f"🗑️ <b>Owner removed bad word via panel</b>\n📝 Word: <code>{word}</code>\n🤖 Bot: Word removed from filter")
        else:
            await query.answer("Word not found.", show_alert=True)
            return
        text, markup = _build_badwords_panel()
        await edit(text, markup)
        return

    # Timings section
    if data == "pnl_time":
        await query.answer()
        text, markup = _build_timings_panel()
        await edit(text, markup)
        return

    if data.startswith("pnl_t_"):
        key = data[6:]
        if key == "lh+":
            LOCK_HOUR = (LOCK_HOUR + 1) % 24
        elif key == "lh-":
            LOCK_HOUR = (LOCK_HOUR - 1) % 24
        elif key == "lm+":
            LOCK_MINUTE = (LOCK_MINUTE + 15) % 60
        elif key == "lm-":
            LOCK_MINUTE = (LOCK_MINUTE - 15) % 60
        elif key == "uh+":
            UNLOCK_HOUR = (UNLOCK_HOUR + 1) % 24
        elif key == "uh-":
            UNLOCK_HOUR = (UNLOCK_HOUR - 1) % 24
        elif key == "um+":
            UNLOCK_MINUTE = (UNLOCK_MINUTE + 15) % 60
        elif key == "um-":
            UNLOCK_MINUTE = (UNLOCK_MINUTE - 15) % 60
        save_state()
        await query.answer("Updated ✅")
        log_to_dm(
            f"⏰ <b>Owner changed timings</b>\n"
            f"🔒 Lock: {LOCK_HOUR:02d}:{LOCK_MINUTE:02d}\n"
            f"🔓 Unlock: {UNLOCK_HOUR:02d}:{UNLOCK_MINUTE:02d}\n"
            f"🤖 Bot: Night schedule updated"
        )
        text, markup = _build_timings_panel()
        await edit(text, markup)
        return

    # Stats section
    if data == "pnl_grps":
        await query.answer()
        text, markup = await _build_groups_panel(context.bot)
        await edit(text, markup)
        return

    if data == "pnl_grp_add":
        panel_state[uid] = "addgroup"
        await query.answer()
        await edit(
            "👥 <b>ADD GROUP</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "Send the group's <b>chat ID</b> (e.g. <code>-1001234567890</code>).\n\n"
            "To find it: forward any message from the group to @userinfobot.",
            InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pnl_cancel")]])
        )
        return

    # Broadcast section
    if data == "pnl_bcast":
        panel_state[uid] = "broadcast"
        await query.answer()
        await edit(
            "📢 <b>BROADCAST</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            f"Will send to <b>{len(known_chats)}</b> group(s).\n\n"
            "Type and send your broadcast message now.",
            InlineKeyboardMarkup([[InlineKeyboardButton("❌ Cancel", callback_data="pnl_cancel")]])
        )
        return

    # ── Logs hub ──────────────────────────────────────────────────
    if data == "pnl_logs":
        await query.answer()
        text, markup = _build_logs_hub()
        await edit(text, markup)
        return

    # Live notify toggle (shown in hub)
    if data == "pnl_log_notify":
        global activity_log_enabled
        activity_log_enabled = not activity_log_enabled
        save_state()
        status = "ON 🟢" if activity_log_enabled else "OFF 🔴"
        await query.answer(f"Live Notify {status}")
        log_to_dm(f"🔔 <b>Owner toggled Live Notify</b>\n🤖 Bot: Live Notify {status}")
        text, markup = _build_logs_hub()
        await edit(text, markup)
        return

    # ── Group log ─────────────────────────────────────────────────
    if data == "pnl_grplog":
        await query.answer()
        text, markup = _build_group_log_panel(0)
        await edit(text, markup)
        return

    if data.startswith("pnl_grplog_p"):
        try:
            page = int(data[len("pnl_grplog_p"):])
        except ValueError:
            page = 0
        await query.answer()
        text, markup = _build_group_log_panel(page)
        await edit(text, markup)
        return

    if data == "pnl_grplog_clear":
        activity_log.clear()
        await query.answer("Group log cleared ✅")
        log_to_dm("🗑️ <b>Owner cleared Group Log</b>\n🤖 Bot: Group log wiped")
        text, markup = _build_group_log_panel(0)
        await edit(text, markup)
        return

    # ── DM interactions log ───────────────────────────────────────
    if data == "pnl_dmlog":
        await query.answer()
        text, markup = _build_dm_log_panel(0)
        await edit(text, markup)
        return

    if data.startswith("pnl_dmlog_p"):
        try:
            page = int(data[len("pnl_dmlog_p"):])
        except ValueError:
            page = 0
        await query.answer()
        text, markup = _build_dm_log_panel(page)
        await edit(text, markup)
        return

    if data == "pnl_dmlog_clear":
        dm_log.clear()
        await query.answer("DM log cleared ✅")
        log_to_dm("🗑️ <b>Owner cleared DM Log</b>\n🤖 Bot: DM log wiped")
        text, markup = _build_dm_log_panel(0)
        await edit(text, markup)
        return

    # Anti-Slang master toggle
    if data == "pnl_as_toggle":
        global anti_slang_enabled
        anti_slang_enabled = not anti_slang_enabled
        save_state()
        status = "ON 🟢" if anti_slang_enabled else "OFF 🔴"
        await query.answer(f"Anti-Slang Filter {status}")
        log_to_dm(f"🛡️ <b>Owner toggled Anti-Slang Master Filter</b>\n🤖 Bot: Anti-Slang Filter {status}")
        text, markup = await _build_slanggroup_panel(context.bot)
        await edit(text, markup)
        return

    # Restart — show confirmation
    if data == "pnl_restart":
        await query.answer()
        await edit(
            "🔴 <b>RESTART BOT</b>\n"
            "━━━━━━━━━━━━━━━━━━━\n"
            "The bot will go offline for a few seconds then come back.\n\n"
            "Are you sure?",
            InlineKeyboardMarkup([
                [
                    InlineKeyboardButton("✅ Yes, Restart", callback_data="pnl_restart_do"),
                    InlineKeyboardButton("❌ Cancel", callback_data="pnl_home"),
                ]
            ])
        )
        return

    # Restart confirmed
    if data == "pnl_restart_do":
        await query.answer("Restarting... 🔄")
        log_to_dm(f"🔄 <b>Owner triggered Bot Restart</b>\n👤 @{OWNER_USERNAME}\n🤖 Bot: Restarting now...")
        await edit(
            "🔄 Bot is restarting...\nI'll be back in a few seconds.",
            InlineKeyboardMarkup([])
        )
        await asyncio.sleep(1)
        os.execv(sys.executable, [sys.executable] + sys.argv)
        return

    # Cancel any pending state
    if data == "pnl_cancel":
        panel_state.pop(uid, None)
        await query.answer("Cancelled ✅")
        text, markup = await _build_main_panel()
        await edit(text, markup)
        return

    await query.answer()


async def panel_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handles text input from the owner in DM when the panel is waiting for a value."""
    if not update.message or not update.effective_user:
        return
    if update.effective_chat.type != "private":
        return
    uname = (update.effective_user.username or "").lower()
    if not OWNER_USERNAME or uname != OWNER_USERNAME:
        return

    uid = update.effective_user.id
    state = panel_state.get(uid)
    if not state:
        return

    text = (update.message.text or "").strip()
    panel_state.pop(uid, None)

    if state == "broadcast":
        success, failed = 0, 0
        for chat_id in list(known_chats):
            try:
                await context.bot.send_message(chat_id=chat_id, text=text)
                success += 1
            except Exception:
                failed += 1
        result_text = f"📢 Broadcast done!\n✅ Sent: <b>{success}</b>  ·  ❌ Failed: <b>{failed}</b>"
        await update.message.reply_text(result_text, parse_mode="HTML")
        log_to_dm(
            f"📢 <b>Owner broadcast message</b>\n"
            f"💬 Message: {text[:100]}{'…' if len(text) > 100 else ''}\n"
            f"🤖 Bot: Sent ✅ {success}  ·  Failed ❌ {failed}"
        )
        ptext, markup = await _build_main_panel()
        await update.message.reply_text(ptext, reply_markup=markup, parse_mode="HTML")

    elif state == "addword":
        word = text.lower().strip()
        if word:
            BAD_WORDS.add(word)
            save_state()
            await update.message.reply_text(f"✅ Added: <code>{word}</code>", parse_mode="HTML")
            log_to_dm(f"➕ <b>Owner added bad word via panel</b>\n📝 Word: <code>{word}</code>\n🤖 Bot: Word added to filter")
            ptext, markup = _build_badwords_panel()
            await update.message.reply_text(ptext, reply_markup=markup, parse_mode="HTML")
        else:
            await update.message.reply_text("⚠️ Empty word, nothing added.")
            log_to_dm("⚠️ <b>Owner tried to add empty bad word</b>\n🤖 Bot: Nothing added")

    elif state == "addgroup":
        try:
            cid = int(text)
            known_chats.add(cid)
            save_state()
            await update.message.reply_text(f"✅ Group <code>{cid}</code> added.", parse_mode="HTML")
            log_to_dm(f"➕ <b>Owner added group via panel</b>\n🏘️ Group ID: <code>{cid}</code>\n🤖 Bot: Group registered")
            ptext, markup = await _build_groups_panel(context.bot)
            await update.message.reply_text(ptext, reply_markup=markup, parse_mode="HTML")
        except ValueError:
            await update.message.reply_text(
                "⚠️ Invalid chat ID. Must be a number like <code>-1001234567890</code>.",
                parse_mode="HTML",
            )
            log_to_dm(f"⚠️ <b>Owner sent invalid group ID</b>\n📝 Input: <code>{text}</code>\n🤖 Bot: Invalid — not a number")


async def bot_added_to_group(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Auto-register a group into known_chats when the bot is added to it."""
    result = update.my_chat_member
    if not result:
        return
    chat = result.chat
    if chat.type not in ("group", "supergroup"):
        return
    new_status = result.new_chat_member.status
    if new_status in ("member", "administrator"):
        if chat.id not in known_chats:
            known_chats.add(chat.id)
            save_state()
            print(f"[Group] Auto-registered group {chat.id} ({chat.title})")


async def addgroup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Owner DM only: /addgroup <chat_id> — manually register a group into known_chats."""
    if not await owner_dm_required(update):
        return
    if not context.args:
        await update.message.reply_text(
            "Usage: <code>/addgroup &lt;chat_id&gt;</code>\n\n"
            "To find your group's chat ID:\n"
            "• Forward any group message to @userinfobot\n"
            "• Or add @RawDataBot to the group and send any message\n"
            "• Group IDs are negative numbers, e.g. <code>-1001234567890</code>",
            parse_mode="HTML",
        )
        return
    try:
        cid = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ Invalid chat ID. It must be a number like <code>-1001234567890</code>.", parse_mode="HTML")
        return
    try:
        chat = await context.bot.get_chat(cid)
        title = chat.title or str(cid)
    except Exception as e:
        await update.message.reply_text(
            f"❌ Could not fetch that group: <code>{e}</code>\n\n"
            "Make sure the bot is already a member of that group.",
            parse_mode="HTML",
        )
        return
    known_chats.add(cid)
    save_state()
    await update.message.reply_text(
        f"✅ Group <b>{title}</b> (<code>{cid}</code>) added.\n"
        "Now use /nightgroup to toggle night mode for it.",
        parse_mode="HTML",
    )


async def post_init(application):
    load_state()
    asyncio.create_task(night_mode_scheduler(application.bot))
    if OWNER_USERNAME:
        try:
            await application.bot.send_message(
                chat_id=f"@{OWNER_USERNAME}",
                text="✅ Bot is back online and ready!",
            )
        except Exception as e:
            print(f"[Startup] Could not notify owner: {e}")


def main():
    app = (
        ApplicationBuilder()
        .token(BOT_TOKEN)
        .concurrent_updates(True)
        .connection_pool_size(16)
        .read_timeout(10)
        .write_timeout(10)
        .connect_timeout(10)
        .pool_timeout(5)
        .post_init(post_init)
        .build()
    )

    app.add_handler(CommandHandler("start", start_command, filters=REAL_USER))
    app.add_handler(CommandHandler("myid", myid_command, filters=REAL_USER))
    app.add_handler(CommandHandler("commands", commands_command, filters=REAL_USER))
    app.add_handler(CommandHandler("restart", restart_command, filters=REAL_USER))
    app.add_handler(CommandHandler("antislang", antislang_command, filters=REAL_USER))
    app.add_handler(CommandHandler("status", status_command, filters=REAL_USER))
    app.add_handler(CommandHandler("settime", settime_command, filters=REAL_USER))
    app.add_handler(CommandHandler("broadcast", broadcast_command, filters=REAL_USER))
    app.add_handler(
        CommandHandler(
            "nightmode",
            owner_nightmode_dm,
            filters=REAL_USER & filters.ChatType.PRIVATE,
        )
    )
    # Auto-register groups when bot is added to them
    app.add_handler(ChatMemberHandler(bot_added_to_group, ChatMemberHandler.MY_CHAT_MEMBER))
    # /nightgroup and /addgroup are owner DM only
    app.add_handler(CommandHandler("panel", panel_command, filters=REAL_USER & filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("nightgroup", nightgroup_command, filters=REAL_USER & filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("slanggroup", slanggroup_command, filters=REAL_USER & filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("editgroup", editgroup_command, filters=REAL_USER & filters.ChatType.PRIVATE))
    app.add_handler(CommandHandler("addgroup", addgroup_command, filters=REAL_USER & filters.ChatType.PRIVATE))
    app.add_handler(CallbackQueryHandler(panel_callback, pattern="^pnl_"))
    app.add_handler(CallbackQueryHandler(nightgroup_callback, pattern="^ng_"))
    app.add_handler(CallbackQueryHandler(slanggroup_callback, pattern="^sg_"))
    app.add_handler(CallbackQueryHandler(editgroup_callback, pattern="^ae_"))
    app.add_handler(
        MessageHandler(
            REAL_USER & filters.ChatType.PRIVATE & ~filters.COMMAND,
            panel_message_handler,
        )
    )
    # Log all DMs from non-owner users (group=2 runs after all primary handlers)
    app.add_handler(
        MessageHandler(
            REAL_USER & filters.ChatType.PRIVATE & filters.ALL,
            dm_logger,
        ),
        group=2,
    )
    GROUP = REAL_USER & filters.ChatType.GROUPS
    app.add_handler(CommandHandler("lock", lock_command, filters=GROUP))
    app.add_handler(CommandHandler("unlock", unlock_command, filters=GROUP))
    app.add_handler(CommandHandler("mute", mute_command, filters=GROUP))
    app.add_handler(CommandHandler("unmute", unmute_command, filters=GROUP))
    app.add_handler(CommandHandler("warnings", warnings_command, filters=GROUP))
    app.add_handler(CommandHandler("whitelist", whitelist_command, filters=GROUP))
    app.add_handler(CommandHandler("addword", addword_command, filters=GROUP))
    app.add_handler(CommandHandler("removeword", removeword_command, filters=GROUP))
    app.add_handler(CommandHandler("listwords", listwords_command, filters=GROUP))
    app.add_handler(CallbackQueryHandler(custom_bot_info_callback, pattern="^custom_bot_info$"))
    app.add_handler(CallbackQueryHandler(start_back_callback, pattern="^start_back$"))
    app.add_handler(CallbackQueryHandler(button, pattern="^check$"))
    app.add_handler(
        MessageHandler(
            REAL_USER
            & filters.ALL
            & ~filters.COMMAND
            & ~filters.UpdateType.EDITED_MESSAGE,
            check_on_message,
        )
    )
    app.add_handler(
        MessageHandler(
            REAL_USER & filters.UpdateType.EDITED_MESSAGE, handle_edited_message
        ),
        group=1,
    )

    print("[Bot] Starting...")
    app.run_polling(drop_pending_updates=True, poll_interval=0.0, timeout=30)


if __name__ == "__main__":
    main()
