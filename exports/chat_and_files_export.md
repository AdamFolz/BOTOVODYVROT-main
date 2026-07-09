# PredskazBot — экспорт чата и файлов

Дата экспорта: 2026-06-26 UTC

## Контекст задачи

Пользователь попросил рассматривать проект как технический владелец: изучать систему целиком, искать слабые места, технический долг, архитектурные тупики, риски масштабирования и безопасности, а также предлагать долгосрочно устойчивые решения.

## Ключевые выводы по проекту

1. Текущий проект — рабочий v1-прототип Telegram-бота с командами `/future`, `/profile`, `/lore`, `/remember`, `/summary`, `/whoami`, `/v2status`.
2. Основная ценность продукта — долговременная память сообщества, а не отдельные команды.
3. Главная проблема v1 — mutable summary memory: LLM обновляет широкие поля `chat_memory`, `user_profiles`, `relationships`, после чего эти поля снова используются как источник контекста.
4. Это создаёт риск ложной памяти, prompt injection, устаревших ярлыков, отсутствия provenance/evidence и деградации качества через месяцы.
5. В репозитории уже есть правильное направление v2: evidence-first memory с `message_events`, `memory_observations`, `memory_claims`, `claim_evidence`, confidence/decay/visibility.
6. Рекомендованная стратегия — не чинить бесконечно v1, а строить новый v2 runtime рядом, используя v1 как прототип, reference behavior и migration source.

## Рекомендованная архитектурная стратегия

Не начинать полностью с нуля, но создать новый core/runtime:

- `app/` — config, logging, dependency container, startup;
- `telegram/` — Telegram adapter, handlers, update mapper;
- `domain/` — entities, policies, safety/retention/confidence logic;
- `storage/` — PostgreSQL repositories and migrations;
- `ingestion/` — idempotent event writer;
- `curation/` — extractor, validator, scorer, consolidator;
- `retrieval/` — planner, ranker, context builder;
- `generation/` — command orchestration, LLM client, prompt versions;
- `admin/` — privacy/export/delete/forget/review tools;
- `tests/` — unit/integration/replay tests.

## Что сохранить из текущего проекта

- Product behavior команд.
- Style prompt и формат ответов.
- Anti-repeat utilities.
- `safe_send` для Telegram.
- `docs/v2_schema.sql` как основу миграций.
- `scripts/export_v1.py` и `scripts/build_v2_seed.py` как основу миграции.
- `AUDIT_ARCHITECTURE.md` как roadmap/decision record.

## Что не тащить в новую архитектуру

- `bot.py` как central runtime.
- v1 `chat_memory` и `user_profiles` как source of truth.
- curation внутри Telegram handlers.
- in-memory cooldowns как production rate limiting.
- прямую запись LLM JSON в durable memory.
- username как стабильную identity.

## Оценка сроков из обсуждения

- Быстро запустить текущий v1 безопаснее: 1–2 рабочих дня.
- Стабильная beta с v2-памятью и privacy basics: 4–7 рабочих дней.
- Production-grade v1.0 на новой архитектуре: 2–3 недели плотной работы.
- Новый v2 runtime pragmatically minimal: 5–8 рабочих дней.

## Экспорт файлов

В этом экспорте рядом с данным файлом подготовлен архив `botovodyvrot-project-files.tar.gz`.
Архив содержит исходники и документацию репозитория без `.git`, `.env`, виртуальных окружений, Python cache и SQLite-файлов.

## Важное замечание о данных чата Telegram

В рабочем дереве на момент экспорта не найдено SQLite/JSONL-файлов с реальными данными чата (`*.sqlite3`, `*.db`, `*.jsonl`). Поэтому экспорт включает код, документацию, scripts и этот handoff-документ, но не содержит фактическую историю Telegram-чата.
Если на машине запуска бота есть `predskazbot.sqlite3`, нужно выполнить:

```bash
python scripts/export_v1.py --db predskazbot.sqlite3 --out exports/v1-export.jsonl
python scripts/build_v2_seed.py --in exports/v1-export.jsonl --out exports/v2-seed.jsonl
```

После этого реальные данные чата можно добавить в отдельный приватный архив.
