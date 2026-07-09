from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from knowledge_base import KnowledgeBase


class KnowledgeBaseTests(unittest.TestCase):
    def test_missing_base_returns_empty_status_and_hits(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            kb = KnowledgeBase(Path(tmp_dir) / "missing")
            self.assertFalse(kb.exists())
            self.assertEqual(kb.search("anything"), [])
            self.assertEqual(kb.status()["summaries"], 0)

    def test_search_prioritizes_summaries_over_service_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            (base / "knowledge" / "summaries").mkdir(parents=True)
            (base / "projects" / "imports").mkdir(parents=True)
            (base / "extracts" / "text").mkdir(parents=True)
            (base / "index.md").write_text("# Index\n", encoding="utf-8")
            (base / "knowledge" / "summaries" / "ai.md").write_text(
                "Freelance knowledge automation summary\n",
                encoding="utf-8",
            )
            (base / "projects" / "imports" / "ai.json").write_text(
                json.dumps({"title": "Freelance knowledge automation"}),
                encoding="utf-8",
            )
            kb = KnowledgeBase(base)
            hits = kb.search("freelance knowledge", limit=2)
            self.assertGreaterEqual(len(hits), 2)
            self.assertTrue(hits[0].path.startswith("knowledge/summaries/"))

    def test_status_reports_failed_imports_and_last_import(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            base = Path(tmp_dir)
            for path in [
                base / "sources" / "text",
                base / "extracts" / "text",
                base / "knowledge" / "summaries",
                base / "knowledge" / "wiki",
                base / "projects" / "imports",
            ]:
                path.mkdir(parents=True)
            (base / "index.md").write_text("# Index\n", encoding="utf-8")
            (base / "projects" / "imports" / "ok.json").write_text(
                json.dumps({"status": "imported", "imported_at": "2026-01-01T00:00:00+00:00"}),
                encoding="utf-8",
            )
            (base / "projects" / "imports" / "err.json").write_text(
                json.dumps({"status": "error", "imported_at": "2026-01-02T00:00:00+00:00"}),
                encoding="utf-8",
            )
            status = KnowledgeBase(base).status()
            self.assertEqual(status["manifests"], 2)
            self.assertEqual(status["failed_imports"], 1)
            self.assertEqual(status["last_import_time"], "2026-01-02T00:00:00+00:00")


if __name__ == "__main__":
    unittest.main()
