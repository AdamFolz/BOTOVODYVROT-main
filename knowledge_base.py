from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_#@-]+")


def normalize_text(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"https?://\S+", " ", text)
    text = re.sub(r"[^a-zа-я0-9_#@\s-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def split_words(text: str) -> list[str]:
    return WORD_RE.findall(normalize_text(text))


@dataclass
class SearchHit:
    path: str
    line_number: int
    line: str
    score: int


class KnowledgeBase:
    def __init__(self, base_dir: str | Path | None = None) -> None:
        env_dir = (os.getenv("KNOWLEDGE_BASE_DIR") or "").strip()
        resolved = Path(base_dir or env_dir or "AI_Knowledge_Base").resolve()
        self.base_dir = resolved
        self.index_path = self.base_dir / "index.md"
        self.summaries_dir = self.base_dir / "knowledge" / "summaries"
        self.extracts_dir = self.base_dir / "extracts"
        self.imports_dir = self.base_dir / "projects" / "imports"
        self.inbox_dir = self.base_dir / "inbox"
        self.kb_script = self.base_dir / "scripts" / "kb.py"
        self.python_executable = os.getenv("KB_PYTHON") or sys.executable

    def exists(self) -> bool:
        return self.base_dir.exists() and self.index_path.exists()

    def rel(self, path: Path) -> str:
        return path.resolve().relative_to(self.base_dir.resolve()).as_posix()

    def status(self) -> dict[str, Any]:
        if not self.exists():
            return {
                "sources": 0,
                "extracts": 0,
                "summaries": 0,
                "wiki": 0,
                "manifests": 0,
                "failed_imports": 0,
                "last_import_time": "",
            }
        manifests = self.load_manifest(limit=10000)
        failed_imports = sum(1 for item in manifests if str(item.get("status", "")).startswith("error"))
        import_times = sorted(str(item.get("imported_at", "")) for item in manifests if item.get("imported_at"))
        return {
            "sources": sum(1 for p in (self.base_dir / "sources").rglob("*") if p.is_file()),
            "extracts": sum(1 for p in self.extracts_dir.rglob("*") if p.is_file()),
            "summaries": sum(1 for _ in self.summaries_dir.glob("*.md")),
            "wiki": sum(1 for _ in (self.base_dir / "knowledge" / "wiki").glob("*.md")),
            "manifests": sum(1 for _ in self.imports_dir.glob("*.json")),
            "failed_imports": failed_imports,
            "last_import_time": import_times[-1] if import_times else "",
        }

    def search(self, query: str, limit: int = 5) -> list[SearchHit]:
        if not self.exists():
            return []
        needles = split_words(query)
        if not needles:
            return []
        hits: list[SearchHit] = []
        for path in self.base_dir.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in {".md", ".txt", ".json"}:
                continue
            try:
                lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            except Exception:
                continue
            for line_number, line in enumerate(lines, start=1):
                hay = normalize_text(line)
                score = sum(2 for token in needles if token in hay)
                if score:
                    score += self._path_weight(path)
                    if all(token in hay for token in needles):
                        score += 3
                    hits.append(
                        SearchHit(
                            path=self.rel(path),
                            line_number=line_number,
                            line=line.strip(),
                            score=score,
                        )
                    )
        hits.sort(key=lambda item: (-item.score, len(item.line), item.path, item.line_number))
        return hits[:limit]

    def _path_weight(self, path: Path) -> int:
        relative = self.rel(path)
        if relative.startswith("knowledge/summaries/"):
            return 8
        if relative.startswith("extracts/"):
            return 6
        if relative.startswith("knowledge/wiki/"):
            return 5
        if relative.startswith("sources/"):
            return 3
        if relative.startswith("indexes/"):
            return 1
        if relative.startswith("projects/imports/"):
            return 0
        return 1

    def build_context(self, query: str, limit: int = 4, max_chars: int = 4000) -> str:
        hits = self.search(query, limit=limit)
        if not hits:
            return ""
        chunks: list[str] = []
        total = 0
        for hit in hits:
            block = f"Source: {hit.path}:{hit.line_number}\nExcerpt: {hit.line}"
            if total + len(block) > max_chars:
                break
            chunks.append(block)
            total += len(block) + 2
        return "\n\n".join(chunks)

    def top_summaries(self, limit: int = 5) -> list[str]:
        if not self.exists():
            return []
        paths = sorted(self.summaries_dir.glob("*.md"))
        return [self.rel(path) for path in paths[-limit:]]

    def load_manifest(self, limit: int = 5) -> list[dict[str, Any]]:
        if not self.exists():
            return []
        manifests: list[dict[str, Any]] = []
        for path in sorted(self.imports_dir.glob("*.json"))[-limit:]:
            try:
                manifests.append(json.loads(path.read_text(encoding="utf-8")))
            except Exception:
                continue
        return manifests

    def run_cli(self, *args: str) -> dict[str, Any]:
        if not self.kb_script.exists():
            raise FileNotFoundError(f"KB script not found: {self.kb_script}")
        proc = subprocess.run(
            [self.python_executable, str(self.kb_script), *args],
            cwd=self.base_dir,
            capture_output=True,
            text=True,
            check=False,
        )
        output = (proc.stdout or proc.stderr or "").strip()
        return {"code": proc.returncode, "output": output}

    def add(self, target: str) -> dict[str, Any]:
        return self.run_cli("add", target)

    def process(self) -> dict[str, Any]:
        return self.run_cli("process")

    def rebuild_index(self) -> dict[str, Any]:
        return self.run_cli("rebuild-index")

    def ensure_inbox(self) -> Path:
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        return self.inbox_dir
