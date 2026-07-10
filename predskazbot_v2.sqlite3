from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_uuid(*parts: object) -> str:
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, "https://predskazbot.local/v2-live")
    return str(uuid.uuid5(namespace, ":".join(str(part) for part in parts)))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class LiveEventLog:
    """Append-only v2 JSONL event log for local/personal bot usage.

    This is the live bridge before PostgreSQL is introduced: every new Telegram
    text message can be written as v2-shaped records immediately, so v2 retrieval
    can see fresh messages without waiting for a full database rewrite.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def append_message(
        self,
        *,
        telegram_chat_id: int,
        telegram_user_id: int,
        username: str,
        display_name: str,
        text: str,
        mentions: list[str],
        telegram_message_id: int | None = None,
        telegram_thread_id: int | None = None,
        reply_to_message_id: int | None = None,
        created_at: str | None = None,
    ) -> None:
        now = utc_now()
        event_created_at = created_at or now
        chat_id = stable_uuid("chat", telegram_chat_id)
        member_id = stable_uuid("member", telegram_user_id)
        event_id = stable_uuid("message_event", telegram_chat_id, telegram_message_id or "", telegram_user_id)
        reply_to_event_id = (
            stable_uuid("message_event", telegram_chat_id, reply_to_message_id, "reply")
            if reply_to_message_id is not None
            else None
        )

        records = [
            seed_row(
                "chats",
                {
                    "id": chat_id,
                    "telegram_chat_id": telegram_chat_id,
                    "title": "",
                    "type": "live_v2",
                    "memory_policy": {},
                    "created_at": event_created_at,
                    "updated_at": now,
                },
            ),
            seed_row(
                "members",
                {
                    "id": member_id,
                    "telegram_user_id": telegram_user_id,
                    "first_seen_at": event_created_at,
                    "last_seen_at": now,
                },
            ),
            seed_row(
                "chat_memberships",
                {
                    "chat_id": chat_id,
                    "member_id": member_id,
                    "current_username": username,
                    "current_display_name": display_name,
                    "aliases": [],
                    "first_seen_at": event_created_at,
                    "last_seen_at": now,
                },
            ),
            seed_row(
                "message_events",
                {
                    "id": event_id,
                    "chat_id": chat_id,
                    "member_id": member_id,
                    "telegram_message_id": telegram_message_id,
                    "telegram_thread_id": telegram_thread_id,
                    "reply_to_event_id": reply_to_event_id,
                    "text": text,
                    "mentions_member_ids": [],
                    "content_hash": content_hash(f"{telegram_chat_id}:{telegram_message_id}:{telegram_user_id}:{event_created_at}:{text}"),
                    "created_at": event_created_at,
                    "edited_at": None,
                    "deleted_at": None,
                    "ingested_at": now,
                    "raw_payload": {
                        "source": "live_v2_jsonl",
                        "mentions": mentions,
                        "reply_to_message_id": reply_to_message_id,
                    },
                },
            ),
        ]

        with self.path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                handle.write("\n")

    def append_manual_memory(
        self,
        *,
        telegram_chat_id: int,
        author_telegram_user_id: int,
        text: str,
        username: str = "",
        display_name: str = "",
        created_at: str | None = None,
    ) -> None:
        now = utc_now()
        event_created_at = created_at or now
        chat_id = stable_uuid("chat", telegram_chat_id)
        member_id = stable_uuid("member", author_telegram_user_id)
        memory_id = stable_uuid("manual_memory", telegram_chat_id, author_telegram_user_id, event_created_at, text)
        records = [
            seed_row(
                "chats",
                {
                    "id": chat_id,
                    "telegram_chat_id": telegram_chat_id,
                    "title": "",
                    "type": "live_v2",
                    "memory_policy": {},
                    "created_at": event_created_at,
                    "updated_at": now,
                },
            ),
            seed_row(
                "members",
                {
                    "id": member_id,
                    "telegram_user_id": author_telegram_user_id,
                    "first_seen_at": event_created_at,
                    "last_seen_at": now,
                },
            ),
            seed_row(
                "chat_memberships",
                {
                    "chat_id": chat_id,
                    "member_id": member_id,
                    "current_username": username,
                    "current_display_name": display_name,
                    "aliases": [],
                    "first_seen_at": event_created_at,
                    "last_seen_at": now,
                },
            ),
            seed_row(
                "manual_memories_v2",
                {
                    "id": memory_id,
                    "chat_id": chat_id,
                    "author_member_id": member_id,
                    "text": text,
                    "visibility": "normal",
                    "created_at": event_created_at,
                    "updated_at": now,
                    "raw_payload": {"source": "live_v2_jsonl"},
                },
            ),
        ]
        with self.path.open("a", encoding="utf-8") as handle:
            for record in records:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
                handle.write("\n")


def seed_row(entity: str, data: dict[str, Any]) -> dict[str, Any]:
    return {
        "record_type": "v2_seed_row",
        "schema": "predskazbot_v2_seed_jsonl",
        "schema_version": 1,
        "entity": entity,
        "data": data,
    }
