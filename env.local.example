from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable


TABLE_ORDER = [
    "chats",
    "members",
    "chat_memberships",
    "message_events",
    "memory_observations",
    "memory_claims",
    "claim_evidence",
    "manual_memories_v2",
    "relationship_edges",
    "daily_chronicles",
    "llm_runs",
]

CONFLICT_TARGETS = {
    "chats": ("id",),
    "members": ("id",),
    "chat_memberships": ("chat_id", "member_id"),
    "message_events": ("id",),
    "memory_observations": ("id",),
    "memory_claims": ("id",),
    "claim_evidence": ("id",),
    "manual_memories_v2": ("id",),
    "relationship_edges": ("id",),
    "daily_chronicles": ("id",),
    "llm_runs": ("id",),
}


class V2ImportError(RuntimeError):
    pass


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import v2 seed JSONL into PostgreSQL.")
    parser.add_argument("--seed", default="exports/v2-seed.jsonl", help="Path to v2 seed/live JSONL.")
    parser.add_argument("--database-url", default=os.getenv("V2_DATABASE_URL", ""), help="PostgreSQL DSN. Defaults to V2_DATABASE_URL.")
    return parser.parse_args(list(argv))


def read_seed(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        raise V2ImportError(f"v2 seed file does not exist: {path}")
    rows_by_entity = {entity: [] for entity in TABLE_ORDER}
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise V2ImportError(f"Invalid JSON on line {line_number}: {exc}") from exc
            if record.get("record_type") == "v2_seed_metadata":
                continue
            if record.get("record_type") != "v2_seed_row":
                raise V2ImportError(f"Unsupported record_type on line {line_number}: {record.get('record_type')!r}")
            entity = str(record.get("entity", ""))
            data = record.get("data")
            if entity not in rows_by_entity:
                raise V2ImportError(f"Unsupported v2 entity on line {line_number}: {entity!r}")
            if not isinstance(data, dict) or not data:
                raise V2ImportError(f"Malformed data object on line {line_number}")
            rows_by_entity[entity].append(data)
    return rows_by_entity


def quote_identifier(identifier: str) -> str:
    if not identifier or not identifier.replace("_", "").isalnum() or identifier[0].isdigit():
        raise V2ImportError(f"Unsafe SQL identifier: {identifier!r}")
    return '"' + identifier.replace('"', '""') + '"'


def upsert_sql(table: str, row: dict[str, Any]) -> str:
    columns = list(row)
    placeholders = ", ".join(["%s"] * len(columns))
    quoted_table = quote_identifier(table)
    quoted_columns = ", ".join(quote_identifier(column) for column in columns)
    conflict_columns = ", ".join(quote_identifier(column) for column in CONFLICT_TARGETS[table])
    update_columns = [column for column in columns if column not in CONFLICT_TARGETS[table]]
    if update_columns:
        assignments = ", ".join(
            f"{quote_identifier(column)}=EXCLUDED.{quote_identifier(column)}"
            for column in update_columns
        )
        conflict_action = f"DO UPDATE SET {assignments}"
    else:
        conflict_action = "DO NOTHING"
    return f"INSERT INTO {quoted_table} ({quoted_columns}) VALUES ({placeholders}) ON CONFLICT ({conflict_columns}) {conflict_action}"


def import_rows(database_url: str, rows_by_entity: dict[str, list[dict[str, Any]]]) -> dict[str, int]:
    if not database_url:
        raise V2ImportError("PostgreSQL DSN is required. Pass --database-url or set V2_DATABASE_URL.")
    try:
        import psycopg
    except ModuleNotFoundError as exc:
        raise V2ImportError("Install psycopg before importing: python -m pip install 'psycopg[binary]'") from exc

    counts: dict[str, int] = {}
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            for entity in TABLE_ORDER:
                rows = rows_by_entity.get(entity, [])
                for row in rows:
                    cur.execute(upsert_sql(entity, row), list(row.values()))
                counts[entity] = len(rows)
        conn.commit()
    return counts


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        rows_by_entity = read_seed(Path(args.seed))
        counts = import_rows(args.database_url, rows_by_entity)
    except V2ImportError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    print(json.dumps(counts, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
