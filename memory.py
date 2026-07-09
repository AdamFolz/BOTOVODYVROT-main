import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI, AuthenticationError

from database import Database
from prompts import MEMORY_CURATOR_PROMPT
from utils import safe_short

SRC_PATH = Path(__file__).resolve().parent / "src"
if SRC_PATH.exists() and str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))

from predskazbot_v2 import SeedStore, SQLiteV2Store
from predskazbot_v2.live_event_log import LiveEventLog
from predskazbot_v2.retrieval import build_lore_context, build_profile_context


logger = logging.getLogger(__name__)


class MemoryManager:
    def __init__(self, db: Database, openai_client: AsyncOpenAI, model: str) -> None:
        self.db = db
        self.client = openai_client
        self.model = model
        self.v2_enabled = os.getenv("V2_MEMORY_ENABLED", "1") == "1"
        self.v2_seed_path = Path(os.getenv("V2_SEED_PATH", "exports/v2-seed.jsonl"))
        self.v2_live_events_path = Path(os.getenv("V2_LIVE_EVENTS_PATH", "exports/v2-live-events.jsonl"))
        self.v2_sqlite_path = Path(os.getenv("V2_SQLITE_PATH", "predskazbot_v2.sqlite3"))
        self.v2_jsonl_bridge_enabled = os.getenv("V2_JSONL_BRIDGE_ENABLED", "0") == "1"
        self.v2_store = SQLiteV2Store(self.v2_sqlite_path) if self.v2_enabled else None
        self.llm_disabled_reason: str | None = None

    def load_v2_seed_store(self) -> SeedStore | None:
        if not self.v2_enabled:
            return None
        if self.v2_store:
            self.v2_store.init()
            return self.v2_store
        paths = [self.v2_seed_path, self.v2_live_events_path]
        if not any(path.exists() for path in paths):
            return None
        return SeedStore.from_jsonl_paths(paths)

    def record_v2_message(
        self,
        *,
        chat_id: int,
        user_id: int,
        username: str,
        display_name: str,
        text: str,
        mentions: list[str],
        telegram_message_id: int | None = None,
        telegram_thread_id: int | None = None,
        chat_title: str = "",
        chat_type: str = "telegram",
    ) -> None:
        if not self.v2_enabled:
            return
        if self.v2_store:
            self.v2_store.init()
            self.v2_store.add_message_event(
                telegram_chat_id=chat_id,
                telegram_user_id=user_id,
                username=username,
                display_name=display_name,
                text=text,
                mentions=mentions,
                telegram_message_id=telegram_message_id,
                telegram_thread_id=telegram_thread_id,
                chat_title=chat_title,
                chat_type=chat_type,
            )
        if self.v2_jsonl_bridge_enabled:
            LiveEventLog(self.v2_live_events_path).append_message(
                telegram_chat_id=chat_id,
                telegram_user_id=user_id,
                username=username,
                display_name=display_name,
                text=text,
                mentions=mentions,
            )


    def record_v2_manual_memory(
        self,
        *,
        chat_id: int,
        author_user_id: int,
        username: str,
        display_name: str,
        text: str,
    ) -> None:
        if not self.v2_enabled or not self.v2_store:
            return
        self.v2_store.init()
        self.v2_store.add_manual_memory(
            telegram_chat_id=chat_id,
            author_telegram_user_id=author_user_id,
            username=username,
            display_name=display_name,
            text=text,
        )

    def record_v2_bot_response(
        self,
        *,
        chat_id: int,
        user_id: int | None,
        command: str,
        response_text: str,
    ) -> None:
        if not self.v2_enabled or not self.v2_store:
            return
        self.v2_store.init()
        self.v2_store.add_bot_response(
            telegram_chat_id=chat_id,
            telegram_user_id=user_id,
            command=command,
            response_text=response_text,
        )

    def v2_status_text(self, chat_id: int) -> str:
        if not self.v2_enabled:
            return "V2 memory выключена: V2_MEMORY_ENABLED != 1"
        if not self.v2_store:
            return "V2 SQLite store не инициализирован."
        self.v2_store.init()
        count = self.v2_store.count_message_events(chat_id)
        return (
            "V2 memory status:\n"
            f"storage: sqlite\n"
            f"path: {self.v2_sqlite_path}\n"
            f"chat_message_events: {count}\n"
            f"jsonl_bridge: {self.v2_jsonl_bridge_enabled}"
        )

    def build_v2_profile_text(self, chat_id: int, user_id: int) -> str | None:
        store = self.load_v2_seed_store()
        if not store:
            return None
        text = build_profile_context(store, chat_id, user_id)
        if "не найден в v2 seed" in text:
            return None
        return text

    def build_v2_lore_text(self, chat_id: int) -> str | None:
        store = self.load_v2_seed_store()
        if not store:
            return None
        text = build_lore_context(store, chat_id)
        if "не найден в v2 seed" in text:
            return None
        return text

    def build_context_for_user(self, chat_id: int, user_id: int, max_recent_messages: int = 80) -> str:
        profile = self.db.get_user_profile(chat_id, user_id)
        chat_memory = self.db.get_chat_memory(chat_id)
        recent_messages = self.db.recent_messages(chat_id, max_recent_messages)
        user_messages = self.db.recent_user_messages(chat_id, user_id, 25)
        relationships = self.db.recent_relationships_for_user(chat_id, user_id, 20)
        manual_memories = self.db.recent_manual_memories(chat_id, 10)
        recent_bot_responses = self.db.recent_bot_responses(chat_id, 20)

        blocks: list[str] = []

        v2_profile = self.build_v2_profile_text(chat_id, user_id)
        if v2_profile:
            blocks.append("V2 MEMORY CONTEXT:\n" + v2_profile)

        if profile:
            blocks.append(
                "ДОСЬЕ УЧАСТНИКА:\n"
                f"Имя: {profile['display_name']} (@{profile['username']})\n"
                f"Стиль: {profile['style_summary']}\n"
                f"Темы: {profile['frequent_topics']}\n"
                f"Упоминания: {profile['mentioned_users']}\n"
                f"Связи: {profile['relationship_notes']}\n"
                f"Личные мемы: {profile['personal_memes']}\n"
                f"Мягкие ярлыки: {profile['soft_labels']}\n"
                f"Активность: {profile['energy_level']}/5\n"
                f"Токсичный стиль: {profile['toxicity_style']}\n"
                f"Мемность: {profile['meme_score']}/5\n"
                f"Ночной режим: {profile['night_mode_behavior']}\n"
                f"Уверенность наблюдений: {profile['confidence_score']}"
            )
        else:
            blocks.append("ДОСЬЕ УЧАСТНИКА: пока почти пустое, используй только свежий контекст.")

        if chat_memory:
            blocks.append(
                "ПАМЯТЬ КОНФЫ:\n"
                f"Настроение дня: {chat_memory['mood_today']}\n"
                f"Уровень хаоса: {chat_memory['chaos_level']}/5\n"
                f"Главная тема: {chat_memory['main_topic_today']}\n"
                f"Главный клоун дня: {chat_memory['main_clown_today']}\n"
                f"Мем дня: {chat_memory['meme_of_the_day']}\n"
                f"Мемы недели: {chat_memory['weekly_memes']}\n"
                f"Недавняя драма: {chat_memory['recent_drama']}\n"
                f"Популярные темы: {chat_memory['popular_topics']}\n"
                f"Локальные фразы: {chat_memory['local_phrases']}\n"
                f"Артефакты: {chat_memory['sacred_artifacts']}\n"
                f"Мифология: {chat_memory['chat_mythology']}"
            )
        else:
            blocks.append("ПАМЯТЬ КОНФЫ: пока пустая.")

        if relationships:
            rel_text = "\n".join(
                f"- {row['relation_type']}: {row['notes']} (наблюдений: {row['evidence_count']})"
                for row in relationships
            )
            blocks.append("СВЯЗИ УЧАСТНИКА:\n" + rel_text)

        if manual_memories:
            mem_text = "\n".join(f"- {row['text']}" for row in manual_memories)
            blocks.append("РУЧНАЯ ПАМЯТЬ ОТ КОНФЫ:\n" + mem_text)

        if user_messages:
            user_text = "\n".join(
                f"{row['display_name']}: {row['text']}"
                for row in user_messages[-15:]
            )
            blocks.append("ПОСЛЕДНИЕ СООБЩЕНИЯ УЧАСТНИКА:\n" + user_text)

        if recent_messages:
            recent_text = "\n".join(
                f"{row['display_name']}: {row['text']}"
                for row in recent_messages[-35:]
            )
            blocks.append("СВЕЖИЙ КОНТЕКСТ ЧАТА:\n" + recent_text)

        if recent_bot_responses:
            old_text = "\n".join(f"- {text}" for text in recent_bot_responses[:15])
            blocks.append("НЕДАВНИЕ ОТВЕТЫ БОТА, ИХ НЕЛЬЗЯ ПОВТОРЯТЬ:\n" + old_text)

        return safe_short("\n\n".join(blocks), 12000)

    def build_chat_context(self, chat_id: int, max_recent_messages: int = 100) -> str:
        chat_memory = self.db.get_chat_memory(chat_id)
        recent_messages = self.db.recent_messages(chat_id, max_recent_messages)
        manual_memories = self.db.recent_manual_memories(chat_id, 10)

        blocks: list[str] = []

        v2_lore = self.build_v2_lore_text(chat_id)
        if v2_lore:
            blocks.append("V2 MEMORY CONTEXT:\n" + v2_lore)

        if chat_memory:
            blocks.append(
                "ПАМЯТЬ КОНФЫ:\n"
                f"Настроение дня: {chat_memory['mood_today']}\n"
                f"Уровень хаоса: {chat_memory['chaos_level']}/5\n"
                f"Главная тема: {chat_memory['main_topic_today']}\n"
                f"Главный клоун дня: {chat_memory['main_clown_today']}\n"
                f"Мем дня: {chat_memory['meme_of_the_day']}\n"
                f"Мемы недели: {chat_memory['weekly_memes']}\n"
                f"Недавняя драма: {chat_memory['recent_drama']}\n"
                f"Популярные темы: {chat_memory['popular_topics']}\n"
                f"Локальные фразы: {chat_memory['local_phrases']}\n"
                f"Артефакты: {chat_memory['sacred_artifacts']}\n"
                f"Мифология: {chat_memory['chat_mythology']}"
            )

        if manual_memories:
            blocks.append("РУЧНАЯ ПАМЯТЬ:\n" + "\n".join(f"- {row['text']}" for row in manual_memories))

        if recent_messages:
            blocks.append(
                "ПОСЛЕДНИЕ СООБЩЕНИЯ:\n"
                + "\n".join(f"{row['display_name']}: {row['text']}" for row in recent_messages[-50:])
            )

        return safe_short("\n\n".join(blocks), 12000)

    async def maybe_update_memory(self, chat_id: int) -> None:
        if self.llm_disabled_reason:
            return

        every = int(os.getenv("MEMORY_UPDATE_EVERY_MESSAGES", "40"))
        min_messages = int(os.getenv("MEMORY_MIN_MESSAGES", "20"))

        count = self.db.count_messages(chat_id)
        last = self.db.get_meta_int(chat_id, "last_memory_update_message_count", 0)

        if count < min_messages:
            return
        if count - last < every:
            return

        await self.update_memory(chat_id)
        self.db.set_meta(chat_id, "last_memory_update_message_count", count)

    async def update_memory(self, chat_id: int) -> None:
        messages = self.db.recent_messages(chat_id, 120)
        if not messages:
            return

        packed_messages = [
            {
                "user_id": row["user_id"],
                "username": row["username"],
                "display_name": row["display_name"],
                "text": row["text"],
                "created_at": row["created_at"],
            }
            for row in messages
        ]

        prompt = MEMORY_CURATOR_PROMPT.format(
            messages=json.dumps(packed_messages, ensure_ascii=False, indent=2)
        )

        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                temperature=0.2,
                response_format={"type": "json_object"},
                messages=[
                    {
                        "role": "system",
                        "content": "Ты аккуратный аналитик памяти. Возвращай только валидный JSON.",
                    },
                    {
                        "role": "user",
                        "content": prompt,
                    },
                ],
            )
        except AuthenticationError:
            self.llm_disabled_reason = "OpenAI authentication failed: check OPENAI_API_KEY"
            logger.error("Memory updates disabled: invalid OPENAI_API_KEY")
            return
        except Exception:
            logger.exception("Memory update OpenAI request failed")
            return

        content = response.choices[0].message.content or "{}"
        data = self._parse_json_object(content)
        if not data:
            logger.warning("Memory update returned invalid JSON")
            return

        chat_memory = data.get("chat_memory")
        if isinstance(chat_memory, dict):
            try:
                self.db.upsert_chat_memory(chat_id, chat_memory)
            except Exception:
                logger.exception("Failed to upsert chat memory")

        profiles = data.get("user_profiles", [])
        if isinstance(profiles, list):
            for profile in profiles:
                if isinstance(profile, dict) and profile.get("user_id"):
                    try:
                        self.db.upsert_user_profile(chat_id, profile)
                    except Exception:
                        logger.exception("Failed to upsert user profile")

        relationships = data.get("relationships", [])
        if isinstance(relationships, list):
            for relation in relationships:
                if isinstance(relation, dict):
                    try:
                        self.db.upsert_relationship(chat_id, relation)
                    except Exception:
                        logger.exception("Failed to upsert relationship")

    def _parse_json_object(self, text: str) -> dict[str, Any]:
        cleaned = text.strip()

        if cleaned.startswith("```"):
            cleaned = cleaned.strip("`")
            cleaned = cleaned.replace("json\n", "", 1).strip()

        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start >= 0 and end >= start:
            cleaned = cleaned[start:end + 1]

        try:
            obj = json.loads(cleaned)
        except json.JSONDecodeError:
            return {}

        return obj if isinstance(obj, dict) else {}
