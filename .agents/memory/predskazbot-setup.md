---
name: PredskazBot setup
description: Telegram bot (python-telegram-bot + OpenAI) env/config quirks found during Replit import setup.
---

- `bot.py`'s `validate_env()` hard-requires `ADMIN_USER_ID` to be a positive integer, but `.env.example` documents it as optional (default `0`). Following the example literally causes a startup crash. If asked to fix, either make it truly optional in validation or update the example/docs — don't just silently change one side without checking which behavior is intended.
- This bot is a long-polling process, not a web server — no port binding, use a console-output workflow (`python main.py`), not webview.
- `TELEGRAM_BOT_TOKEN` and `OPENAI_API_KEY` are secrets (Replit Secrets); `ADMIN_USER_ID` is not sensitive (just a numeric Telegram user ID) so it's set as a plain shared env var, not requested as a secret.
