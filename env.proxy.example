#!/usr/bin/env python3
"""Run the local v1 -> v2 migration preview in one command.

For personal/local usage this is easier than running export_v1.py and
build_v2_seed.py separately. It does not modify the bot database: the v1 SQLite
file is opened read-only by export_v1.py, then the exported JSONL is converted
into deterministic v2 seed JSONL.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

from build_v2_seed import SeedError, build_v2_seed, read_v1_export
from export_v1 import ExportError, export_database


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview local migration: v1 SQLite -> v1 JSONL export -> v2 seed JSONL.",
    )
    parser.add_argument(
        "--db",
        default="predskazbot.sqlite3",
        help="Path to the v1 SQLite database. Default: predskazbot.sqlite3",
    )
    parser.add_argument(
        "--export-out",
        default="exports/v1-export.jsonl",
        help="Where to write the intermediate v1 export JSONL.",
    )
    parser.add_argument(
        "--seed-out",
        default="exports/v2-seed.jsonl",
        help="Where to write the v2 seed JSONL.",
    )
    parser.add_argument(
        "--allow-missing-tables",
        action="store_true",
        help="Allow partial exports if an old/local database is missing some v1 tables.",
    )
    return parser.parse_args(list(argv))


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    db_path = Path(args.db)
    export_path = Path(args.export_out)
    seed_path = Path(args.seed_out)

    try:
        print("Step 1/2: exporting v1 SQLite to JSONL...")
        export_counts = export_database(
            db_path=db_path,
            out_path=export_path,
            allow_missing_tables=bool(args.allow_missing_tables),
        )
        print(f"Export written: {export_path}")
        for table, count in sorted(export_counts.items()):
            print(f"- v1 {table}: {count}")

        print("\nStep 2/2: building v2 seed JSONL...")
        tables = read_v1_export(export_path)
        seed_counts = build_v2_seed(tables, export_path, seed_path)
        print(f"Seed written: {seed_path}")
        for entity, count in sorted(seed_counts.items()):
            print(f"- v2 {entity}: {count}")
    except ExportError as exc:
        print(f"Migration preview failed: {exc}", file=sys.stderr)
        print("", file=sys.stderr)
        print("Что делать:", file=sys.stderr)
        print("1. Если бот ещё ни разу не запускался, сначала создай .env и запусти python bot.py.", file=sys.stderr)
        print("2. Если база лежит в другом месте, передай путь: python scripts/migration_preview.py --db path/to/db.sqlite3", file=sys.stderr)
        print("3. Если база задана в .env как DATABASE_PATH, используй этот путь в --db.", file=sys.stderr)
        return 2
    except SeedError as exc:
        print(f"Seed build failed: {exc}", file=sys.stderr)
        return 3

    print("\nDone. These files are local/private and are ignored by git:")
    print(f"- {export_path}")
    print(f"- {seed_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
