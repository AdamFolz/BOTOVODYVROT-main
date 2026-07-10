# Автономный деплой PredskazBot

## Вариант 1 – дешёвый VPS (рекомендую)
Hetzner CX11 ~4€/мес, Ubuntu 24.04

```bash
# на сервере
apt update && apt install -y git python3.12-venv
useradd -m -s /bin/bash predskazbot
cd /opt
git clone https://github.com/AdamFolz/BOTOVODYVROT-main predskazbot
chown -R predskazbot:predskazbot /opt/predskazbot
su - predskazbot
cd /opt/predskazbot
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env   # вставь токены
.venv/bin/python scripts/check_provider.py
exit
cp /opt/predskazbot/deploy/predskazbot.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now predskazbot
journalctl -u predskazbot -f
```

Обновление:
```bash
cd /opt/predskazbot
sudo -u predskazbot git pull
sudo systemctl restart predskazbot
```

## Вариант 2 – Docker
```bash
docker compose up -d --build
docker compose logs -f
```

## Вариант 3 – Railway / Render
- Fork репозиторий
- Railway: New Project → Deploy from GitHub
- Variables: TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL, ADMIN_USER_ID
- Start command: `python bot.py`
- Включи persistent volume для *.sqlite3 если нужно сохранять память между редеплоями

## Вариант 4 – Replit
- Import from GitHub
- Secrets: TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, OPENAI_BASE_URL, OPENAI_MODEL
- Workflow: `python main.py`
- Replit не даёт always-on бесплатно — для 24/7 лучше VPS.

---

### Провайдеры (готовые пресеты)

**vip.j3gb.com (твой текущий)**
```
OPENAI_API_KEY=твой_ключ
OPENAI_BASE_URL=https://vip.j3gb.com/v1
OPENAI_MODEL=gpt-4o-mini
# или gpt-5.5 если прокси так называет
```

**Venice.ai**
```
VENICE_API_KEY=...
# или
OPENAI_API_KEY=...
OPENAI_BASE_URL=https://api.venice.ai/api/v1
OPENAI_MODEL=qwen3-4b
```

**KIMI Code**
```
MOONSHOT_API_KEY=...
OPENAI_BASE_URL=https://api.kimi.com/coding/v1
OPENAI_MODEL=kimi-k2.7-code
```

**Moonshot**
```
MOONSHOT_API_KEY=...
OPENAI_BASE_URL=https://api.moonshot.ai/v1
OPENAI_MODEL=moonshot-v1-8k
```

Проверка:
```
python scripts/check_provider.py
```
