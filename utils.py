# PredskazBot v2.1 – unified provider config
# ==================================================
# Telegram
TELEGRAM_BOT_TOKEN=123456:ABC-DEF...

# --- CHOOSE ONE LLM PROVIDER ---
# 1) OpenAI (официальный)
#OPENAI_API_KEY=sk-...
#OPENAI_MODEL=gpt-4o-mini
#OPENAI_BASE_URL=

# 2) OpenAI-compatible прокси (vip.j3gb.com, bizdecipher и т.п.)
OPENAI_API_KEY=sk-proxy-key-here
OPENAI_BASE_URL=https://vip.j3gb.com/v1
OPENAI_MODEL=gpt-4o-mini

# 3) Venice.ai
#VENICE_API_KEY=...
#OPENAI_BASE_URL=https://api.venice.ai/api/v1
#OPENAI_MODEL=qwen3-4b
#  или: venice-uncensored, llama-3.3-70b, deepseek-r1-671b, ...

# 4) KIMI / Moonshot
#MOONSHOT_API_KEY=...
#  KIMI Code product:
#OPENAI_BASE_URL=https://api.kimi.com/coding/v1
#OPENAI_MODEL=kimi-k2.7-code
#  Moonshot general:
#OPENAI_BASE_URL=https://api.moonshot.ai/v1
#OPENAI_MODEL=moonshot-v1-8k

# 5) OpenRouter
#OPENROUTER_API_KEY=...
#OPENAI_BASE_URL=https://openrouter.ai/api/v1
#OPENAI_MODEL=openai/gpt-4o-mini

# 6) DeepSeek / Groq
#DEEPSEEK_API_KEY=...
#GROQ_API_KEY=...

# --- Telegram admin ---
ADMIN_USER_ID=0
ALLOWED_CHAT_IDS=

# --- storage ---
DATABASE_PATH=predskazbot.sqlite3
V2_MEMORY_ENABLED=1
V2_SQLITE_PATH=predskazbot_v2.sqlite3
V2_FULL_TRANSITION=0
V1_MEMORY_FALLBACK_ENABLED=1

# --- KB ---
KNOWLEDGE_BASE_DIR=AI_Knowledge_Base
KB_SEARCH_LIMIT=5
ASK_COOLDOWN_SECONDS=15
FUTURE_COOLDOWN_SECONDS=20
SUMMARY_COOLDOWN_SECONDS=60
