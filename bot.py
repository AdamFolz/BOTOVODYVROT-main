import asyncio
import logging
import os
import time
from collections import defaultdict

from dotenv import load_dotenv
from openai import AsyncOpenAI, AuthenticationError
from telegram import Update
from telegram.constants import ChatType
from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from database import Database
from memory import MemoryManager
from prompts import CORE_STYLE_SYSTEM, FUTURE_PROMPT, SUMMARY_PROMPT
from utils import clean_bot_reply, extract_mentions, is_too_similar, safe_short


load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("predskazbot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip()
DATABASE_PATH = os.getenv("DATABASE_PATH", "predskazbot.sqlite3").strip()
MAX_RECENT_MESSAGES = int(os.getenv("MAX_RECENT_MESSAGES", "80"))
MAX_RECENT_BOT_RESPONSES = int(os.getenv("MAX_RECENT_BOT_RESPONSES", "80"))
REGENERATION_ATTEMPTS = int(os.getenv("REGENERATION_ATTEMPTS", "3"))
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
FUTURE_COOLDOWN_SECONDS = int(os.getenv("FUTURE_COOLDOWN_SECONDS", "20"))
SUMMARY_COOLDOWN_SECONDS = int(os.getenv("SUMMARY_COOLDOWN_SECONDS", "60"))

db = Database(DATABASE_PATH)
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL or None)
memory_manager = MemoryManager(db, openai_client, OPENAI_MODEL)

future_rate_limit: dict[tuple[int, int], float] = defaultdict(float)
summary_rate_limit: dict[int, float] = defaultdict(float)


def user_display_name(update: Update) -> str:
    user = update.effective_user
    if not user:
        return "Неизвестный"
    name = " ".join(part for part in [user.first_name, user.last_name] if part)
    return name or user.username or str(user.id)


def username_of(update: Update) -> str:
    user = update.effective_user
    if not user:
        return ""
    return user.username or ""


def chat_id_of(update: Update) -> int:
    chat = update.effective_chat
    if not chat:
        raise RuntimeError("No chat in update")
    return int(chat.id)


def user_id_of(update: Update) -> int:
    user = update.effective_user
    if not user:
        raise RuntimeError("No user in update")
    return int(user.id)


def is_admin(update: Update) -> bool:
    user = update.effective_user
    return bool(user and ADMIN_USER_ID and user.id == ADMIN_USER_ID)


def check_user_cooldown(
    bucket: dict[tuple[int, int], float],
    chat_id: int,
    user_id: int,
    cooldown_seconds: int,
) -> int:
    now = time.time()
    key = (chat_id, user_id)
    allowed_at = bucket.get(key, 0.0)
    if now < allowed_at:
        return int(allowed_at - now) + 1
    bucket[key] = now + cooldown_seconds
    return 0


def check_chat_cooldown(
    bucket: dict[int, float],
    chat_id: int,
    cooldown_seconds: int,
) -> int:
    now = time.time()
    allowed_at = bucket.get(chat_id, 0.0)
    if now < allowed_at:
        return int(allowed_at - now) + 1
    bucket[chat_id] = now + cooldown_seconds
    return 0


async def safe_send(update: Update, text: str, max_len: int = 3500) -> None:
    chat = update.effective_chat
    if not chat:
        logger.warning("safe_send skipped: no effective chat")
        return

    payload = safe_short(text, max_len)
    try:
        await chat.send_message(payload)
    except RetryAfter as exc:
        logger.warning("Telegram rate limit hit: retry_after=%s", exc.retry_after)
    except (BadRequest, Forbidden, TimedOut):
        logger.exception("Failed to send Telegram message")
    except Exception:
        logger.exception("Unexpected Telegram send failure")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (
        "Я PredskazBot v1. Я запоминаю конфу, строю досье и выдаю предсказания.\n\n"
        "Команды:\n"
        "/future — предсказание\n"
        "/profile — твоё досье\n"
        "/profile @username — досье участника\n"
        "/lore — лор конфы\n"
        "/remember текст — сохранить мем/факт (только админ)\n"
        "/summary — летопись последних событий\n"
        "/whoami — показать user_id/chat_id/admin debug\n"
        "/v2status — проверить, пишет ли v2 storage (только админ)"
    )
    await safe_send(update, text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    chat = update.effective_chat
    user = update.effective_user
    if not chat or not user:
        await safe_send(update, "Не вижу chat/user в update.")
        return

    text = (
        "Диагностика:\n"
        f"user_id: {user.id}\n"
        f"username: @{user.username or ''}\n"
        f"chat_id: {chat.id}\n"
        f"chat_type: {chat.type}\n"
        f"ADMIN_USER_ID: {ADMIN_USER_ID}\n"
        f"is_admin: {is_admin(update)}"
    )
    await safe_send(update, text)


async def v2status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not is_admin(update):
        await safe_send(update, "Эта команда доступна только админу.")
        return
    await safe_send(update, memory_manager.v2_status_text(chat_id_of(update)))


async def remember(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    if not is_admin(update):
        await safe_send(update, "Эта команда доступна только админу.")
        return

    chat_id = chat_id_of(update)
    user_id = user_id_of(update)
    text = update.message.text or ""
    memory_text = text.partition(" ")[2].strip()

    if not memory_text:
        await safe_send(update, "Напиши так: /remember важный мем конфы")
        return

    if len(memory_text) > 500:
        await safe_send(update, "Слишком длинная память. Держи её короткой.")
        return

    try:
        db.add_manual_memory(chat_id, user_id, memory_text)
    except Exception:
        logger.exception("Failed to save manual memory")
        await safe_send(update, "Не получилось сохранить память. Попробуй позже.")
        return

    try:
        memory_manager.record_v2_manual_memory(
            chat_id=chat_id,
            author_user_id=user_id,
            username=username_of(update),
            display_name=user_display_name(update),
            text=memory_text,
        )
    except Exception:
        logger.exception("Failed to save manual memory to v2 storage")

    await safe_send(update, "Запомнил.")


def build_draft_profile_text(chat_id: int, user_id: int) -> str | None:
    messages = db.recent_user_messages(chat_id, user_id, 8)
    if not messages:
        return None

    display_name = messages[-1]["display_name"] or str(user_id)
    username = messages[-1]["username"] or ""
    header = f"Черновое досье: {display_name}"
    if username:
        header += f" (@{username})"

    lines = [
        header,
        f"Сообщений в памяти: минимум {len(messages)}",
        "LLM-профиль ещё не собран, но сырые сообщения уже сохраняются.",
        "Последние реплики:",
    ]
    for row in messages[-5:]:
        lines.append(f"- {safe_short(row['text'], 180)}")
    return "\n".join(lines)


async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    chat_id = chat_id_of(update)
    target_user_id = user_id_of(update)

    if context.args:
        raw = context.args[0].strip()
        if raw.startswith("@"):
            row = db.get_user_by_username(chat_id, raw)
            if not row:
                await safe_send(update, "Я пока не знаю такого персонажа. Пусть напишет что-нибудь в чат.")
                return
            target_user_id = int(row["user_id"])

    v2_profile = memory_manager.build_v2_profile_text(chat_id, target_user_id)
    if v2_profile:
        await safe_send(update, v2_profile)
        return

    row = db.get_user_profile(chat_id, target_user_id)
    if not row:
        draft_profile = build_draft_profile_text(chat_id, target_user_id)
        if draft_profile:
            await safe_send(update, draft_profile)
            return
        await safe_send(
            update,
            "Досье пока пустое. Напиши несколько обычных сообщений в чат — команды не считаются.",
        )
        return

    text = (
        f"Досье: {row['display_name']} (@{row['username']})\n"
        f"Стиль: {row['style_summary']}\n"
        f"Темы: {row['frequent_topics']}\n"
        f"Мемы: {row['personal_memes']}\n"
        f"Ярлыки: {row['soft_labels']}\n"
        f"Активность: {row['energy_level']}/5\n"
        f"Токсичный стиль: {row['toxicity_style']}\n"
        f"Мемность: {row['meme_score']}/5\n"
        f"Ночной режим: {row['night_mode_behavior']}\n"
        f"Уверенность: {row['confidence_score']}"
    )
    await safe_send(update, text)


async def lore(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    chat_id = chat_id_of(update)
    v2_lore = memory_manager.build_v2_lore_text(chat_id)
    if v2_lore:
        await safe_send(update, v2_lore)
        return

    row = db.get_chat_memory(chat_id)
    if not row:
        await safe_send(update, "Лор пока не сформировался. Конфе нужно совершить пару исторических ошибок.")
        return

    text = (
        "Лор конфы:\n"
        f"Настроение: {row['mood_today']}\n"
        f"Хаос: {row['chaos_level']}/5\n"
        f"Тема дня: {row['main_topic_today']}\n"
        f"Главный клоун дня: {row['main_clown_today']}\n"
        f"Мем дня: {row['meme_of_the_day']}\n"
        f"Мемы недели: {row['weekly_memes']}\n"
        f"Драма: {row['recent_drama']}\n"
        f"Фразы: {row['local_phrases']}\n"
        f"Артефакты: {row['sacred_artifacts']}\n"
        f"Мифология: {row['chat_mythology']}"
    )
    await safe_send(update, text)


async def summary(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    chat_id = chat_id_of(update)
    wait_seconds = check_chat_cooldown(summary_rate_limit, chat_id, SUMMARY_COOLDOWN_SECONDS)
    if wait_seconds > 0:
        await safe_send(update, f"Летописец отдыхает. Повтори через {wait_seconds} сек.")
        return

    try:
        await memory_manager.maybe_update_memory(chat_id)
        context_text = memory_manager.build_chat_context(chat_id, 100)

        response = await openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.7,
            messages=[
                {"role": "system", "content": CORE_STYLE_SYSTEM},
                {"role": "user", "content": SUMMARY_PROMPT.format(context=context_text)},
            ],
        )
    except AuthenticationError:
        summary_rate_limit[chat_id] = 0
        logger.error("Summary generation failed: invalid OPENAI_API_KEY")
        await safe_send(update, "OpenAI API key неверный. Обнови OPENAI_API_KEY в .env и перезапусти бота.")
        return
    except Exception:
        summary_rate_limit[chat_id] = 0
        logger.exception("Summary generation failed")
        await safe_send(update, "Летопись не сложилась. Попробуй позже.")
        return

    reply = clean_bot_reply(response.choices[0].message.content or "")
    if not reply:
        reply = "Летопись не сложилась. Видимо, конфа сегодня превзошла письменность."

    try:
        db.add_bot_response(chat_id, None, "summary", reply)
        memory_manager.record_v2_bot_response(chat_id=chat_id, user_id=None, command="summary", response_text=reply)
    except Exception:
        logger.exception("Failed to save summary response")

    await safe_send(update, reply)


async def future(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    chat_id = chat_id_of(update)
    user_id = user_id_of(update)

    wait_seconds = check_user_cooldown(
        future_rate_limit,
        chat_id,
        user_id,
        FUTURE_COOLDOWN_SECONDS,
    )
    if wait_seconds > 0:
        await safe_send(update, f"Оракул устал именно от тебя. Повтори через {wait_seconds} сек.", max_len=1000)
        return

    try:
        await memory_manager.maybe_update_memory(chat_id)

        context_text = memory_manager.build_context_for_user(chat_id, user_id, MAX_RECENT_MESSAGES)
        previous = db.recent_bot_responses(chat_id, MAX_RECENT_BOT_RESPONSES)

        last_reason = ""
        chosen = ""

        for _attempt in range(REGENERATION_ATTEMPTS):
            extra = ""
            if last_reason:
                extra = (
                    "\n\nПредыдущая попытка была отклонена: "
                    f"{last_reason}. Напиши иначе, с другим началом, другим ритмом и другой шуткой."
                )

            response = await openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                temperature=0.95,
                messages=[
                    {"role": "system", "content": CORE_STYLE_SYSTEM},
                    {"role": "user", "content": FUTURE_PROMPT.format(context=context_text + extra)},
                ],
            )

            candidate = clean_bot_reply(response.choices[0].message.content or "")
            if not candidate:
                continue

            too_similar, reason = is_too_similar(candidate, previous)
            if not too_similar:
                chosen = candidate
                break

            last_reason = reason
            chosen = candidate

    except AuthenticationError:
        future_rate_limit[(chat_id, user_id)] = 0
        logger.error("Future generation failed: invalid OPENAI_API_KEY")
        await safe_send(update, "OpenAI API key неверный. Обнови OPENAI_API_KEY в .env и перезапусти бота.", max_len=1000)
        return
    except Exception:
        future_rate_limit[(chat_id, user_id)] = 0
        logger.exception("Future generation failed")
        await safe_send(update, "Оракул завис. Попробуй позже.", max_len=1000)
        return

    if not chosen:
        chosen = "Оракул завис. Видимо, будущее посмотрело на конфу и решило не загружаться."

    try:
        db.add_bot_response(chat_id, user_id, "future", chosen)
        memory_manager.record_v2_bot_response(chat_id=chat_id, user_id=user_id, command="future", response_text=chosen)
    except Exception:
        logger.exception("Failed to save future response")

    await safe_send(update, chosen, max_len=1000)


async def store_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.message.text:
        return

    chat = update.effective_chat
    if not chat:
        return

    if chat.type not in {ChatType.GROUP, ChatType.SUPERGROUP, ChatType.PRIVATE}:
        return

    text = update.message.text.strip()
    if not text:
        return

    try:
        chat_id = chat_id_of(update)
        user_id = user_id_of(update)
    except RuntimeError:
        logger.warning("Skipped update without chat or user")
        return

    display_name = user_display_name(update)
    username = username_of(update)
    mentions = extract_mentions(text)

    try:
        db.add_message(chat_id, user_id, username, display_name, text, mentions)
    except Exception:
        logger.exception("Failed to save incoming message")
        return

    try:
        memory_manager.record_v2_message(
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            display_name=display_name,
            text=text,
            mentions=mentions,
            telegram_message_id=update.message.message_id,
            telegram_thread_id=getattr(update.message, "message_thread_id", None),
            chat_title=chat.title or "",
            chat_type=chat.type,
        )
    except Exception:
        logger.exception("Failed to save incoming message to v2 live event log")

    try:
        await memory_manager.maybe_update_memory(chat_id)
    except Exception:
        logger.exception("Memory update failed")


def ensure_event_loop() -> None:
    """Create a main-thread asyncio event loop when Python does not provide one.

    Python 3.14 no longer guarantees that asyncio.get_event_loop() returns a
    default loop. python-telegram-bot still expects one during run_polling(), so
    Windows/local runs need an explicit loop before Application starts polling.
    """
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())


def validate_env() -> None:
    missing = []
    if not TELEGRAM_BOT_TOKEN:
        missing.append("TELEGRAM_BOT_TOKEN")
    if not OPENAI_API_KEY:
        missing.append("OPENAI_API_KEY")
    if missing:
        raise RuntimeError(
            "Missing env variables: "
            + ", ".join(missing)
            + ". Create .env from .env.example and fill the tokens."
        )


def main() -> None:
    validate_env()
    ensure_event_loop()
    db.init()

    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("future", future))
    app.add_handler(CommandHandler("profile", profile))
    app.add_handler(CommandHandler("lore", lore))
    app.add_handler(CommandHandler("remember", remember))
    app.add_handler(CommandHandler("summary", summary))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("v2status", v2status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_message))

    logger.info("PredskazBot started with v2 live storage bridge")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
