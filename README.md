# PredskazBot

Telegram-бот для конфы: предсказания, досье участников, лор чата, память, анти-повторы и локальная AI Knowledge Base.

## Возможности

- `/future` — персональное предсказание с памятью чата
- `/profile` — досье на себя
- `/profile @username` — досье на участника
- `/lore` — мифология и состояние конфы
- `/remember текст` — сохранить локальный факт/мем/лор
- `/summary` — краткая сводка последних событий
- `/ask вопрос` — ответ по контексту чата и базе знаний
- `/kbstatus` — статус локальной базы знаний
- `/kbsearch запрос` — поиск по локальной базе
- `/kbask вопрос` — ответ только по локальной базе с указанием источников
- `/kbimport` — импорт reply/document/url в базу знаний
- `/health` — статус OpenAI config, v1 SQLite, V2 и KB
- `/privacy` — что бот хранит и какие есть user-controls
- `/export_me` — выгрузить свои v1-данные из текущего чата
- `/delete_me CONFIRM` — удалить свои v1-данные из текущего чата
- `/forget <id>` — удалить ручную память по id, только админ
- `/whoami` — показать свой `user_id`, `chat_id` и admin status
- Автоматически сохраняет сообщения
- Автоматически обновляет профили, темы, мемы, связи и настроение чата
- Проверяет повторы перед отправкой
- Может читать локальную базу знаний из `AI_Knowledge_Base/`
- Может импортировать материалы в базу знаний прямо из Telegram

## Установка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

На Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

## Настройка

1. Создай Telegram-бота через `@BotFather`.
2. Получи токен.
3. Вставь токен в `.env`.
4. Создай OpenAI API key.
5. Вставь ключ в `.env`.

Важно: чтобы бот видел обычные сообщения в группе, у `@BotFather` выключи privacy mode:

```text
/mybots → твой бот → Bot Settings → Group Privacy → Turn off
```

## Запуск

```bash
python bot.py
```

## Добавление в чат

1. Добавь бота в группу.
2. Дай ему право читать сообщения.
3. Напиши несколько обычных сообщений.
4. Вызови:

```text
/future
```

## Команды

```text
/start
/help
/future
/profile
/profile @username
/lore
/remember Андрей — леший, который вызывает /future чаще, чем здравый смысл
/summary
/ask что чат знает про автоматизацию?
/kbstatus
/kbsearch freelance automation
/kbask что база знает про knowledge workflows?
/kbimport https://example.com/article
/health
/privacy
/export_me
/delete_me CONFIRM
/forget 1
```

## Импорт в базу знаний из Telegram

- `/kbimport <url>` — импортирует URL напрямую в локальную knowledge base
- `/kbimport` reply на текст — сохраняет текст как note и импортирует в KB
- `/kbimport` reply на document/audio/voice/video — скачивает файл в `AI_Knowledge_Base/inbox/` и добавляет в KB
- Команда админская и использует `ADMIN_USER_ID` из `.env`

## Безопасность и доступ

- `ADMIN_USER_ID` необязателен для запуска бота: без него бот стартует нормально, но `/remember`, `/kbimport`, `/forget`, `/v2status` и будущие memory-admin команды отвечают, что админ не настроен, и остаются недоступны.
- `ALLOWED_CHAT_IDS` можно оставить пустым для локального теста или заполнить через запятую, чтобы бот отвечал только в доверенных чатах.
- `/delete_me CONFIRM` удаляет v1 SQLite-данные пользователя в текущем чате. V2 raw event log пока append-only; retention/delete policy вынесена в `ROADMAP.md`.

## Roadmap

Основные цели, статусы команд, env-флаги и Definition of Done зафиксированы в `ROADMAP.md`.

## Локальная проверка

```bash
.venv\Scripts\python scripts/smoke_test_product.py
```

Скрипт проверяет импорт модулей, knowledge-base retrieval и базовую целостность продукта без Telegram token.

## Как работает память

Бот хранит сырые сообщения как факты, а профили и мемы — как вероятностные наблюдения.

Не хранится:
```text
Миша идиот
```

Хранится:
```text
В конфе часто шутят, что Миша внезапно появляется, пишет странную фразу и исчезает.
```

## Структура

```text
bot.py          Telegram handlers
database.py     SQLite layer
memory.py       memory curator and context loading
prompts.py      system prompts
models.py       dataclasses
utils.py        text helpers and anti-repeat logic
knowledge_base.py local knowledge base retrieval
```
# BOTOVODYVROT-main
