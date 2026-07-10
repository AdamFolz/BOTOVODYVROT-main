from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from typing import Any


class SeedStoreError(RuntimeError):
    """Raised when a v2 seed file cannot be read."""


class SeedStore:
    """Read-only in-memory view over v2 seed JSONL.

    This is not the production storage layer. It is a local bridge that lets us
    test v2 retrieval semantics before PostgreSQL repositories are wired in.
    """

    def __init__(self, records_by_entity: dict[str, list[dict[str, Any]]]) -> None:
        self.records_by_entity = records_by_entity
        self._chats_by_telegram_id = {
            int(row["telegram_chat_id"]): row
            for row in self.records_by_entity.get("chats", [])
        }
        self._members_by_telegram_id = {
            int(row["telegram_user_id"]): row
            for row in self.records_by_entity.get("members", [])
        }

    @classmethod
    def from_jsonl(cls, path: str | Path) -> "SeedStore":
        return cls.from_jsonl_paths([path])

    @classmethod
    def from_jsonl_paths(cls, paths: list[str | Path]) -> "SeedStore":
        records_by_entity: dict[str, list[dict[str, Any]]] = defaultdict(list)
        existing_paths = [Path(path) for path in paths if Path(path).exists()]
        if not existing_paths:
            raise SeedStoreError("no v2 seed/live JSONL files exist")

        for seed_path in existing_paths:
            with seed_path.open("r", encoding="utf-8") as handle:
                for line_number, line in enumerate(handle, start=1):
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        record = json.loads(stripped)
                    except json.JSONDecodeError as exc:
                        raise SeedStoreError(f"Invalid JSON in {seed_path} on line {line_number}: {exc}") from exc

                    if record.get("record_type") == "v2_seed_metadata":
                        continue
                    if record.get("record_type") != "v2_seed_row":
                        raise SeedStoreError(f"Unsupported seed record in {seed_path} on line {line_number}")

                    entity = str(record.get("entity", ""))
                    data = record.get("data")
                    if not entity or not isinstance(data, dict):
                        raise SeedStoreError(f"Malformed seed row in {seed_path} on line {line_number}")
                    records_by_entity[entity].append(data)

        return cls(_dedupe_records(dict(records_by_entity)))

    def chat_by_telegram_id(self, telegram_chat_id: int) -> dict[str, Any] | None:
        return self._chats_by_telegram_id.get(int(telegram_chat_id))

    def member_by_telegram_id(self, telegram_user_id: int) -> dict[str, Any] | None:
        return self._members_by_telegram_id.get(int(telegram_user_id))

    def membership(self, chat_id: str, member_id: str) -> dict[str, Any] | None:
        for row in self.records_by_entity.get("chat_memberships", []):
            if row.get("chat_id") == chat_id and row.get("member_id") == member_id:
                return row
        return None

    def message_events_for_chat(self, chat_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = [
            row for row in self.records_by_entity.get("message_events", [])
            if row.get("chat_id") == chat_id
        ]
        rows.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
        return rows[:limit]

    def manual_memories_for_chat(self, chat_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = [
            row for row in self.records_by_entity.get("manual_memories_v2", [])
            if row.get("chat_id") == chat_id
        ]
        rows.sort(key=lambda row: str(row.get("created_at", "")), reverse=True)
        return rows[:limit]

    def claims_for_chat(self, chat_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._rank_claims(
            [
                row for row in self.records_by_entity.get("memory_claims", [])
                if row.get("chat_id") == chat_id and row.get("subject_type") == "chat"
            ],
            limit,
        )

    def claims_for_member(self, chat_id: str, member_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return self._rank_claims(
            [
                row for row in self.records_by_entity.get("memory_claims", [])
                if row.get("chat_id") == chat_id and member_id in row.get("subject_ids", [])
            ],
            limit,
        )

    def relationship_edges_for_member(self, chat_id: str, member_id: str, limit: int = 20) -> list[dict[str, Any]]:
        rows = [
            row for row in self.records_by_entity.get("relationship_edges", [])
            if row.get("chat_id") == chat_id
            and member_id in {row.get("member_a_id"), row.get("member_b_id")}
        ]
        rows.sort(
            key=lambda row: (
                float(row.get("decayed_weight") or 0),
                int(row.get("evidence_count") or 0),
                str(row.get("updated_at", "")),
            ),
            reverse=True,
        )
        return rows[:limit]

    def display_name_for_member(self, chat_id: str, member_id: str) -> str:
        membership = self.membership(chat_id, member_id)
        if not membership:
            return member_id
        return membership.get("current_display_name") or membership.get("current_username") or member_id

    def _rank_claims(self, rows: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
        visible_rows = [row for row in rows if row.get("visibility", "normal") == "normal"]
        visible_rows.sort(
            key=lambda row: (
                float(row.get("decayed_weight") or 0),
                float(row.get("confidence") or 0),
                str(row.get("updated_at", "")),
            ),
            reverse=True,
        )
        return visible_rows[:limit]


def _dedupe_records(records_by_entity: dict[str, list[dict[str, Any]]]) -> dict[str, list[dict[str, Any]]]:
    key_fields_by_entity = {
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
    deduped: dict[str, list[dict[str, Any]]] = {}
    for entity, rows in records_by_entity.items():
        key_fields = key_fields_by_entity.get(entity)
        if not key_fields:
            deduped[entity] = rows
            continue
        by_key: dict[tuple[object, ...], dict[str, Any]] = {}
        passthrough: list[dict[str, Any]] = []
        for row in rows:
            key = tuple(row.get(field) for field in key_fields)
            if any(part is None or part == "" for part in key):
                passthrough.append(row)
                continue
            if entity == "chat_memberships" and key in by_key:
                by_key[key] = _merge_membership(by_key[key], row)
            else:
                by_key[key] = row
        deduped[entity] = passthrough + list(by_key.values())
    return deduped


def _merge_membership(previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    merged = dict(previous)
    merged.update(current)
    for field in ("current_username", "current_display_name"):
        if not current.get(field) and previous.get(field):
            merged[field] = previous[field]
    return merged
