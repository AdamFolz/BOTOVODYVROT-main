# PredskazBot

Telegram-бот для конфы: предсказания, досье участников, лор чата, память, анти-повторы и локальная AI Knowledge Base. Built with `python-telegram-bot`, OpenAI API, and local SQLite storage (v1) plus a JSONL-backed v2 memory layer.

## Stack
- Python 3.12
- python-telegram-bot 21.10 (long polling)
- OpenAI API (via `openai` SDK)
- SQLite (via `aiosqlite` / `sqlite3`) for v1 storage; JSONL event log + SQLite for v2 memory
- File-based local Knowledge Base (`AI_Knowledge_Base/`)

## Running on Replit
- Entry point: `main.py` → calls `main()` in `bot.py`.
- Workflow `PredskazBot` runs `python main.py` (console output, no web port — this is a background Telegram polling bot, not a web app).
- Configuration lives in `.env` (see `.env.example` for all variables). Secrets (`TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`) are stored as Replit Secrets, not in `.env`. `ADMIN_USER_ID` is set as a (non-secret) environment variable since it's just a Telegram numeric ID.
- To restart after code changes, restart the `PredskazBot` workflow.

## Notes
- All core modules (`database.py`, `knowledge_base.py`, `memory.py`, `prompts.py`, `utils.py`, `models.py`) were already present and complete in the imported project — no rewrites were needed to get it running.
