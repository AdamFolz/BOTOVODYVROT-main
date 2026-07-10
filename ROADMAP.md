from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import bot
from database import Database
from knowledge_base import KnowledgeBase


class FakeChat:
    def __init__(self, chat_id: int = 123) -> None:
        self.id = chat_id
        self.type = "private"
        self.title = "Test Chat"
        self.messages: list[str] = []

    async def send_message(self, text: str) -> None:
        self.messages.append(text)


class FakeUser:
    id = 777
    username = "tester"
    first_name = "Test"
    last_name = "User"


class FakeMessage:
    def __init__(self, text: str = "") -> None:
        self.text = text
        self.message_id = 1
        self.reply_to_message = None


class FakeUpdate:
    def __init__(self, text: str = "", chat_id: int = 123) -> None:
        self.effective_chat = FakeChat(chat_id)
        self.effective_user = FakeUser()
        self.message = FakeMessage(text)


class HandlerTests(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    def test_health_reports_runtime_status(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            update = FakeUpdate("/health")
            db = Database(str(Path(tmp_dir) / "bot.sqlite3"))
            kb_dir = Path(tmp_dir) / "kb"
            (kb_dir / "knowledge" / "summaries").mkdir(parents=True)
            (kb_dir / "knowledge" / "wiki").mkdir(parents=True)
            (kb_dir / "extracts").mkdir(parents=True)
            (kb_dir / "projects" / "imports").mkdir(parents=True)
            (kb_dir / "sources").mkdir(parents=True)
            (kb_dir / "index.md").write_text("# Index\n", encoding="utf-8")
            with patch.object(bot, "db", db), patch.object(bot, "knowledge_base", KnowledgeBase(kb_dir)):
                self.run_async(bot.health(update, SimpleNamespace(args=[])))
            self.assertTrue(any("kb: ok" in item for item in update.effective_chat.messages))

    def test_privacy_mentions_export_and_delete(self) -> None:
        update = FakeUpdate("/privacy")
        self.run_async(bot.privacy(update, SimpleNamespace(args=[])))
        payload = "\n".join(update.effective_chat.messages)
        self.assertIn("/export_me", payload)
        self.assertIn("/delete_me CONFIRM", payload)

    def test_delete_me_requires_confirmation(self) -> None:
        update = FakeUpdate("/delete_me")
        self.run_async(bot.delete_me(update, SimpleNamespace(args=[])))
        self.assertIn("/delete_me CONFIRM", "\n".join(update.effective_chat.messages))

    def test_allowlist_blocks_unknown_chat(self) -> None:
        update = FakeUpdate("/health", chat_id=999)
        with patch.object(bot, "ALLOWED_CHAT_IDS", {123}):
            allowed = self.run_async(bot.ensure_allowed_chat(update))
        self.assertFalse(allowed)
        self.assertIn("не подключён", "\n".join(update.effective_chat.messages))


if __name__ == "__main__":
    unittest.main()
