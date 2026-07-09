# PredskazBot v1

Telegram-бот для конфы: предсказания, досье участников, лор чата, память, анти-повторы.

## Возможности

- `/future` — персональное предсказание с памятью чата
- `/profile` — досье на себя
- `/profile @username` — досье на участника
- `/lore` — мифология и состояние конфы
- `/remember текст` — сохранить локальный факт/мем/лор
- `/summary` — краткая сводка последних событий
- Автоматически сохраняет сообщения
- Автоматически обновляет профили, темы, мемы, связи и настроение чата
- Проверяет повторы перед отправкой

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
```

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
```

## Что исправлено в этом патче

- ответы бота отправляются через безопасный `safe_send`, без `reply_text`
- исправлен краш `Message to be replied not found`
- `/remember` теперь только для `ADMIN_USER_ID`
- добавлены cooldown для `/future` и `/summary`
- убраны сырые `print` из memory pipeline
- исправлена логика и отступы в `memory.py`
