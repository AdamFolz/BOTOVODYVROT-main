from __future__ import annotations

import hashlib
import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_uuid(*parts: object) -> str:
    namespace = uuid.uuid5(uuid.NAMESPACE_URL, "https://predskazbot.local/v2-sqlite")
    return str(uuid.uuid5(namespace, ":".join(str(part) for part in parts)))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SQLiteV2Store:
    """Local v2 storage for personal deployments.

    The long-term target can still be PostgreSQL, but this store gives the bot a
    real v2 write/read path today: immutable message events, stable chat/member
    ids, manual memories, claim tables and bot responses live in v2-shaped
    tables instead of only in the legacy v1 schema or JSONL preview files.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def init(self) -> None:
        with self.connect() as conn:
            conn.executescript(
                """
                PRAGMA journal_mode=WAL;
                PRAGMA foreign_keys=ON;

                CREATE TABLE IF NOT EXISTS chats (
                    id TEXT PRIMARY KEY,
                    telegram_chat_id INTEGER NOT NULL UNIQUE,
                    title TEXT NOT NULL DEFAULT '',
                    type TEXT NOT NULL DEFAULT 'telegram',
                    memory_policy_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS members (
                    id TEXT PRIMARY KEY,
                    telegram_user_id INTEGER NOT NULL UNIQUE,
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS chat_memberships (
                    chat_id TEXT NOT NULL,
                    member_id TEXT NOT NULL,
                    current_username TEXT NOT NULL DEFAULT '',
                    current_display_name TEXT NOT NULL DEFAULT '',
                    aliases_json TEXT NOT NULL DEFAULT '[]',
                    first_seen_at TEXT NOT NULL,
                    last_seen_at TEXT NOT NULL,
                    PRIMARY KEY (chat_id, member_id),
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS message_events (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    member_id TEXT NOT NULL,
                    telegram_message_id INTEGER,
                    telegram_thread_id INTEGER,
                    reply_to_event_id TEXT,
                    text TEXT NOT NULL,
                    mentions_json TEXT NOT NULL DEFAULT '[]',
                    content_hash TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    edited_at TEXT,
                    deleted_at TEXT,
                    ingested_at TEXT NOT NULL,
                    raw_payload_json TEXT NOT NULL DEFAULT '{}',
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_message_events_chat_created
                ON message_events(chat_id, created_at DESC);

                CREATE INDEX IF NOT EXISTS idx_message_events_member_created
                ON message_events(chat_id, member_id, created_at DESC);

                CREATE UNIQUE INDEX IF NOT EXISTS idx_message_events_telegram_unique
                ON message_events(chat_id, telegram_message_id)
                WHERE telegram_message_id IS NOT NULL;

                CREATE TABLE IF NOT EXISTS manual_memories_v2 (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    author_member_id TEXT NOT NULL,
                    text TEXT NOT NULL,
                    visibility TEXT NOT NULL DEFAULT 'normal',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                    FOREIGN KEY (author_member_id) REFERENCES members(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_manual_memories_v2_chat_created
                ON manual_memories_v2(chat_id, created_at DESC);

                CREATE TABLE IF NOT EXISTS memory_claims (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    subject_type TEXT NOT NULL,
                    subject_ids_json TEXT NOT NULL DEFAULT '[]',
                    claim_type TEXT NOT NULL DEFAULT 'observation',
                    summary_for_prompt TEXT NOT NULL,
                    confidence REAL NOT NULL DEFAULT 0.0,
                    decayed_weight REAL NOT NULL DEFAULT 0.0,
                    source TEXT NOT NULL DEFAULT 'runtime',
                    visibility TEXT NOT NULL DEFAULT 'normal',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_memory_claims_chat_weight
                ON memory_claims(chat_id, visibility, decayed_weight DESC, confidence DESC);

                CREATE TABLE IF NOT EXISTS bot_responses_v2 (
                    id TEXT PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    member_id TEXT,
                    command TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE,
                    FOREIGN KEY (member_id) REFERENCES members(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS meta_v2 (
                    chat_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (chat_id, key),
                    FOREIGN KEY (chat_id) REFERENCES chats(id) ON DELETE CASCADE
                );
                """
            )

    def ensure_chat(self, telegram_chat_id: int, title: str = "", chat_type: str = "telegram") -> str:
        now = utc_now()
        chat_id = stable_uuid("chat", telegram_chat_id)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chats(id, telegram_chat_id, title, type, memory_policy_json, created_at, updated_at)
                VALUES (?, ?, ?, ?, '{}', ?, ?)
                ON CONFLICT(telegram_chat_id) DO UPDATE SET
                    title=COALESCE(NULLIF(excluded.title, ''), chats.title),
                    type=excluded.type,
                    updated_at=excluded.updated_at
                """,
                (chat_id, int(telegram_chat_id), title or "", chat_type or "telegram", now, now),
            )
        return chat_id

    def ensure_member(self, telegram_user_id: int) -> str:
        now = utc_now()
        member_id = stable_uuid("member", telegram_user_id)
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO members(id, telegram_user_id, first_seen_at, last_seen_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(telegram_user_id) DO UPDATE SET last_seen_at=excluded.last_seen_at
                """,
                (member_id, int(telegram_user_id), now, now),
            )
        return member_id

    def ensure_membership(
        self,
        chat_id: str,
        member_id: str,
        *,
        username: str,
        display_name: str,
    ) -> None:
        now = utc_now()
        with self.connect() as conn:
            existing = conn.execute(
                "SELECT aliases_json, current_username, current_display_name FROM chat_memberships WHERE chat_id=? AND member_id=?",
                (chat_id, member_id),
            ).fetchone()
            aliases: list[str] = []
            if existing:
                try:
                    aliases = list(json.loads(existing["aliases_json"] or "[]"))
                except json.JSONDecodeError:
                    aliases = []
                for alias in (existing["current_username"], existing["current_display_name"]):
                    if alias and alias not in aliases and alias not in {username, display_name}:
                        aliases.append(alias)

            conn.execute(
                """
                INSERT INTO chat_memberships(
                    chat_id, member_id, current_username, current_display_name,
                    aliases_json, first_seen_at, last_seen_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, member_id) DO UPDATE SET
                    current_username=excluded.current_username,
                    current_display_name=excluded.current_display_name,
                    aliases_json=excluded.aliases_json,
                    last_seen_at=excluded.last_seen_at
                """,
                (chat_id, member_id, username or "", display_name or "", json.dumps(aliases, ensure_ascii=False), now, now),
            )

    def add_message_event(
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
        chat_title: str = "",
        chat_type: str = "telegram",
        created_at: str | None = None,
    ) -> str:
        now = utc_now()
        event_created_at = created_at or now
        chat_id = self.ensure_chat(telegram_chat_id, title=chat_title, chat_type=chat_type)
        member_id = self.ensure_member(telegram_user_id)
        self.ensure_membership(chat_id, member_id, username=username, display_name=display_name)
        event_id = str(uuid.uuid4())
        reply_to_event_id = (
            stable_uuid("message_event", telegram_chat_id, reply_to_message_id)
            if reply_to_message_id is not None
            else None
        )
        event_hash = content_hash(f"{telegram_chat_id}:{telegram_message_id}:{telegram_user_id}:{event_created_at}:{text}")
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO message_events(
                    id, chat_id, member_id, telegram_message_id, telegram_thread_id,
                    reply_to_event_id, text, mentions_json, content_hash, created_at,
                    edited_at, deleted_at, ingested_at, raw_payload_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, NULL, ?, ?)
                """,
                (
                    event_id,
                    chat_id,
                    member_id,
                    telegram_message_id,
                    telegram_thread_id,
                    reply_to_event_id,
                    text,
                    json.dumps(mentions, ensure_ascii=False),
                    event_hash,
                    event_created_at,
                    now,
                    json.dumps(
                        {"source": "telegram_runtime", "reply_to_message_id": reply_to_message_id},
                        ensure_ascii=False,
                    ),
                ),
            )
        return event_id

    def add_manual_memory(
        self,
        *,
        telegram_chat_id: int,
        author_telegram_user_id: int,
        text: str,
        username: str = "",
        display_name: str = "",
    ) -> str:
        now = utc_now()
        chat_id = self.ensure_chat(telegram_chat_id)
        member_id = self.ensure_member(author_telegram_user_id)
        self.ensure_membership(chat_id, member_id, username=username, display_name=display_name)
        memory_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO manual_memories_v2(id, chat_id, author_member_id, text, visibility, created_at, updated_at)
                VALUES (?, ?, ?, ?, 'normal', ?, ?)
                """,
                (memory_id, chat_id, member_id, text, now, now),
            )
        return memory_id

    def add_bot_response(
        self,
        *,
        telegram_chat_id: int,
        telegram_user_id: int | None,
        command: str,
        response_text: str,
    ) -> str:
        chat_id = self.ensure_chat(telegram_chat_id)
        member_id = self.ensure_member(telegram_user_id) if telegram_user_id is not None else None
        response_id = str(uuid.uuid4())
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO bot_responses_v2(id, chat_id, member_id, command, response_text, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (response_id, chat_id, member_id, command, response_text, utc_now()),
            )
        return response_id

    def chat_by_telegram_id(self, telegram_chat_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM chats WHERE telegram_chat_id=?", (int(telegram_chat_id),)).fetchone()
        return dict(row) if row else None

    def member_by_telegram_id(self, telegram_user_id: int) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM members WHERE telegram_user_id=?", (int(telegram_user_id),)).fetchone()
        return dict(row) if row else None

    def membership(self, chat_id: str, member_id: str) -> dict[str, Any] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM chat_memberships WHERE chat_id=? AND member_id=?",
                (chat_id, member_id),
            ).fetchone()
        return dict(row) if row else None

    def message_events_for_chat(self, chat_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM message_events WHERE chat_id=? ORDER BY created_at DESC LIMIT ?",
                (chat_id, int(limit)),
            ).fetchall()
        return [self._message_row_to_dict(row) for row in rows]

    def manual_memories_for_chat(self, chat_id: str, limit: int = 20) -> list[dict[str, Any]]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM manual_memories_v2 WHERE chat_id=? AND visibility='normal' ORDER BY created_at DESC LIMIT ?",
                (chat_id, int(limit)),
            ).fetchall()
        return [dict(row) for row in rows]

    def claims_for_chat(self, chat_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._claims("subject_type='chat'", (chat_id,), limit)

    def claims_for_member(self, chat_id: str, member_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._claims("1=1", (chat_id,), 500)
        return [row for row in rows if member_id in row.get("subject_ids", [])][:limit]

    def relationship_edges_for_member(self, chat_id: str, member_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return []

    def display_name_for_member(self, chat_id: str, member_id: str) -> str:
        row = self.membership(chat_id, member_id)
        if not row:
            return member_id
        return row.get("current_display_name") or row.get("current_username") or member_id

    def count_message_events(self, telegram_chat_id: int) -> int:
        chat = self.chat_by_telegram_id(telegram_chat_id)
        if not chat:
            return 0
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) AS count FROM message_events WHERE chat_id=?", (chat["id"],)).fetchone()
        return int(row["count"] if row else 0)

    def _claims(self, where_sql: str, params: tuple[Any, ...], limit: int) -> list[dict[str, Any]]:
        chat_id = params[0]
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT * FROM memory_claims
                WHERE chat_id=? AND visibility='normal' AND {where_sql}
                ORDER BY decayed_weight DESC, confidence DESC, updated_at DESC
                LIMIT ?
                """,
                (chat_id, *params[1:], int(limit)),
            ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            try:
                item["subject_ids"] = list(json.loads(item.pop("subject_ids_json") or "[]"))
            except json.JSONDecodeError:
                item["subject_ids"] = []
            result.append(item)
        return result

    def _message_row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["mentions_member_ids"] = list(json.loads(item.pop("mentions_json") or "[]"))
        except json.JSONDecodeError:
            item["mentions_member_ids"] = []
        try:
            item["raw_payload"] = dict(json.loads(item.pop("raw_payload_json") or "{}"))
        except json.JSONDecodeError:
            item["raw_payload"] = {}
        return item
