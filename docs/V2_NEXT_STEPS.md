# Что дальше после v1 export

Принятые решения:

1. v2 можно строить рядом с v1 и постепенно заменить v1.
2. Технические решения выбираются по качеству долгосрочной памяти: PostgreSQL для v2, SQLite только для локального v1/export.
3. Privacy mode — вариант B: заложить `/privacy`, `/export_me`, `/delete_me`, `/forget` и admin review.
4. Автоматизация памяти — бот сам предлагает наблюдения, но risky/personal claims уходят в quarantine/review.
5. Текущий запуск — локально на компьютере; production-контур позже можно вынести на бесплатный/дешёвый сервер или VPS.

## Следующий практический этап

После `scripts/export_v1.py` следующий шаг — зафиксировать v2 data model. Для этого добавлен `docs/v2_schema.sql` — PostgreSQL draft схемы evidence-first memory.

Эта схема ещё не подключена к runtime. Она нужна как контракт для следующих PR:

1. `scripts/build_v2_seed.py` — локальная конвертация v1 export в v2-shaped seed JSONL.
2. `scripts/import_v2_seed.py` или Alembic-based importer — загрузка v2 seed в PostgreSQL.
3. `src/storage/` — async PostgreSQL connection/repositories.
4. `src/ingestion/` — idempotent Telegram event writer.
5. `src/curation/` — LLM extraction в `memory_observations`, затем validation/scoring.
6. `src/retrieval/` — выбор claims для `/profile`, `/lore`, `/summary`, `/future`.

Текущий переходный режим допускает `V2_FULL_TRANSITION=1`, где prompt context уже строится из v2 seed/live и старый v1 memory curator пропускается. Это полезно для staged rollout, но не заменяет финальный repository-based runtime.

## Почему не сразу переписывать bot.py

Сначала нужно защитить данные и определить memory contract. Если сразу переписать handlers, но оставить старую модель памяти, главная проблема не исчезнет: бот продолжит превращать mutable summaries в источник истины.
