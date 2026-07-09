---
name: PredskazBot setup
description: Telegram bot (python-telegram-bot + OpenAI-compatible) env/config quirks found during Replit import setup.
---

- `bot.py`'s `validate_env()` used to hard-require `ADMIN_USER_ID` to be a positive integer even though `.env.example` documented it as optional; fixed so the bot starts with `ADMIN_USER_ID=0` and admin-gated commands (/remember, /forget, /v2status, /kbimport) just reply that admin isn't configured.
- This bot is a long-polling process, not a web server — no port binding, use a console-output workflow (`python main.py`), not webview.
- `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `MOONSHOT_API_KEY` are secrets (Replit Secrets); `ADMIN_USER_ID` is not sensitive (numeric Telegram user ID) so it's a plain shared env var.
- KIMI Code (Moonshot AI) has an OpenAI-compatible API, but its base URL depends on which product issued the key: the "Kimi Code" console/membership key (shown at kimi.com/code, distinct from the general Moonshot Open Platform) requires `https://api.kimi.com/coding/v1`, NOT `https://api.moonshot.ai/v1` — the latter returns 401 Invalid Authentication even with a valid Kimi Code key. Model name for that product is `kimi-k2.7-code`.
- The user has cycled through several third-party OpenAI-compatible reverse-proxy providers (bizdecipher.com, vip.j3gb.com) supplied as raw Codex-CLI-style TOML configs with a key pasted in chat. Auth failures on these are usually either wrong balance (`INSUFFICIENT_BALANCE`) or a missing `/v1` suffix on `base_url` — always append `/v1` to the bare domain from the TOML's `base_url` field before setting `OPENAI_BASE_URL`. Verify a new key/base_url pair with a direct curl to `{base_url}/chat/completions` before assuming the bot integration is broken.
