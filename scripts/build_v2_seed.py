#!/usr/bin/env python3
"""Convert a PredskazBot v1 JSONL export into v2 seed JSONL.

This script does not require PostgreSQL. It prepares deterministic v2-shaped
records that can be inspected locally and later consumed by a real importer.
The goal is to make the migration observable before wiring runtime storage.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

V2_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_URL, "https://predskazbot.local/v2-seed")
LEGACY_CLAIM_CONFIDENCE = 0.20
LEGACY_CLAIM_WEIGHT = 0.20


class SeedError(RuntimeError):
    """Raised when the v2 seed build cannot continue safely."""


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def stable_uuid(*parts: object) -> str:
    raw = ":".join(str(part) for part in parts)
    return str(uuid.uuid5(V2_NAMESPACE, raw))


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def parse_args(argv: Iterable[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert PredskazBot v1 JSONL export into deterministic v2 seed JSONL.",
    )
    parser.add_argument(
        "--in",
        dest="input_path",
        default="exports/v1-export.jsonl",
        help="Input v1 export JSONL path. Default: exports/v1-export.jsonl",
    )
    parser.add_argument(
        "--out",
        dest="output_path",
        default="exports/v2-seed.jsonl",
        help="Output v2 seed JSONL path. Default: exports/v2-seed.jsonl",
    )
    return parser.parse_args(list(argv))


def read_v1_export(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        raise SeedError(f"v1 export file does not exist: {path}")

    tables: dict[str, list[dict[str, Any]]] = defaultdict(list)
    metadata_seen = False

    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue

            try:
                record = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise SeedError(f"Invalid JSON on line {line_number}: {exc}") from exc

            record_type = record.get("record_type")
            if record_type == "export_metadata":
                metadata_seen = True
                continue
            if record_type == "export_summary":
                continue
            if record_type != "table_row":
                raise SeedError(f"Unsupported record_type on line {line_number}: {record_type!r}")

            table = str(record.get("table", ""))
            data = record.get("data")
            if not table or not isinstance(data, dict):
                raise SeedError(f"Malformed table row on line {line_number}")
            tables[table].append(data)

    if not metadata_seen:
        raise SeedError("Input does not look like scripts/export_v1.py output: metadata record missing")

    return dict(tables)


def write_record(handle, entity: str, data: dict[str, Any]) -> None:
    handle.write(
        json.dumps(
            {
                "record_type": "v2_seed_row",
                "schema": "predskazbot_v2_seed_jsonl",
                "schema_version": 1,
                "entity": entity,
                "data": data,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    handle.write("\n")


def write_metadata(handle, source_export: Path, counts: dict[str, int]) -> None:
    handle.write(
        json.dumps(
            {
                "record_type": "v2_seed_metadata",
                "schema": "predskazbot_v2_seed_jsonl",
                "schema_version": 1,
                "source_export": str(source_export),
                "generated_at": utc_now(),
                "row_counts": counts,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    handle.write("\n")


def collect_chat_ids(tables: dict[str, list[dict[str, Any]]]) -> set[int]:
    chat_ids: set[int] = set()
    for rows in tables.values():
        for row in rows:
            if "chat_id" in row and row["chat_id"] is not None:
                chat_ids.add(int(row["chat_id"]))
    return chat_ids


def collect_users(tables: dict[str, list[dict[str, Any]]]) -> dict[tuple[int, int], dict[str, Any]]:
    users: dict[tuple[int, int], dict[str, Any]] = {}

    for row in tables.get("users", []):
        key = (int(row["chat_id"]), int(row["user_id"]))
        users[key] = dict(row)

    for row in tables.get("raw_messages", []):
        key = (int(row["chat_id"]), int(row["user_id"]))
        users.setdefault(
            key,
            {
                "chat_id": row["chat_id"],
                "user_id": row["user_id"],
                "username": row.get("username", ""),
                "display_name": row.get("display_name", ""),
                "first_seen": row.get("created_at"),
                "last_seen": row.get("created_at"),
            },
        )

    return users


def build_v2_seed(tables: dict[str, list[dict[str, Any]]], source_export: Path, output_path: Path) -> dict[str, int]:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = defaultdict(int)
    generated_at = utc_now()

    chat_ids = sorted(collect_chat_ids(tables))
    users = collect_users(tables)

    chat_uuid_by_telegram_id = {
        chat_id: stable_uuid("chat", chat_id)
        for chat_id in chat_ids
    }
    member_uuid_by_telegram_id = {
        user_id: stable_uuid("member", user_id)
        for _chat_id, user_id in users
    }

    with output_path.open("w", encoding="utf-8") as handle:
        for telegram_chat_id in chat_ids:
            write_record(
                handle,
                "chats",
                {
                    "id": chat_uuid_by_telegram_id[telegram_chat_id],
                    "telegram_chat_id": telegram_chat_id,
                    "title": "",
                    "type": "legacy_v1",
                    "memory_policy": {},
                    "created_at": generated_at,
                    "updated_at": generated_at,
                },
            )
            counts["chats"] += 1

        for telegram_user_id in sorted(member_uuid_by_telegram_id):
            first_seen_values = [
                row.get("first_seen") or row.get("created_at") or generated_at
                for (_chat_id, user_id), row in users.items()
                if user_id == telegram_user_id
            ]
            last_seen_values = [
                row.get("last_seen") or row.get("created_at") or generated_at
                for (_chat_id, user_id), row in users.items()
                if user_id == telegram_user_id
            ]
            write_record(
                handle,
                "members",
                {
                    "id": member_uuid_by_telegram_id[telegram_user_id],
                    "telegram_user_id": telegram_user_id,
                    "first_seen_at": min(first_seen_values),
                    "last_seen_at": max(last_seen_values),
                },
            )
            counts["members"] += 1

        for (chat_id, user_id), row in sorted(users.items()):
            write_record(
                handle,
                "chat_memberships",
                {
                    "chat_id": chat_uuid_by_telegram_id[chat_id],
                    "member_id": member_uuid_by_telegram_id[user_id],
                    "current_username": row.get("username", "") or "",
                    "current_display_name": row.get("display_name", "") or "",
                    "aliases": [],
                    "first_seen_at": row.get("first_seen") or row.get("created_at") or generated_at,
                    "last_seen_at": row.get("last_seen") or row.get("created_at") or generated_at,
                },
            )
            counts["chat_memberships"] += 1

        message_event_uuid_by_v1_id: dict[int, str] = {}
        for row in sorted(tables.get("raw_messages", []), key=lambda item: int(item.get("id", 0))):
            v1_id = int(row["id"])
            chat_id = int(row["chat_id"])
            user_id = int(row["user_id"])
            event_id = stable_uuid("message_event", chat_id, v1_id)
            message_event_uuid_by_v1_id[v1_id] = event_id
            text = row.get("text", "") or ""
            write_record(
                handle,
                "message_events",
                {
                    "id": event_id,
                    "chat_id": chat_uuid_by_telegram_id[chat_id],
                    "member_id": member_uuid_by_telegram_id.get(user_id),
                    "telegram_message_id": None,
                    "telegram_thread_id": None,
                    "reply_to_event_id": None,
                    "text": text,
                    "mentions_member_ids": [],
                    "content_hash": content_hash(f"{chat_id}:{v1_id}:{text}"),
                    "created_at": row.get("created_at") or generated_at,
                    "edited_at": None,
                    "deleted_at": None,
                    "ingested_at": generated_at,
                    "raw_payload": {"legacy_v1_id": v1_id, "mentions_json": row.get("mentions_json", "[]")},
                },
            )
            counts["message_events"] += 1

        for row in sorted(tables.get("manual_memories", []), key=lambda item: int(item.get("id", 0))):
            v1_id = int(row["id"])
            chat_id = int(row["chat_id"])
            author_user_id = int(row["author_user_id"])
            write_record(
                handle,
                "manual_memories_v2",
                {
                    "id": stable_uuid("manual_memory", chat_id, v1_id),
                    "chat_id": chat_uuid_by_telegram_id[chat_id],
                    "author_member_id": member_uuid_by_telegram_id.get(author_user_id),
                    "claim_id": None,
                    "text": row.get("text", "") or "",
                    "memory_type": "legacy_manual",
                    "pinned": True,
                    "expires_at": None,
                    "created_at": row.get("created_at") or generated_at,
                },
            )
            counts["manual_memories_v2"] += 1

        for row in tables.get("chat_memory", []):
            chat_id = int(row["chat_id"])
            legacy_fields = [
                "mood_today",
                "main_topic_today",
                "meme_of_the_day",
                "weekly_memes",
                "recent_drama",
                "popular_topics",
                "local_phrases",
                "sacred_artifacts",
                "chat_mythology",
            ]
            statement_parts = [str(row.get(field, "")).strip() for field in legacy_fields if str(row.get(field, "")).strip()]
            if not statement_parts:
                continue
            write_record(
                handle,
                "memory_claims",
                legacy_claim(
                    claim_id=stable_uuid("legacy_chat_memory", chat_id),
                    chat_id=chat_uuid_by_telegram_id[chat_id],
                    claim_type="legacy_chat_memory",
                    subject_type="chat",
                    subject_ids=[chat_uuid_by_telegram_id[chat_id]],
                    statement="; ".join(statement_parts),
                    updated_at=row.get("updated_at") or generated_at,
                ),
            )
            counts["memory_claims"] += 1

        for row in tables.get("user_profiles", []):
            chat_id = int(row["chat_id"])
            user_id = int(row["user_id"])
            member_id = member_uuid_by_telegram_id.get(user_id)
            if not member_id:
                continue
            legacy_fields = [
                "style_summary",
                "frequent_topics",
                "relationship_notes",
                "personal_memes",
                "soft_labels",
                "toxicity_style",
                "night_mode_behavior",
            ]
            statement_parts = [str(row.get(field, "")).strip() for field in legacy_fields if str(row.get(field, "")).strip()]
            if not statement_parts:
                continue
            write_record(
                handle,
                "memory_claims",
                legacy_claim(
                    claim_id=stable_uuid("legacy_user_profile", chat_id, user_id),
                    chat_id=chat_uuid_by_telegram_id[chat_id],
                    claim_type="legacy_user_profile",
                    subject_type="user",
                    subject_ids=[member_id],
                    statement="; ".join(statement_parts),
                    updated_at=row.get("updated_at") or generated_at,
                ),
            )
            counts["memory_claims"] += 1

        for row in tables.get("relationships", []):
            chat_id = int(row["chat_id"])
            user_a_id = int(row["user_a_id"])
            user_b_id = int(row["user_b_id"])
            member_a_id = member_uuid_by_telegram_id.get(user_a_id)
            member_b_id = member_uuid_by_telegram_id.get(user_b_id)
            if not member_a_id or not member_b_id:
                continue
            label = row.get("relation_type", "") or "legacy_relationship"
            write_record(
                handle,
                "relationship_edges",
                {
                    "id": stable_uuid("relationship_edge", chat_id, user_a_id, user_b_id, label),
                    "chat_id": chat_uuid_by_telegram_id[chat_id],
                    "member_a_id": member_a_id,
                    "member_b_id": member_b_id,
                    "relation_label": label,
                    "confidence": LEGACY_CLAIM_CONFIDENCE,
                    "evidence_count": int(row.get("evidence_count") or 0),
                    "last_seen_at": row.get("updated_at") or generated_at,
                    "decayed_weight": LEGACY_CLAIM_WEIGHT,
                    "updated_at": row.get("updated_at") or generated_at,
                },
            )
            counts["relationship_edges"] += 1

        write_metadata(handle, source_export, dict(counts))

    return dict(counts)


def legacy_claim(
    *,
    claim_id: str,
    chat_id: str,
    claim_type: str,
    subject_type: str,
    subject_ids: list[str],
    statement: str,
    updated_at: str,
) -> dict[str, Any]:
    return {
        "id": claim_id,
        "chat_id": chat_id,
        "claim_type": claim_type,
        "subject_type": subject_type,
        "subject_ids": subject_ids,
        "canonical_statement": statement,
        "summary_for_prompt": statement,
        "confidence": LEGACY_CLAIM_CONFIDENCE,
        "support_count": 0,
        "contradiction_count": 0,
        "first_seen_at": updated_at,
        "last_seen_at": updated_at,
        "half_life_days": 30,
        "decayed_weight": LEGACY_CLAIM_WEIGHT,
        "sensitivity": "normal",
        "visibility": "normal",
        "source": "legacy_v1_summary",
        "created_at": updated_at,
        "updated_at": updated_at,
    }


def main(argv: Iterable[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    input_path = Path(args.input_path)
    output_path = Path(args.output_path)

    try:
        tables = read_v1_export(input_path)
        counts = build_v2_seed(tables, input_path, output_path)
    except SeedError as exc:
        print(f"Seed build failed: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"Seed build I/O failed: {exc}", file=sys.stderr)
        return 3

    total_rows = sum(counts.values())
    print(f"Built {total_rows} v2 seed rows at {output_path}")
    for entity, count in sorted(counts.items()):
        print(f"- {entity}: {count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
