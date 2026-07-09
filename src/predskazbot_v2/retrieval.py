from __future__ import annotations

from .seed_store import SeedStore


def build_profile_context(store: SeedStore, telegram_chat_id: int, telegram_user_id: int) -> str:
    chat = store.chat_by_telegram_id(telegram_chat_id)
    if not chat:
        return f"Чат {telegram_chat_id} не найден в v2 seed."

    member = store.member_by_telegram_id(telegram_user_id)
    if not member:
        return f"Пользователь {telegram_user_id} не найден в v2 seed."

    chat_id = str(chat["id"])
    member_id = str(member["id"])
    membership = store.membership(chat_id, member_id)
    display_name = store.display_name_for_member(chat_id, member_id)

    blocks = [
        "Досье v2",
        f"Пользователь: {display_name}",
        f"Telegram user id: {telegram_user_id}",
    ]
    if membership:
        blocks.append(f"Username: @{membership.get('current_username', '')}".rstrip("@"))

    claims = store.claims_for_member(chat_id, member_id, limit=10)
    if claims:
        blocks.append("\nClaims про участника:")
        for claim in claims:
            blocks.append(format_claim(claim))
    else:
        blocks.append("\nClaims про участника пока нет.")

    relationships = store.relationship_edges_for_member(chat_id, member_id, limit=10)
    if relationships:
        blocks.append("\nСвязи:")
        for edge in relationships:
            other_member_id = edge["member_b_id"] if edge.get("member_a_id") == member_id else edge.get("member_a_id")
            other_name = store.display_name_for_member(chat_id, str(other_member_id))
            blocks.append(
                "- "
                f"{edge.get('relation_label', 'relationship')} с {other_name} "
                f"(confidence={edge.get('confidence')}, evidence={edge.get('evidence_count')})"
            )

    recent_messages = [
        row for row in store.message_events_for_chat(chat_id, limit=50)
        if row.get("member_id") == member_id
    ][:5]
    if recent_messages:
        blocks.append("\nПоследние сообщения участника:")
        for row in recent_messages:
            blocks.append(f"- {row.get('text', '')}")

    return "\n".join(blocks)


def build_lore_context(store: SeedStore, telegram_chat_id: int) -> str:
    chat = store.chat_by_telegram_id(telegram_chat_id)
    if not chat:
        return f"Чат {telegram_chat_id} не найден в v2 seed."

    chat_id = str(chat["id"])
    blocks = [
        "Лор v2",
        f"Telegram chat id: {telegram_chat_id}",
    ]

    claims = store.claims_for_chat(chat_id, limit=15)
    if claims:
        blocks.append("\nClaims про чат:")
        for claim in claims:
            blocks.append(format_claim(claim))
    else:
        blocks.append("\nClaims про чат пока нет.")

    manual_memories = store.manual_memories_for_chat(chat_id, limit=10)
    if manual_memories:
        blocks.append("\nРучная память:")
        for row in manual_memories:
            blocks.append(f"- {row.get('text', '')}")

    recent_messages = store.message_events_for_chat(chat_id, limit=10)
    if recent_messages:
        blocks.append("\nСвежие сообщения:")
        for row in recent_messages:
            blocks.append(f"- {row.get('text', '')}")

    return "\n".join(blocks)


def format_claim(claim: dict[str, object]) -> str:
    return (
        "- "
        f"{claim.get('summary_for_prompt', '')} "
        f"(confidence={claim.get('confidence')}, weight={claim.get('decayed_weight')}, source={claim.get('source')})"
    )
