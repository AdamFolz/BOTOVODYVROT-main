from dataclasses import dataclass
from typing import Optional


@dataclass(slots=True)
class TelegramUser:
    user_id: int
    username: str
    display_name: str


@dataclass(slots=True)
class ChatMessage:
    chat_id: int
    user_id: int
    username: str
    display_name: str
    text: str
    created_at: str


@dataclass(slots=True)
class UserProfile:
    chat_id: int
    user_id: int
    username: str
    display_name: str
    style_summary: str
    frequent_topics: str
    mentioned_users: str
    relationship_notes: str
    personal_memes: str
    soft_labels: str
    energy_level: int
    toxicity_style: str
    meme_score: int
    night_mode_behavior: str
    confidence_score: float
    updated_at: str


@dataclass(slots=True)
class ChatMemory:
    chat_id: int
    mood_today: str
    chaos_level: int
    main_topic_today: str
    main_clown_today: str
    meme_of_the_day: str
    weekly_memes: str
    recent_drama: str
    popular_topics: str
    local_phrases: str
    sacred_artifacts: str
    chat_mythology: str
    updated_at: str
