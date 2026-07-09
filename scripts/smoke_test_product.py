from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def run(*args: str) -> str:
    proc = subprocess.run(
        [sys.executable, *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return (proc.stdout or proc.stderr).strip()


def main() -> int:
    run("-m", "py_compile", "bot.py", "knowledge_base.py", "prompts.py", "utils.py", "memory.py", "database.py")

    snippet = (
        "from knowledge_base import KnowledgeBase;"
        "kb=KnowledgeBase('AI_Knowledge_Base');"
        "print(kb.exists());"
        "print(json.dumps(kb.status(), ensure_ascii=False));"
        "print(len(kb.search('freelance knowledge', limit=3)));"
        "print(bool(kb.build_context('freelance knowledge', limit=2)));"
    )
    output = run("-c", "import json;" + snippet)
    lines = output.splitlines()
    assert lines[0] == "True", output
    status = json.loads(lines[1])
    assert status["summaries"] >= 1, output
    assert int(lines[2]) >= 1, output
    assert lines[3] == "True", output
    print("Smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
