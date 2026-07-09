#!/usr/bin/env python3
"""Preview v2 retrieval context from a local v2 seed JSONL file."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from predskazbot_v2 import SeedStore
from predskazbot_v2.retrieval import build_lore_context, build_profile_context


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Query v2 seed JSONL retrieval preview.")
    parser.add_argument("--seed", default="exports/v2-seed.jsonl", help="Path to v2 seed JSONL.")
    parser.add_argument("--chat-id", required=True, type=int, help="Telegram chat id.")
    parser.add_argument(
        "--mode",
        choices=("lore", "profile"),
        default="lore",
        help="Retrieval preview mode.",
    )
    parser.add_argument("--user-id", type=int, help="Telegram user id for --mode profile.")
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.mode == "profile" and args.user_id is None:
        print("--user-id is required for --mode profile", file=sys.stderr)
        return 2

    store = SeedStore.from_jsonl(args.seed)
    if args.mode == "profile":
        print(build_profile_context(store, args.chat_id, int(args.user_id)))
    else:
        print(build_lore_context(store, args.chat_id))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
