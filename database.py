import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def connect(self):
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
                '''
                PRAGMA journal_mode=WAL;

                CREATE TABLE IF NOT EXISTS users (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL,
                    PRIMARY KEY (chat_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS raw_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    text TEXT NOT NULL,
                    mentions_json TEXT NOT NULL DEFAULT '[]',
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_raw_messages_chat_id_id
                ON raw_messages(chat_id, id);

                CREATE INDEX IF NOT EXISTS idx_raw_messages_chat_user
                ON raw_messages(chat_id, user_id, id);

                CREATE TABLE IF NOT EXISTS user_profiles (
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    username TEXT NOT NULL DEFAULT '',
                    display_name TEXT NOT NULL DEFAULT '',
                    style_summary TEXT NOT NULL DEFAULT '',
                    frequent_topics TEXT NOT NULL DEFAULT '',
                    mentioned_users TEXT NOT NULL DEFAULT '',
                    relationship_notes TEXT NOT NULL DEFAULT '',
                    personal_memes TEXT NOT NULL DEFAULT '',
                    soft_labels TEXT NOT NULL DEFAULT '',
                    energy_level INTEGER NOT NULL DEFAULT 1,
                    toxicity_style TEXT NOT NULL DEFAULT '',
                    meme_score INTEGER NOT NULL DEFAULT 1,
                    night_mode_behavior TEXT NOT NULL DEFAULT '',
                    confidence_score REAL NOT NULL DEFAULT 0.0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (chat_id, user_id)
                );

                CREATE TABLE IF NOT EXISTS chat_memory (
                    chat_id INTEGER PRIMARY KEY,
                    mood_today TEXT NOT NULL DEFAULT '',
                    chaos_level INTEGER NOT NULL DEFAULT 1,
                    main_topic_today TEXT NOT NULL DEFAULT '',
                    main_clown_today TEXT NOT NULL DEFAULT '',
                    meme_of_the_day TEXT NOT NULL DEFAULT '',
                    weekly_memes TEXT NOT NULL DEFAULT '',
                    recent_drama TEXT NOT NULL DEFAULT '',
                    popular_topics TEXT NOT NULL DEFAULT '',
                    local_phrases TEXT NOT NULL DEFAULT '',
                    sacred_artifacts TEXT NOT NULL DEFAULT '',
                    chat_mythology TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS relationships (
                    chat_id INTEGER NOT NULL,
                    user_a_id INTEGER NOT NULL,
                    user_b_id INTEGER NOT NULL,
                    relation_type TEXT NOT NULL DEFAULT '',
                    notes TEXT NOT NULL DEFAULT '',
                    evidence_count INTEGER NOT NULL DEFAULT 0,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (chat_id, user_a_id, user_b_id, relation_type)
                );

                CREATE TABLE IF NOT EXISTS bot_responses (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    user_id INTEGER,
                    command TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_bot_responses_chat_id_id
                ON bot_responses(chat_id, id);

                CREATE TABLE IF NOT EXISTS manual_memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    chat_id INTEGER NOT NULL,
                    author_user_id INTEGER NOT NULL,
                    text TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS meta (
                    chat_id INTEGER NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    PRIMARY KEY (chat_id, key)
                );
                '''
            )

    def upsert_user(self, chat_id: int, user_id: int, username: str, display_name: str) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                '''
                INSERT INTO users(chat_id, user_id, username, display_name, first_seen, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    username=excluded.username,
                    display_name=excluded.display_name,
                    last_seen=excluded.last_seen
                ''',
                (chat_id, user_id, username, display_name, now, now),
            )

    def add_message(self, chat_id: int, user_id: int, username: str, display_name: str, text: str, mentions: list[str]) -> None:
        self.upsert_user(chat_id, user_id, username, display_name)
        with self.connect() as conn:
            conn.execute(
                '''
                INSERT INTO raw_messages(chat_id, user_id, username, display_name, text, mentions_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (chat_id, user_id, username, display_name, text, json.dumps(mentions, ensure_ascii=False), utc_now()),
            )

    def recent_messages(self, chat_id: int, limit: int = 80) -> list[sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute(
                '''
                SELECT * FROM raw_messages
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                ''',
                (chat_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def recent_user_messages(self, chat_id: int, user_id: int, limit: int = 30) -> list[sqlite3.Row]:
        with self.connect() as conn:
            rows = conn.execute(
                '''
                SELECT * FROM raw_messages
                WHERE chat_id = ? AND user_id = ?
                ORDER BY id DESC
                LIMIT ?
                ''',
                (chat_id, user_id, limit),
            ).fetchall()
        return list(reversed(rows))

    def get_user_by_username(self, chat_id: int, username: str) -> Optional[sqlite3.Row]:
        username = username.lstrip("@").lower()
        with self.connect() as conn:
            return conn.execute(
                '''
                SELECT * FROM users
                WHERE chat_id = ? AND lower(username) = ?
                ''',
                (chat_id, username),
            ).fetchone()

    def get_user_profile(self, chat_id: int, user_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                'SELECT * FROM user_profiles WHERE chat_id = ? AND user_id = ?',
                (chat_id, user_id),
            ).fetchone()

    def upsert_user_profile(self, chat_id: int, profile: dict[str, Any]) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                '''
                INSERT INTO user_profiles(
                    chat_id, user_id, username, display_name, style_summary,
                    frequent_topics, mentioned_users, relationship_notes, personal_memes,
                    soft_labels, energy_level, toxicity_style, meme_score,
                    night_mode_behavior, confidence_score, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_id) DO UPDATE SET
                    username=excluded.username,
                    display_name=excluded.display_name,
                    style_summary=excluded.style_summary,
                    frequent_topics=excluded.frequent_topics,
                    mentioned_users=excluded.mentioned_users,
                    relationship_notes=excluded.relationship_notes,
                    personal_memes=excluded.personal_memes,
                    soft_labels=excluded.soft_labels,
                    energy_level=excluded.energy_level,
                    toxicity_style=excluded.toxicity_style,
                    meme_score=excluded.meme_score,
                    night_mode_behavior=excluded.night_mode_behavior,
                    confidence_score=excluded.confidence_score,
                    updated_at=excluded.updated_at
                ''',
                (
                    chat_id,
                    int(profile.get("user_id", 0)),
                    str(profile.get("username", "")),
                    str(profile.get("display_name", "")),
                    str(profile.get("style_summary", "")),
                    str(profile.get("frequent_topics", "")),
                    str(profile.get("mentioned_users", "")),
                    str(profile.get("relationship_notes", "")),
                    str(profile.get("personal_memes", "")),
                    str(profile.get("soft_labels", "")),
                    int(profile.get("energy_level", 1)),
                    str(profile.get("toxicity_style", "")),
                    int(profile.get("meme_score", 1)),
                    str(profile.get("night_mode_behavior", "")),
                    float(profile.get("confidence_score", 0.0)),
                    now,
                ),
            )

    def get_chat_memory(self, chat_id: int) -> Optional[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute('SELECT * FROM chat_memory WHERE chat_id = ?', (chat_id,)).fetchone()

    def upsert_chat_memory(self, chat_id: int, memory: dict[str, Any]) -> None:
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                '''
                INSERT INTO chat_memory(
                    chat_id, mood_today, chaos_level, main_topic_today, main_clown_today,
                    meme_of_the_day, weekly_memes, recent_drama, popular_topics,
                    local_phrases, sacred_artifacts, chat_mythology, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id) DO UPDATE SET
                    mood_today=excluded.mood_today,
                    chaos_level=excluded.chaos_level,
                    main_topic_today=excluded.main_topic_today,
                    main_clown_today=excluded.main_clown_today,
                    meme_of_the_day=excluded.meme_of_the_day,
                    weekly_memes=excluded.weekly_memes,
                    recent_drama=excluded.recent_drama,
                    popular_topics=excluded.popular_topics,
                    local_phrases=excluded.local_phrases,
                    sacred_artifacts=excluded.sacred_artifacts,
                    chat_mythology=excluded.chat_mythology,
                    updated_at=excluded.updated_at
                ''',
                (
                    chat_id,
                    str(memory.get("mood_today", "")),
                    int(memory.get("chaos_level", 1)),
                    str(memory.get("main_topic_today", "")),
                    str(memory.get("main_clown_today", "")),
                    str(memory.get("meme_of_the_day", "")),
                    str(memory.get("weekly_memes", "")),
                    str(memory.get("recent_drama", "")),
                    str(memory.get("popular_topics", "")),
                    str(memory.get("local_phrases", "")),
                    str(memory.get("sacred_artifacts", "")),
                    str(memory.get("chat_mythology", "")),
                    now,
                ),
            )

    def upsert_relationship(self, chat_id: int, relation: dict[str, Any]) -> None:
        a = int(relation.get("user_a_id", 0))
        b = int(relation.get("user_b_id", 0))
        if not a or not b or a == b:
            return
        if a > b:
            a, b = b, a
        now = utc_now()
        with self.connect() as conn:
            conn.execute(
                '''
                INSERT INTO relationships(chat_id, user_a_id, user_b_id, relation_type, notes, evidence_count, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, user_a_id, user_b_id, relation_type) DO UPDATE SET
                    notes=excluded.notes,
                    evidence_count=relationships.evidence_count + excluded.evidence_count,
                    updated_at=excluded.updated_at
                ''',
                (
                    chat_id,
                    a,
                    b,
                    str(relation.get("relation_type", "")),
                    str(relation.get("notes", "")),
                    int(relation.get("evidence_count", 1)),
                    now,
                ),
            )

    def recent_relationships_for_user(self, chat_id: int, user_id: int, limit: int = 20) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                '''
                SELECT * FROM relationships
                WHERE chat_id = ? AND (user_a_id = ? OR user_b_id = ?)
                ORDER BY updated_at DESC
                LIMIT ?
                ''',
                (chat_id, user_id, user_id, limit),
            ).fetchall()

    def add_bot_response(self, chat_id: int, user_id: Optional[int], command: str, response_text: str) -> None:
        with self.connect() as conn:
            conn.execute(
                '''
                INSERT INTO bot_responses(chat_id, user_id, command, response_text, created_at)
                VALUES (?, ?, ?, ?, ?)
                ''',
                (chat_id, user_id, command, response_text, utc_now()),
            )

    def recent_bot_responses(self, chat_id: int, limit: int = 80) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                '''
                SELECT response_text FROM bot_responses
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                ''',
                (chat_id, limit),
            ).fetchall()
        return [str(row["response_text"]) for row in rows]

    def add_manual_memory(self, chat_id: int, author_user_id: int, text: str) -> None:
        with self.connect() as conn:
            conn.execute(
                '''
                INSERT INTO manual_memories(chat_id, author_user_id, text, created_at)
                VALUES (?, ?, ?, ?)
                ''',
                (chat_id, author_user_id, text, utc_now()),
            )

    def recent_manual_memories(self, chat_id: int, limit: int = 30) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                '''
                SELECT * FROM manual_memories
                WHERE chat_id = ?
                ORDER BY id DESC
                LIMIT ?
                ''',
                (chat_id, limit),
            ).fetchall()

    def get_meta_int(self, chat_id: int, key: str, default: int = 0) -> int:
        with self.connect() as conn:
            row = conn.execute(
                'SELECT value FROM meta WHERE chat_id = ? AND key = ?',
                (chat_id, key),
            ).fetchone()
        if not row:
            return default
        try:
            return int(row["value"])
        except ValueError:
            return default

    def set_meta(self, chat_id: int, key: str, value: str | int) -> None:
        with self.connect() as conn:
            conn.execute(
                '''
                INSERT INTO meta(chat_id, key, value)
                VALUES (?, ?, ?)
                ON CONFLICT(chat_id, key) DO UPDATE SET value=excluded.value
                ''',
                (chat_id, key, str(value)),
            )

    def count_messages(self, chat_id: int) -> int:
        with self.connect() as conn:
            row = conn.execute(
                'SELECT COUNT(*) AS c FROM raw_messages WHERE chat_id = ?',
                (chat_id,),
            ).fetchone()
        return int(row["c"])
