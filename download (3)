#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interactive .env wizard for PredskazBot v2.1
"""
import os, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
EXAMPLE = ROOT / ".env.example"

def ask(prompt, default=""):
    v = input(f"{prompt} [{default}]: ").strip()
    return v or default

def main():
    print("=== PredskazBot v2.1 setup ===")
    if ENV_PATH.exists():
        print(f".env уже существует: {ENV_PATH}")
        if ask("Перезаписать? y/N", "N").lower() != "y":
            print("Отмена."); return
    print("\n1) Telegram Bot Token от @BotFather")
    tg = ask("TELEGRAM_BOT_TOKEN", "")
    print("\n2) Выбери провайдера:")
    print("  1 - OpenAI")
    print("  2 - OpenAI-compatible proxy (vip.j3gb.com / bizdecipher)")
    print("  3 - Venice.ai")
    print("  4 - KIMI / Moonshot")
    print("  5 - OpenRouter")
    print("  6 - DeepSeek / Groq")
    choice = ask("Номер", "2")
    api_key = ""
    base_url = ""
    model = ""
    if choice == "1":
        api_key = ask("OPENAI_API_KEY", "")
        model = ask("OPENAI_MODEL", "gpt-4o-mini")
        base_url = ""
    elif choice == "2":
        base_url = ask("OPENAI_BASE_URL", "https://vip.j3gb.com/v1")
        api_key = ask("OPENAI_API_KEY", "")
        model = ask("OPENAI_MODEL", "gpt-4o-mini")
    elif choice == "3":
        api_key = ask("VENICE_API_KEY (или вставь в OPENAI_API_KEY)", "")
        base_url = "https://api.venice.ai/api/v1"
        model = ask("OPENAI_MODEL", "qwen3-4b")
    elif choice == "4":
        print("KIMI Code: https://api.kimi.com/coding/v1  model=kimi-k2.7-code")
        print("Moonshot: https://api.moonshot.ai/v1  model=moonshot-v1-8k")
        base_url = ask("OPENAI_BASE_URL", "https://api.moonshot.ai/v1")
        api_key = ask("MOONSHOT_API_KEY (или OPENAI_API_KEY)", "")
        model = ask("OPENAI_MODEL", "moonshot-v1-8k")
    elif choice == "5":
        api_key = ask("OPENROUTER_API_KEY", "")
        base_url = "https://openrouter.ai/api/v1"
        model = ask("OPENAI_MODEL", "openai/gpt-4o-mini")
    else:
        api_key = ask("OPENAI_API_KEY", "")
        base_url = ask("OPENAI_BASE_URL (пусто = openai.com)", "")
        model = ask("OPENAI_MODEL", "gpt-4o-mini")
    admin = ask("ADMIN_USER_ID (твой Telegram user_id, узнаешь через /whoami)", "0")
    content = f"""TELEGRAM_BOT_TOKEN={tg}
OPENAI_API_KEY={api_key}
OPENAI_BASE_URL={base_url}
OPENAI_MODEL={model}
ADMIN_USER_ID={admin}
ALLOWED_CHAT_IDS=
DATABASE_PATH=predskazbot.sqlite3
V2_MEMORY_ENABLED=1
V2_SQLITE_PATH=predskazbot_v2.sqlite3
V2_FULL_TRANSITION=0
V1_MEMORY_FALLBACK_ENABLED=1
KNOWLEDGE_BASE_DIR=AI_Knowledge_Base
KB_SEARCH_LIMIT=5
ASK_COOLDOWN_SECONDS=15
FUTURE_COOLDOWN_SECONDS=20
SUMMARY_COOLDOWN_SECONDS=60
"""
    ENV_PATH.write_text(content, encoding="utf-8")
    print(f"\n✅ .env сохранён: {ENV_PATH}")
    print("\nПроверь ключ: python scripts/check_provider.py")
    print("Запуск: python bot.py")

if __name__ == "__main__":
    main()
