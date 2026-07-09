---
name: PredskazBot setup
description: Telegram bot (python-telegram-bot + OpenAI-compatible) env/config quirks found during Replit import setup.
---

- `bot.py`'s `validate_env()` used to hard-require `ADMIN_USER_ID` to be a positive integer even though `.env.example` documented it as optional; fixed so the bot starts with `ADMIN_USER_ID=0` and admin-gated commands (/remember, /forget, /v2status, /kbimport) just reply that admin isn't configured.
- This bot is a long-polling process, not a web server — no port binding, use a console-output workflow (`python main.py`), not webview.
- `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `MOONSHOT_API_KEY` are secrets (Replit Secrets); `ADMIN_USER_ID` is not sensitive (numeric Telegram user ID) so it's a plain shared env var.
- KIMI Code (Moonshot AI) has an OpenAI-compatible API, but its base URL depends on which product issued the key: the "Kimi Code" console/membership key (shown at kimi.com/code, distinct from the general Moonshot Open Platform) requires `https://api.kimi.com/coding/v1`, NOT `https://api.moonshot.ai/v1` — the latter returns 401 Invalid Authentication even with a valid Kimi Code key. Model name for that product is `kimi-k2.7-code`.
