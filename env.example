#!/usr/bin/env python3
"""Export PredskazBot v1 SQLite data to JSONL.

This is the first safe migration step for the v2 rewrite: keep the current
SQLite database as the source of truth, export every v1 table as plain JSONL,
and let future import/backfill tools build the evidence-first schema from this
snapshot.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

V1_TABLES: tuple[str, ...] = (
    "users",
    "raw_messages",
    "user_profiles",
    "chat_memory",
    "relationships",
    "bot_responses",
    "manual_memories",
    "meta",
)


class ExportError(RuntimeError):
    """Raised when the v1 export cannot be completed safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export PredskazBot v1 SQLite tables to JSONL for v2 migration.",
    )
    parser.add_argument(
        "--db",
        default="predskazbot.sqlite3",
        help="Path to the v1 SQLite database. Default: predskazbot.sqlite3",
    )
    parser.add_argument(
        "--out",
        default="exports/v1-export.jsonl",
        help="Output JSONL path. Default: exports/v1-export.jsonl",
    )
    parser.add_argument(
        "--allow-missing-tables",
        action="store_true",
        help="Export existing tables and record missing v1 tables instead of failing.",
    )
    return parser.parse_args(list(argv))


def connect_readonly(db_path: Path) -> sqlite3.Connection:
    if not db_path.exists():
        raise ExportError(f"Database file does not exist: {db_path}")

    uri = f"file:{db_path.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def existing_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        """,
    ).fetchall()
    return {str(row["name"]) for row in rows}


def table_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    return [str(row["name"]) for row in rows]


def table_rows(conn: sqlite3.Connection, table: str) -> Iterable[sqlite3.Row]:
    return conn.execute(f'SELECT * FROM "{table}"')


def normalize_row(row: sqlite3.Row, columns: list[str]) -> dict[str, Any]:
    return {column: row[column] for column in columns}


def write_jsonl_record(handle, record: dict[str, Any]) -> None:
    handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True))
    handle.write("\n")


def export_database(db_path: Path, out_path: Path, allow_missing_tables: bool) -> dict[str, int]:
    with connect_readonly(db_path) as conn:
        present_tables = existing_tables(conn)
        missing_tables = [table for table in V1_TABLES if table not in present_tables]

        if missing_tables and not allow_missing_tables:
            missing = ", ".join(missing_tables)
            raise ExportError(
                "Database is missing expected v1 tables: "
                f"{missing}. Use --allow-missing-tables for partial exports.",
            )

        out_path.parent.mkdir(parents=True, exist_ok=True)
        counts: dict[str, int] = {table: 0 for table in V1_TABLES}

        with out_path.open("w", encoding="utf-8") as handle:
            write_jsonl_record(
                handle,
                {
                    "record_type": "export_metadata",
                    "schema": "predskazbot_v1_jsonl",
                    "schema_version": 1,
                    "exported_at": utc_now(),
                    "source_db": str(db_path),
                    "tables": list(V1_TABLES),
                    "missing_tables": missing_tables,
                },
            )

            for table in V1_TABLES:
                if table not in present_tables:
                    continue

                columns = table_columns(conn, table)
                for row in table_rows(conn, table):
                    write_jsonl_record(
                        handle,
                        {
                            "record_type": "table_row",
                            "schema": "predskazbot_v1_jsonl",
                            "schema_version": 1,
                            "table": table,
                            "data": normalize_row(row, columns),
                        },
                    )
                    counts[table] += 1

            write_jsonl_record(
                handle,
                {
                    "record_type": "export_summary",
                    "schema": "predskazbot_v1_jsonl",
                    "schema_version": 1,
                    "exported_at": utc_now(),
                    "source_db": str(db_path),
                    "row_counts": counts,
                },
            )

    return counts


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    db_path = Path(args.db)
    out_path = Path(args.out)

    try:
        counts = export_database(
            db_path=db_path,
            out_path=out_path,
            allow_missing_tables=bool(args.allow_missing_tables),
        )
    except ExportError as exc:
        print(f"Export failed: {exc}", file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"SQLite export failed: {exc}", file=sys.stderr)
        return 3

    total_rows = sum(counts.values())
    print(f"Exported {total_rows} rows to {out_path}")
    for table in V1_TABLES:
        print(f"- {table}: {counts[table]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
