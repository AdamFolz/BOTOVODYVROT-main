# ROADMAP: PredskazBot

## Product Goal

PredskazBot должен быть стабильным Telegram-ботом для малого доверенного чата: он сохраняет контекст, отвечает через память чата, работает с локальной `AI_Knowledge_Base`, даёт пользователю базовые privacy-инструменты и постепенно переходит на V2 evidence-first memory.

## Goal Levels

- MVP для личного чата: стабильный запуск, основные команды, локальная KB, allowlist, admin controls, health/privacy команды.
- V2 memory engine: V2 ingest как основной путь, idempotent события, retrieval из V2 при `V2_FULL_TRANSITION=1`, v1 только как fallback.
- Production readiness: PostgreSQL/Alembic, worker для curation, typed config, observability, retention/delete policy, admin review.

## Command Status

| Command | Status | Access | Notes |
| --- | --- | --- | --- |
| `/start`, `/help` | ready | allowed chats | Shows supported commands. |
| `/future` | ready | allowed chats | Uses chat memory plus optional KB context. |
| `/profile` | ready | allowed chats | Uses V2 retrieval first, v1 fallback when enabled. |
| `/lore` | ready | allowed chats | Uses V2 retrieval first, v1 fallback when enabled. |
| `/summary` | ready | allowed chats | Uses chat context plus optional KB context. |
| `/ask` | ready | allowed chats | Answers with chat context and KB context. |
| `/remember` | ready | admin | Saves manual memory in v1/V2 paths. |
| `/kbstatus`, `/kbsearch`, `/kbask` | ready | allowed chats | Local knowledge base status/search/answering. |
| `/kbimport` | ready | admin | Imports URL or replied Telegram file/text into KB. |
| `/health` | ready | allowed chats | Runtime status for OpenAI config, v1, V2, KB. |
| `/privacy` | ready | allowed chats | Explains stored data and user controls. |
| `/export_me` | ready | allowed chats | Exports current user's v1 data for this chat. |
| `/delete_me` | ready | allowed chats | Requires `/delete_me CONFIRM`; deletes current user's v1 data. |
| `/forget` | ready | admin | Deletes a v1 manual memory by id. |
| `/whoami`, `/v2status` | ready | self/admin | Debug and V2 status. |

## Environment Flags

| Flag | Default | Purpose |
| --- | --- | --- |
| `TELEGRAM_BOT_TOKEN` | empty | Required for polling. |
| `OPENAI_API_KEY` | empty | Required for LLM commands. |
| `ADMIN_USER_ID` | `0` | Required for runtime start; protects admin commands. |
| `ALLOWED_CHAT_IDS` | empty | Comma-separated allowlist. Empty means all chats allowed. |
| `V2_MEMORY_ENABLED` | `1` | Enables V2 storage/retrieval path. |
| `V2_FULL_TRANSITION` | `0` | Makes V2 the main runtime memory context. |
| `V1_MEMORY_FALLBACK_ENABLED` | `1` | Allows v1 fallback during transition. |
| `V2_SQLITE_PATH` | `predskazbot_v2.sqlite3` | Local V2 SQLite storage path. |
| `V2_JSONL_BRIDGE_ENABLED` | `0` | Also writes live V2 JSONL records. |
| `KNOWLEDGE_BASE_DIR` | `AI_Knowledge_Base` | Local KB path. |
| `KB_SEARCH_LIMIT` | `5` | Search hit count for KB commands. |
| `ASK_COOLDOWN_SECONDS` | `15` | Per-user `/ask` cooldown. |

## Milestones

### Phase 0: Baseline

Definition of Done:
- `ROADMAP.md` exists and reflects current command/env/runtime state.
- `README.md` links the operator to setup, smoke tests, KB workflow and V2 modes.
- Static and smoke checks pass.

### Phase 1: Stable Personal Bot

Definition of Done:
- Bot starts after `.env` is filled.
- `ADMIN_USER_ID` is required.
- `ALLOWED_CHAT_IDS` can restrict runtime.
- `/health` reports OpenAI config, v1 SQLite, V2 and KB.
- Handler smoke tests cover key non-LLM commands.

### Phase 2: Knowledge Base Source

Definition of Done:
- KB search ranks summaries/extracts above service files.
- KB status reports failed imports and last import time.
- `/kbimport` reports duplicate/import/error status clearly.
- Unit tests cover search, context, status and missing KB.

### Phase 3: V2 Memory Transition

Definition of Done:
- V2 message ingest stores Telegram message id, thread, reply, author and raw payload.
- Replay/duplicate tests pass.
- `V2_FULL_TRANSITION=1` builds `/profile` and `/lore` from V2 without v1 context.
- v1 fallback remains available until real chat acceptance is complete.

### Phase 4: Privacy And Admin

Definition of Done:
- `/privacy`, `/export_me`, `/delete_me CONFIRM` and `/forget` exist.
- Admin actions write audit logs where v1 SQLite is available.
- User-facing privacy text states current V2 append-only limitation.
- Future retention/delete work is tracked explicitly instead of hidden.

### Phase 5: Production V2 Foundation

Definition of Done:
- Typed config and application factory replace module-level wiring.
- PostgreSQL import path is documented and tested at SQL generation level.
- Curation is moved out of Telegram handlers into a worker/job boundary.
- Token/cost logging is available for OpenAI calls.

## Current Acceptance Commands

```powershell
.venv\Scripts\python.exe scripts\smoke_test_product.py
.venv\Scripts\python.exe -m unittest tests.test_v2_jsonl
.venv\Scripts\python.exe -m unittest tests.test_knowledge_base tests.test_handlers
.venv\Scripts\python.exe -m py_compile bot.py memory.py database.py knowledge_base.py prompts.py utils.py src\predskazbot_v2\*.py scripts\*.py tests\*.py
```

## Explicit Deferred Work

- PostgreSQL runtime repositories and Alembic baseline are not required for the local MVP.
- V2 raw event deletion/retention is not implemented yet; current user deletion affects v1 SQLite data.
- Full curation worker, embeddings and admin review UI remain production-readiness work.
