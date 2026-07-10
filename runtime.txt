from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

from src.predskazbot_v2.live_event_log import LiveEventLog
from src.predskazbot_v2.retrieval import build_lore_context, build_profile_context
from src.predskazbot_v2.seed_store import SeedStore


class V2JsonlTests(unittest.TestCase):
    def test_live_log_is_self_contained_and_deduped_for_retrieval(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = Path(tmp_dir) / "live.jsonl"
            log = LiveEventLog(path)
            log.append_message(
                telegram_chat_id=100,
                telegram_user_id=200,
                username="old",
                display_name="Old Name",
                text="hello once",
                mentions=[],
                telegram_message_id=10,
                telegram_thread_id=1,
            )
            log.append_message(
                telegram_chat_id=100,
                telegram_user_id=200,
                username="new",
                display_name="New Name",
                text="hello once edited by replay",
                mentions=[],
                telegram_message_id=10,
                telegram_thread_id=1,
            )
            log.append_manual_memory(
                telegram_chat_id=100,
                author_telegram_user_id=200,
                text="manual v2 note",
            )
            store = SeedStore.from_jsonl(path)
            self.assertEqual(len(store.records_by_entity["message_events"]), 1)
            self.assertEqual(len(store.records_by_entity["chat_memberships"]), 1)
            self.assertIn("New Name", build_profile_context(store, 100, 200))
            self.assertIn("hello once edited by replay", build_profile_context(store, 100, 200))
            self.assertIn("manual v2 note", build_lore_context(store, 100))

    def test_importer_quotes_identifiers_and_rejects_unsafe_names(self) -> None:
        importer = _load_importer()
        sql = importer.upsert_sql("message_events", {"id": "1", "chat_id": "2", "text": "hello"})
        self.assertIn('INSERT INTO "message_events"', sql)
        self.assertIn('"text"=EXCLUDED."text"', sql)
        with self.assertRaises(importer.V2ImportError):
            importer.quote_identifier("message_events; DROP TABLE chats")


def _load_importer():
    spec = importlib.util.spec_from_file_location("import_v2_seed", Path("scripts/import_v2_seed.py"))
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load import_v2_seed.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


if __name__ == "__main__":
    unittest.main()
