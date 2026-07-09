# Быстрый запуск для новичка

## 1. Установи Python

Скачай Python 3.11+:
https://www.python.org/downloads/

При установке на Windows обязательно отметь:

```text
Add Python to PATH
```

## 2. Распакуй проект

Открой терминал в папке проекта.

## 3. Создай виртуальное окружение

macOS / Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

## 4. Установи зависимости

```bash
pip install -r requirements.txt
```

## 5. Создай .env

macOS / Linux:

```bash
cp .env.example .env
```

Windows:

```bash
copy .env.example .env
```

Открой `.env` и вставь токены. Без `TELEGRAM_BOT_TOKEN` и `OPENAI_API_KEY` команда `python bot.py` завершится ошибкой.

Проверка на Windows PowerShell:

```powershell
copy .env.example .env
notepad .env
```

После вставки токенов запускай:

```powershell
python bot.py
```

Если `predskazbot.sqlite3` ещё не существует, это нормально: он появится после успешного старта бота.


Если на Windows/Python 3.14 была ошибка `There is no current event loop`, обнови код до версии с `ensure_event_loop()` и снова запусти:

```powershell
python bot.py
```


## 6. Telegram token

В Telegram:

```text
@BotFather
/newbot
```

Скопируй токен в:

```text
TELEGRAM_BOT_TOKEN=
```

Выключи privacy mode:

```text
/mybots
Bot Settings
Group Privacy
Turn off
```

## 7. OpenAI key

Создай API key и вставь:

```text
OPENAI_API_KEY=
```

## 8. Запусти

```bash
python bot.py
```

## 9. Проверь

В группе:

```text
/future
/remember Андрей — леший, который вызывает предсказания чаще, чем здравый смысл
/lore
/profile
/summary
/whoami
```

## 10. Экспорт памяти v1 перед rewrite

Перед переходом на v2 сделай JSONL-снимок текущей SQLite-базы. Это безопасный первый шаг миграции: v1 продолжает работать, а v2 сможет импортировать историю, профили, лор и ручные воспоминания из файла.

```bash
python scripts/export_v1.py --db predskazbot.sqlite3 --out exports/v1-export.jsonl
```

Если база старая или частично пустая и в ней нет всех таблиц v1, можно сделать частичный экспорт:

```bash
python scripts/export_v1.py --db predskazbot.sqlite3 --out exports/v1-export.jsonl --allow-missing-tables
```

## 11. Подготовь v2 seed из v1 export

После экспорта можно локально сконвертировать v1 JSONL в v2-shaped seed JSONL. Для этого PostgreSQL пока не нужен: файл нужен, чтобы проверить будущую миграцию до подключения реальной v2 базы.

```bash
python scripts/build_v2_seed.py --in exports/v1-export.jsonl --out exports/v2-seed.jsonl
```


## 12. Одна команда для локальной проверки миграции

Если не хочешь запускать export и seed отдельно, используй одну команду:

```bash
python scripts/migration_preview.py --db predskazbot.sqlite3
```

Она создаст локальные приватные файлы `exports/v1-export.jsonl` и `exports/v2-seed.jsonl`.

## 13. Посмотри, что v2 уже достаёт из памяти

После `migration_preview.py` можно посмотреть retrieval preview без запуска Telegram-бота:

```bash
python scripts/query_v2_seed.py --seed exports/v2-seed.jsonl --chat-id <TELEGRAM_CHAT_ID> --mode lore
python scripts/query_v2_seed.py --seed exports/v2-seed.jsonl --chat-id <TELEGRAM_CHAT_ID> --mode profile --user-id <TELEGRAM_USER_ID>
```


## 14. Включение v2 памяти в боте

По умолчанию бот теперь пытается использовать `exports/v2-seed.jsonl` для `/profile`, `/lore` и LLM-контекста команд. Если seed-файла нет, бот автоматически остаётся на v1 памяти.

Можно явно задать путь:

```text
V2_MEMORY_ENABLED=1
V2_SEED_PATH=exports/v2-seed.jsonl
```

Если нужно временно отключить v2:

```text
V2_MEMORY_ENABLED=0
```


## 15. Live v2 ingestion

При `V2_MEMORY_ENABLED=1` новые сообщения теперь пишутся ещё и в live v2 JSONL-журнал:

```text
V2_LIVE_EVENTS_PATH=exports/v2-live-events.jsonl
```

Это не заменяет будущую PostgreSQL v2 базу, но уже не даёт новым сообщениям оставаться только в v1 SQLite во время перехода.


## 16. Ошибка OpenAI 401 / invalid API key

Если в консоли видно `Incorrect API key provided` или `401 Unauthorized`, Telegram-бот уже запустился, но OpenAI key в `.env` неверный.

Что сделать:

1. Создай новый OpenAI API key.
2. Вставь его в `.env`:

```text
OPENAI_API_KEY=sk-...
```

3. Полностью останови бота (`Ctrl+C`) и запусти снова:

```powershell
python bot.py
```

После ошибки 401 memory updates временно отключаются до перезапуска, чтобы консоль не засыпало traceback-ами.


### Безопасно проверить OpenAI key локально

Не отправляй API key в чат. Проверяй его только локально:

```powershell
python scripts/check_openai_key.py
```

Скрипт замаскирует ключ, попробует обратиться к OpenAI и скажет, валидный он или нет.


## 17. Как обновлять файлы без скачивания ZIP

Не скачивай архив с GitHub каждый раз. Один раз склонируй репозиторий через Git:

```powershell
cd M:/
git clone https://github.com/AdamFolz/BOTOVODYVROT.git
cd BOTOVODYVROT
copy .env.example .env
notepad .env
```

После этого для обновления используй:

```powershell
git pull --ff-only
python -m pip install -r requirements.txt
python bot.py
```

Или одной командой из папки проекта:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/update_and_run.ps1
```

Важно: `.env`, SQLite-база и `exports/*.jsonl` не должны попадать в GitHub. Они локальные и уже игнорируются через `.gitignore`.

### Как обновления попадают на GitHub

Я делаю изменения в ветке и оформляю PR. Чтобы они появились в основном репозитории на GitHub, PR нужно смерджить. После merge у себя на ПК запускаешь `git pull --ff-only`.


## 18. Custom OpenAI-compatible API endpoint

Если ты используешь не официальный `api.openai.com`, а совместимый endpoint/proxy, добавь в `.env`:

```text
OPENAI_BASE_URL=https://beefjerky.wujiezhidi.moe:32768
```

Если провайдер требует `/v1` в конце, укажи так:

```text
OPENAI_BASE_URL=https://beefjerky.wujiezhidi.moe:32768/v1
```

После изменения `.env` полностью перезапусти бота. Проверить локально можно так:

```powershell
python scripts/check_openai_key.py
```


## 19. Проверка ADMIN_USER_ID

Если `/remember` пишет, что команда только для админа, отправь в чат:

```text
/whoami
```

Бот покажет `user_id`, `chat_id`, текущий `ADMIN_USER_ID` и `is_admin`. Для доступа к `/remember` значение `user_id` должно совпадать с `ADMIN_USER_ID` в `.env`. После изменения `.env` перезапусти бота.

## V2 live SQLite storage (текущий шаг)

Теперь бот пишет новые сообщения не только в старую v1 SQLite, но и в отдельное v2-хранилище `predskazbot_v2.sqlite3`.
Это уже не preview JSONL: таблицы `chats`, `members`, `chat_memberships`, `message_events`, `manual_memories_v2`, `memory_claims` и `bot_responses_v2` создаются автоматически при запуске.

Проверь, что v2 включена в `.env`:

```env
V2_MEMORY_ENABLED=1
V2_SQLITE_PATH=predskazbot_v2.sqlite3
V2_JSONL_BRIDGE_ENABLED=0
```

Запусти бота и напиши в Telegram обычное сообщение, затем админом отправь:

```text
/v2status
```

Если всё нормально, бот покажет `storage: sqlite` и количество `chat_message_events` для текущего чата. Это значит, что новые сообщения уже собираются в v2 live storage.

## V2 full transition mode

Если хочешь перевести runtime memory context на v2 и отключить обычный v1 fallback для `/profile`, `/lore`, `/summary` и `/future`, включи:

```env
V2_FULL_TRANSITION=1
V1_MEMORY_FALLBACK_ENABLED=0
```

В этом режиме бот продолжает писать v2 live-данные и не полагается на v1 summaries как на основной memory context. Если v1 SQLite временно падает, входящие сообщения и `/remember` всё равно пытаются сохраниться в v2 log.

## PostgreSQL import для v2 seed/live

Если хочешь загрузить `exports/v2-seed.jsonl` или `exports/v2-live-events.jsonl` в PostgreSQL:

```powershell
python -m pip install "psycopg[binary]"
python scripts/import_v2_seed.py --seed exports/v2-seed.jsonl --database-url "postgresql://user:pass@host:5432/dbname"
```
