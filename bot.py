import asyncio
import io
import json
import logging
import os
import re
import time
from collections import defaultdict
from pathlib import Path

from dotenv import load_dotenv
from openai import AsyncOpenAI, AuthenticationError
from telegram import Update
from telegram.constants import ChatType
from telegram.error import BadRequest, Forbidden, RetryAfter, TimedOut
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from database import Database
from knowledge_base import KnowledgeBase
from memory import MemoryManager
from prompts import ASK_PROMPT, CORE_STYLE_SYSTEM, FUTURE_PROMPT, KB_ANSWER_PROMPT, SUMMARY_PROMPT
from utils import clean_bot_reply, extract_mentions, is_too_similar, safe_short


load_dotenv()

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)

logger = logging.getLogger("predskazbot")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
# KIMI (Moonshot AI) exposes an OpenAI-compatible API. If MOONSHOT_API_KEY is
# set, it's used as the primary provider via OPENAI_BASE_URL/OPENAI_MODEL
# defaults below, without touching the OpenAI-specific env vars.
MOONSHOT_API_KEY = os.getenv("MOONSHOT_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip() or MOONSHOT_API_KEY
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "").strip() or (
    "kimi-k2.7-code" if MOONSHOT_API_KEY else "gpt-4o-mini"
)
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "").strip() or (
    "https://api.kimi.com/coding/v1" if MOONSHOT_API_KEY else ""
)
DATABASE_PATH = os.getenv("DATABASE_PATH", "predskazbot.sqlite3").strip()
MAX_RECENT_MESSAGES = int(os.getenv("MAX_RECENT_MESSAGES", "80"))
MAX_RECENT_BOT_RESPONSES = int(os.getenv("MAX_RECENT_BOT_RESPONSES", "80"))
REGENERATION_ATTEMPTS = int(os.getenv("REGENERATION_ATTEMPTS", "3"))
ADMIN_USER_ID = int(os.getenv("ADMIN_USER_ID", "0"))
FUTURE_COOLDOWN_SECONDS = int(os.getenv("FUTURE_COOLDOWN_SECONDS", "20"))
SUMMARY_COOLDOWN_SECONDS = int(os.getenv("SUMMARY_COOLDOWN_SECONDS", "60"))
KNOWLEDGE_BASE_DIR = os.getenv("KNOWLEDGE_BASE_DIR", "AI_Knowledge_Base").strip()
KB_SEARCH_LIMIT = int(os.getenv("KB_SEARCH_LIMIT", "5"))
ASK_COOLDOWN_SECONDS = int(os.getenv("ASK_COOLDOWN_SECONDS", "15"))
ALLOWED_CHAT_IDS = {
    int(item.strip())
    for item in os.getenv("ALLOWED_CHAT_IDS", "").split(",")
    if item.strip().lstrip("-").isdigit()
}

db = Database(DATABASE_PATH)
openai_client = AsyncOpenAI(api_key=OPENAI_API_KEY, base_url=OPENAI_BASE_URL or None)
memory_manager = MemoryManager(db, openai_client, OPENAI_MODEL)
knowledge_base = KnowledgeBase(KNOWLEDGE_BASE_DIR)

future_rate_limit: dict[tuple[int, int], float] = defaultdict(float)
ask_rate_limit: dict[tuple[int, int], float] = defaultdict(float)
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


def admin_denied_message() -> str:
    if ADMIN_USER_ID <= 0:
        return (
            "Эта команда доступна только админу, а ADMIN_USER_ID не настроен. "
            "Задай его в .env, чтобы включить админ-команды."
        )
    return "Эта команда доступна только админу."


def is_allowed_chat_id(chat_id: int) -> bool:
    return not ALLOWED_CHAT_IDS or int(chat_id) in ALLOWED_CHAT_IDS


def record_audit(
    chat_id: int,
    actor_user_id: int,
    action: str,
    target_user_id: int | None = None,
    details: dict[str, object] | None = None,
) -> None:
    try:
        db.add_audit_log(chat_id, actor_user_id, action, target_user_id=target_user_id, details=details)
    except Exception:
        logger.exception("Failed to write audit log action=%s chat_id=%s", action, chat_id)


async def ensure_allowed_chat(update: Update) -> bool:
    try:
        chat_id = chat_id_of(update)
    except RuntimeError:
        return False
    if is_allowed_chat_id(chat_id):
        return True
    logger.warning("Rejected update from non-allowlisted chat_id=%s", chat_id)
    await safe_send(update, "Этот чат не подключён к боту.")
    return False


def extract_first_url(text: str) -> str:
    match = re.search(r"https?://\S+", text)
    return match.group(0) if match else ""


def build_kb_query(question: str, fallback_context: str = "") -> str:
    combined = (question + "\n" + fallback_context).strip()
    words = re.findall(r"[A-Za-zА-Яа-яЁё0-9_-]{4,}", combined)
    return " ".join(words[:20]) or question.strip()


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
    if not await ensure_allowed_chat(update):
        return
    text = (
        "Я PredskazBot. Я запоминаю конфу, строю досье и выдаю предсказания.\n\n"
        "Команды:\n"
        "/future — предсказание\n"
        "/profile — твоё досье\n"
        "/profile @username — досье участника\n"
        "/lore — лор конфы\n"
        "/remember текст — сохранить мем/факт (только админ)\n"
        "/summary — летопись последних событий\n"
        "/ask вопрос — ответ по чату и базе знаний\n"
        "/kbstatus — статус локальной базы знаний\n"
        "/kbsearch запрос — поиск по локальной базе\n"
        "/kbask вопрос — ответ только по локальной базе\n"
        "/kbimport — импортировать reply/document/url в базу знаний (админ)\n"
        "/health — статус runtime\n"
        "/privacy — что хранится и как удалить данные\n"
        "/export_me — выгрузка твоих данных\n"
        "/delete_me CONFIRM — удалить твои v1-данные\n"
        "/forget <id> — удалить ручную память (админ)\n"
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
        f"is_admin: {is_admin(update)}\n"
        f"chat_allowed: {is_allowed_chat_id(int(chat.id))}"
    )
    await safe_send(update, text)


async def health(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not await ensure_allowed_chat(update):
        return
    chat_id = chat_id_of(update)
    checks: list[str] = []
    checks.append(f"bot: ok")
    checks.append(f"openai_key: {'set' if OPENAI_API_KEY else 'missing'}")
    checks.append(f"admin_user_id: {'set' if ADMIN_USER_ID else 'missing'}")
    checks.append(f"chat_allowed: {is_allowed_chat_id(chat_id)}")
    try:
        db.init()
        checks.append(f"v1_sqlite: ok ({DATABASE_PATH})")
        checks.append(f"v1_messages: {db.count_messages(chat_id)}")
        checks.append(f"v1_users: {db.count_users(chat_id)}")
        checks.append(f"manual_memories: {db.count_manual_memories(chat_id)}")
    except Exception as exc:
        checks.append(f"v1_sqlite: error ({exc})")
    try:
        checks.append(memory_manager.v2_status_text(chat_id))
    except Exception as exc:
        checks.append(f"v2: error ({exc})")
    if knowledge_base.exists():
        status = knowledge_base.status()
        checks.append(
            "kb: ok "
            f"sources={status['sources']} extracts={status['extracts']} "
            f"summaries={status['summaries']} failed={status['failed_imports']}"
        )
    else:
        checks.append(f"kb: missing ({knowledge_base.base_dir})")
    await safe_send(update, "\n".join(checks))


async def privacy(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not await ensure_allowed_chat(update):
        return
    text = (
        "Privacy:\n"
        "- Бот хранит сообщения чата, Telegram user_id, username/display name, ручную память, ответы бота и V2-события.\n"
        "- Эти данные нужны для /future, /profile, /lore, /summary, /ask и V2-памяти.\n"
        "- /export_me выгружает твои v1-данные из текущего чата.\n"
        "- /delete_me CONFIRM удаляет твои v1-сообщения, профиль, отношения, ручную память и ответы из текущего чата.\n"
        "- V2 raw event log считается append-only evidence log; его полная retention/erase policy запланирована в ROADMAP.md.\n"
        "- Админ может удалить ручную память командой /forget <id>."
    )
    await safe_send(update, text)


async def export_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not await ensure_allowed_chat(update):
        return
    chat_id = chat_id_of(update)
    user_id = user_id_of(update)
    payload = db.export_user_data(chat_id, user_id)
    payload_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    filename = f"predskazbot-export-{chat_id}-{user_id}.json"
    try:
        await context.bot.send_document(
            chat_id=chat_id,
            document=io.BytesIO(payload_bytes),
            filename=filename,
            caption="Твой v1-экспорт данных из этого чата.",
        )
    except Exception:
        logger.exception("Failed to send export document")
        await safe_send(update, safe_short(payload_bytes.decode("utf-8", errors="ignore"), 3000))


async def delete_me(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not await ensure_allowed_chat(update):
        return
    confirmation = " ".join(context.args).strip() if context.args else ""
    if confirmation != "CONFIRM":
        await safe_send(update, "Для удаления v1-данных напиши: /delete_me CONFIRM")
        return
    chat_id = chat_id_of(update)
    user_id = user_id_of(update)
    counts = db.delete_user_data(chat_id, user_id)
    record_audit(chat_id, user_id, "delete_me", target_user_id=user_id, details=counts)
    deleted = ", ".join(f"{table}={count}" for table, count in counts.items())
    await safe_send(update, f"v1-данные удалены: {deleted}")


async def forget(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not await ensure_allowed_chat(update):
        return
    if not is_admin(update):
        await safe_send(update, admin_denied_message())
        return
    if not context.args or not context.args[0].isdigit():
        await safe_send(update, "Напиши так: /forget <manual_memory_id>")
        return
    chat_id = chat_id_of(update)
    actor_user_id = user_id_of(update)
    memory_id = int(context.args[0])
    deleted = db.forget_manual_memory(chat_id, memory_id)
    record_audit(
        chat_id,
        actor_user_id,
        "forget_manual_memory",
        details={"manual_memory_id": memory_id, "deleted": deleted},
    )
    await safe_send(update, "Память удалена." if deleted else "Такой ручной памяти в этом чате нет.")


async def v2status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not await ensure_allowed_chat(update):
        return
    if not is_admin(update):
        await safe_send(update, admin_denied_message())
        return
    await safe_send(update, memory_manager.v2_status_text(chat_id_of(update)))


async def kbstatus(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_allowed_chat(update):
        return
    if not knowledge_base.exists():
        await safe_send(update, f"База знаний не найдена по пути: {knowledge_base.base_dir}")
        return
    status = knowledge_base.status()
    recent = knowledge_base.top_summaries(limit=3)
    lines = [
        f"KB path: {knowledge_base.base_dir}",
        f"sources: {status['sources']}",
        f"extracts: {status['extracts']}",
        f"summaries: {status['summaries']}",
        f"wiki: {status['wiki']}",
        f"manifests: {status['manifests']}",
        f"failed_imports: {status['failed_imports']}",
        f"last_import_time: {status['last_import_time'] or 'none'}",
    ]
    if recent:
        lines.append("recent summaries:")
        lines.extend(f"- {item}" for item in recent)
    await safe_send(update, "\n".join(lines))


async def kbsearch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_allowed_chat(update):
        return
    if not knowledge_base.exists():
        await safe_send(update, f"База знаний не найдена по пути: {knowledge_base.base_dir}")
        return
    query = " ".join(context.args).strip() if context.args else ""
    if not query:
        await safe_send(update, "Напиши так: /kbsearch твой запрос")
        return
    hits = knowledge_base.search(query, limit=KB_SEARCH_LIMIT)
    if not hits:
        await safe_send(update, "В локальной базе ничего не найдено.")
        return
    lines = [f"Найдено по запросу: {query}"]
    for hit in hits:
        lines.append(f"- {hit.path}:{hit.line_number} — {safe_short(hit.line, 180)}")
    await safe_send(update, "\n".join(lines))


async def kbask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_allowed_chat(update):
        return
    if not knowledge_base.exists():
        await safe_send(update, f"База знаний не найдена по пути: {knowledge_base.base_dir}")
        return
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await safe_send(update, "Напиши так: /kbask твой вопрос")
        return

    kb_context = knowledge_base.build_context(question, limit=KB_SEARCH_LIMIT, max_chars=5000)
    if not kb_context:
        await safe_send(update, "В локальной базе нет подтверждения по этому вопросу.")
        return

    try:
        response = await openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.2,
            messages=[
                {"role": "system", "content": "Ты отвечаешь только по локальной базе знаний и не выдумываешь факты."},
                {"role": "user", "content": KB_ANSWER_PROMPT.format(question=question, context=kb_context)},
            ],
        )
    except AuthenticationError:
        await safe_send(update, "OpenAI API key неверный. Обнови OPENAI_API_KEY в .env и перезапусти бота.")
        return
    except Exception:
        logger.exception("KB answer generation failed")
        await safe_send(update, "Не получилось ответить по базе знаний. Попробуй позже.")
        return

    reply = clean_bot_reply(response.choices[0].message.content or "")
    if not reply:
        reply = "В локальной базе нет подтверждения по этому вопросу."

    chat_id = chat_id_of(update)
    user_id = user_id_of(update)
    try:
        db.add_bot_response(chat_id, user_id, "kbask", reply)
        memory_manager.record_v2_bot_response(chat_id=chat_id, user_id=user_id, command="kbask", response_text=reply)
    except Exception:
        logger.exception("Failed to save kbask response")

    await safe_send(update, reply, max_len=3500)


async def remember(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not await ensure_allowed_chat(update):
        return

    if not is_admin(update):
        await safe_send(update, admin_denied_message())
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
        v1_saved = False
        db.add_manual_memory(chat_id, user_id, memory_text)
        v1_saved = True
    except Exception:
        v1_saved = False
        logger.exception("Failed to save manual memory")
        if not memory_manager.v2_full_transition and memory_manager.v1_memory_fallback_enabled:
            await safe_send(update, "Не получилось сохранить память. Попробуй позже.")
            return

    try:
        v2_saved = True
        memory_manager.record_v2_manual_memory(
            chat_id=chat_id,
            author_user_id=user_id,
            username=username_of(update),
            display_name=user_display_name(update),
            text=memory_text,
        )
    except Exception:
        v2_saved = False
        logger.exception("Failed to save manual memory to v2 storage")
        if memory_manager.v2_full_transition or not memory_manager.v1_memory_fallback_enabled:
            await safe_send(update, "Не получилось сохранить v2-память. Попробуй позже.")
            return

    if v1_saved and v2_saved:
        record_audit(chat_id, user_id, "remember", details={"text": memory_text})
        await safe_send(update, "Запомнил.")
    elif v2_saved:
        record_audit(chat_id, user_id, "remember_v2_only", details={"text": memory_text})
        await safe_send(update, "Запомнил в v2. Старый SQLite fallback недоступен.")
    else:
        record_audit(chat_id, user_id, "remember_v1_only", details={"text": memory_text})
        await safe_send(update, "Запомнил в старой памяти. v2 live log временно недоступен.")


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
    if not await ensure_allowed_chat(update):
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
    if memory_manager.v2_full_transition:
        await safe_send(update, "V2-досье по этому участнику пока пустое.")
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
    if not await ensure_allowed_chat(update):
        return

    chat_id = chat_id_of(update)
    v2_lore = memory_manager.build_v2_lore_text(chat_id)
    if v2_lore:
        await safe_send(update, v2_lore)
        return
    if memory_manager.v2_full_transition:
        await safe_send(update, "V2-лор для этого чата пока не сформировался.")
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
    if not await ensure_allowed_chat(update):
        return

    chat_id = chat_id_of(update)
    wait_seconds = check_chat_cooldown(summary_rate_limit, chat_id, SUMMARY_COOLDOWN_SECONDS)
    if wait_seconds > 0:
        await safe_send(update, f"Летописец отдыхает. Повтори через {wait_seconds} сек.")
        return

    try:
        await memory_manager.maybe_update_memory(chat_id)
        context_text = memory_manager.build_chat_context(chat_id, 100)
        kb_context = ""
        if knowledge_base.exists():
            recent = db.recent_messages(chat_id, 20)
            query = build_kb_query(" ".join(row["text"] for row in recent[-10:]), context_text)
            kb_context = knowledge_base.build_context(query, limit=3, max_chars=2500)
        if kb_context:
            context_text = safe_short(context_text + "\n\nKNOWLEDGE BASE:\n" + kb_context, 14000)

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
    if not await ensure_allowed_chat(update):
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
        if knowledge_base.exists():
            recent_user = db.recent_user_messages(chat_id, user_id, 10)
            query_seed = " ".join(row["text"] for row in recent_user[-5:]) or context_text
            kb_context = knowledge_base.build_context(build_kb_query(query_seed), limit=3, max_chars=2200)
            if kb_context:
                context_text = safe_short(context_text + "\n\nKNOWLEDGE BASE:\n" + kb_context, 14000)
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


async def ask(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not await ensure_allowed_chat(update):
        return

    chat_id = chat_id_of(update)
    user_id = user_id_of(update)
    question = " ".join(context.args).strip() if context.args else ""
    if not question:
        await safe_send(update, "Напиши так: /ask твой вопрос")
        return

    wait_seconds = check_user_cooldown(ask_rate_limit, chat_id, user_id, ASK_COOLDOWN_SECONDS)
    if wait_seconds > 0:
        await safe_send(update, f"Слишком быстро. Повтори через {wait_seconds} сек.", max_len=1000)
        return

    try:
        await memory_manager.maybe_update_memory(chat_id)
        chat_context = memory_manager.build_chat_context(chat_id, 80)
        kb_context = ""
        if knowledge_base.exists():
            kb_context = knowledge_base.build_context(build_kb_query(question, chat_context), limit=KB_SEARCH_LIMIT, max_chars=5000)
    except Exception:
        logger.exception("Failed to build /ask context")
        await safe_send(update, "Не получилось собрать контекст. Попробуй позже.")
        return

    try:
        response = await openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.35,
            messages=[
                {"role": "system", "content": "Ты полезный Telegram-бот. Отвечай точно, кратко и без выдумки."},
                {"role": "user", "content": ASK_PROMPT.format(question=question, chat_context=chat_context, kb_context=kb_context or "No KB matches found.")},
            ],
        )
    except AuthenticationError:
        ask_rate_limit[(chat_id, user_id)] = 0
        await safe_send(update, "OpenAI API key неверный. Обнови OPENAI_API_KEY в .env и перезапусти бота.")
        return
    except Exception:
        ask_rate_limit[(chat_id, user_id)] = 0
        logger.exception("Ask generation failed")
        await safe_send(update, "Не получилось ответить. Попробуй позже.")
        return

    reply = clean_bot_reply(response.choices[0].message.content or "")
    if not reply:
        reply = "Не получилось собрать внятный ответ."

    try:
        db.add_bot_response(chat_id, user_id, "ask", reply)
        memory_manager.record_v2_bot_response(chat_id=chat_id, user_id=user_id, command="ask", response_text=reply)
    except Exception:
        logger.exception("Failed to save ask response")

    await safe_send(update, reply, max_len=3500)


async def kbimport(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not await ensure_allowed_chat(update):
        return
    if not is_admin(update):
        await safe_send(update, admin_denied_message())
        return
    if not knowledge_base.exists():
        await safe_send(update, f"База знаний не найдена по пути: {knowledge_base.base_dir}")
        return

    reply = update.message.reply_to_message
    arg_text = " ".join(context.args).strip() if context.args else ""
    target_desc = ""

    try:
        knowledge_base.ensure_inbox()
        if arg_text:
            target_desc = arg_text
            result = await asyncio.to_thread(knowledge_base.add, arg_text)
        elif reply and reply.text:
            url = extract_first_url(reply.text)
            if url:
                target_desc = url
                result = await asyncio.to_thread(knowledge_base.add, url)
            else:
                file_name = f"telegram-note-{chat_id_of(update)}-{reply.message_id}.txt"
                note_path = knowledge_base.inbox_dir / file_name
                note_path.write_text(reply.text, encoding="utf-8")
                target_desc = note_path.name
                result = await asyncio.to_thread(knowledge_base.add, str(note_path))
        elif reply and reply.document:
            original_name = reply.document.file_name or f"document-{reply.message_id}.bin"
            target_path = knowledge_base.inbox_dir / original_name
            telegram_file = await context.bot.get_file(reply.document.file_id)
            await telegram_file.download_to_drive(custom_path=str(target_path))
            target_desc = target_path.name
            result = await asyncio.to_thread(knowledge_base.add, str(target_path))
        elif reply and reply.audio:
            ext = Path(reply.audio.file_name or "audio.mp3").suffix or ".mp3"
            target_path = knowledge_base.inbox_dir / f"telegram-audio-{chat_id_of(update)}-{reply.message_id}{ext}"
            telegram_file = await context.bot.get_file(reply.audio.file_id)
            await telegram_file.download_to_drive(custom_path=str(target_path))
            target_desc = target_path.name
            result = await asyncio.to_thread(knowledge_base.add, str(target_path))
        elif reply and reply.voice:
            target_path = knowledge_base.inbox_dir / f"telegram-voice-{chat_id_of(update)}-{reply.message_id}.ogg"
            telegram_file = await context.bot.get_file(reply.voice.file_id)
            await telegram_file.download_to_drive(custom_path=str(target_path))
            target_desc = target_path.name
            result = await asyncio.to_thread(knowledge_base.add, str(target_path))
        elif reply and reply.video:
            ext = Path(reply.video.file_name or "video.mp4").suffix or ".mp4"
            target_path = knowledge_base.inbox_dir / f"telegram-video-{chat_id_of(update)}-{reply.message_id}{ext}"
            telegram_file = await context.bot.get_file(reply.video.file_id)
            await telegram_file.download_to_drive(custom_path=str(target_path))
            target_desc = target_path.name
            result = await asyncio.to_thread(knowledge_base.add, str(target_path))
        else:
            await safe_send(update, "Сделай reply на текст/документ/аудио/видео или передай URL: /kbimport <url>")
            return
    except Exception:
        logger.exception("KB import failed")
        await safe_send(update, "Импорт в базу знаний не удался.")
        return

    if result.get("code") != 0:
        await safe_send(update, f"Импорт не удался: {safe_short(result.get('output', ''), 1200)}")
        return

    try:
        await asyncio.to_thread(knowledge_base.rebuild_index)
    except Exception:
        logger.exception("Failed to rebuild KB index after import")

    output = result.get("output", "").strip()
    try:
        parsed = json.loads(output) if output.startswith("{") else None
    except json.JSONDecodeError:
        parsed = None
    status_text = parsed.get("status") if isinstance(parsed, dict) else "imported"
    record_audit(
        chat_id_of(update),
        user_id_of(update),
        "kbimport",
        details={"target": target_desc, "status": status_text},
    )
    await safe_send(update, f"Импортировано в KB: {target_desc}\nstatus: {status_text}")


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
    if not is_allowed_chat_id(chat_id):
        logger.warning("Skipped message from non-allowlisted chat_id=%s", chat_id)
        return

    display_name = user_display_name(update)
    username = username_of(update)
    mentions = extract_mentions(text)
    reply_to_message_id = update.message.reply_to_message.message_id if update.message.reply_to_message else None

    try:
        v1_saved = False
        db.add_message(chat_id, user_id, username, display_name, text, mentions)
        v1_saved = True
    except Exception:
        v1_saved = False
        logger.exception("Failed to save incoming message to v1 SQLite")
        if not memory_manager.v2_full_transition and memory_manager.v1_memory_fallback_enabled:
            return

    try:
        v2_saved = True
        memory_manager.record_v2_message(
            chat_id=chat_id,
            user_id=user_id,
            username=username,
            display_name=display_name,
            text=text,
            mentions=mentions,
            telegram_message_id=update.message.message_id,
            telegram_thread_id=getattr(update.message, "message_thread_id", None),
            reply_to_message_id=reply_to_message_id,
            chat_title=chat.title or "",
            chat_type=chat.type,
        )
    except Exception:
        v2_saved = False
        logger.exception("Failed to save incoming message to v2 live event log")
        if memory_manager.v2_full_transition or not memory_manager.v1_memory_fallback_enabled:
            return

    if v1_saved:
        try:
            await memory_manager.maybe_update_memory(chat_id)
        except Exception:
            logger.exception("Memory update failed")
    elif not v2_saved:
        logger.warning("Message was not saved in either v1 or v2 storage")


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
    app.add_handler(CommandHandler("ask", ask))
    app.add_handler(CommandHandler("health", health))
    app.add_handler(CommandHandler("privacy", privacy))
    app.add_handler(CommandHandler("export_me", export_me))
    app.add_handler(CommandHandler("delete_me", delete_me))
    app.add_handler(CommandHandler("forget", forget))
    app.add_handler(CommandHandler("kbstatus", kbstatus))
    app.add_handler(CommandHandler("kbsearch", kbsearch))
    app.add_handler(CommandHandler("kbask", kbask))
    app.add_handler(CommandHandler("kbimport", kbimport))
    app.add_handler(CommandHandler("whoami", whoami))
    app.add_handler(CommandHandler("v2status", v2status))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, store_message))

    mode = "v2-full" if memory_manager.v2_full_transition else "bridge"
    logger.info("PredskazBot started with v2 mode=%s", mode)
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
