-- PredskazBot v2 evidence-first memory schema draft.
-- Target database: PostgreSQL 15+.
-- This schema is intentionally independent from the current Telegram framework:
-- Telegram-specific data enters through message_events, while profiles/lore are
-- derived from observations, claims, and evidence links.

BEGIN;

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS chats (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_chat_id BIGINT NOT NULL UNIQUE,
    title TEXT NOT NULL DEFAULT '',
    type TEXT NOT NULL DEFAULT 'unknown',
    memory_policy JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS members (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    telegram_user_id BIGINT NOT NULL UNIQUE,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS chat_memberships (
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    member_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    current_username TEXT NOT NULL DEFAULT '',
    current_display_name TEXT NOT NULL DEFAULT '',
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (chat_id, member_id)
);

CREATE TABLE IF NOT EXISTS message_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    telegram_message_id BIGINT,
    telegram_thread_id BIGINT,
    reply_to_event_id UUID REFERENCES message_events(id) ON DELETE SET NULL,
    text TEXT NOT NULL DEFAULT '',
    mentions_member_ids UUID[] NOT NULL DEFAULT '{}',
    content_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    edited_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ,
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
    UNIQUE (chat_id, telegram_message_id)
);

CREATE INDEX IF NOT EXISTS idx_message_events_chat_created
    ON message_events(chat_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_message_events_member_created
    ON message_events(member_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_message_events_text_fts
    ON message_events USING GIN (to_tsvector('simple', text));

CREATE TABLE IF NOT EXISTS memory_observations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    observation_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_ids UUID[] NOT NULL DEFAULT '{}',
    statement TEXT NOT NULL,
    stance TEXT NOT NULL DEFAULT 'uncertain',
    source_event_ids UUID[] NOT NULL DEFAULT '{}',
    evidence_snippets JSONB NOT NULL DEFAULT '[]'::jsonb,
    extractor_model TEXT NOT NULL DEFAULT '',
    extractor_prompt_version TEXT NOT NULL DEFAULT '',
    curator_confidence REAL NOT NULL DEFAULT 0 CHECK (curator_confidence >= 0 AND curator_confidence <= 1),
    status TEXT NOT NULL DEFAULT 'candidate',
    rejection_reason TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    reviewed_at TIMESTAMPTZ,
    reviewed_by_member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    CHECK (status IN ('candidate', 'accepted', 'rejected', 'needs_review')),
    CHECK (stance IN ('observed', 'jokingly_attributed', 'quoted', 'uncertain'))
);

CREATE INDEX IF NOT EXISTS idx_memory_observations_chat_status
    ON memory_observations(chat_id, status, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_observations_subject
    ON memory_observations USING GIN (subject_ids);

CREATE TABLE IF NOT EXISTS memory_claims (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    claim_type TEXT NOT NULL,
    subject_type TEXT NOT NULL,
    subject_ids UUID[] NOT NULL DEFAULT '{}',
    canonical_statement TEXT NOT NULL,
    summary_for_prompt TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0 CHECK (confidence >= 0 AND confidence <= 1),
    support_count INTEGER NOT NULL DEFAULT 0 CHECK (support_count >= 0),
    contradiction_count INTEGER NOT NULL DEFAULT 0 CHECK (contradiction_count >= 0),
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    half_life_days INTEGER NOT NULL DEFAULT 60 CHECK (half_life_days > 0),
    decayed_weight REAL NOT NULL DEFAULT 0 CHECK (decayed_weight >= 0 AND decayed_weight <= 1),
    sensitivity TEXT NOT NULL DEFAULT 'normal',
    visibility TEXT NOT NULL DEFAULT 'normal',
    source TEXT NOT NULL DEFAULT 'v2',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (sensitivity IN ('normal', 'personal', 'risky')),
    CHECK (visibility IN ('normal', 'admin_only', 'hidden'))
);

CREATE INDEX IF NOT EXISTS idx_memory_claims_chat_type_weight
    ON memory_claims(chat_id, claim_type, decayed_weight DESC, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_memory_claims_subject
    ON memory_claims USING GIN (subject_ids);

CREATE INDEX IF NOT EXISTS idx_memory_claims_prompt_fts
    ON memory_claims USING GIN (to_tsvector('simple', summary_for_prompt));

CREATE TABLE IF NOT EXISTS claim_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    claim_id UUID NOT NULL REFERENCES memory_claims(id) ON DELETE CASCADE,
    observation_id UUID REFERENCES memory_observations(id) ON DELETE SET NULL,
    event_id UUID REFERENCES message_events(id) ON DELETE SET NULL,
    evidence_role TEXT NOT NULL DEFAULT 'support',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (observation_id IS NOT NULL OR event_id IS NOT NULL),
    CHECK (evidence_role IN ('support', 'contradiction', 'context'))
);

CREATE INDEX IF NOT EXISTS idx_claim_evidence_event
    ON claim_evidence(event_id);

CREATE TABLE IF NOT EXISTS manual_memories_v2 (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    author_member_id UUID REFERENCES members(id) ON DELETE SET NULL,
    claim_id UUID REFERENCES memory_claims(id) ON DELETE SET NULL,
    text TEXT NOT NULL,
    memory_type TEXT NOT NULL DEFAULT 'note',
    pinned BOOLEAN NOT NULL DEFAULT false,
    expires_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_manual_memories_v2_chat_created
    ON manual_memories_v2(chat_id, created_at DESC);

CREATE TABLE IF NOT EXISTS relationship_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    member_a_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    member_b_id UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    relation_label TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0 CHECK (confidence >= 0 AND confidence <= 1),
    evidence_count INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
    last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decayed_weight REAL NOT NULL DEFAULT 0 CHECK (decayed_weight >= 0 AND decayed_weight <= 1),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (member_a_id <> member_b_id),
    UNIQUE (chat_id, member_a_id, member_b_id, relation_label)
);

CREATE INDEX IF NOT EXISTS idx_relationship_edges_chat_weight
    ON relationship_edges(chat_id, decayed_weight DESC, updated_at DESC);

CREATE TABLE IF NOT EXISTS daily_chronicles (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID NOT NULL REFERENCES chats(id) ON DELETE CASCADE,
    period_start DATE NOT NULL,
    period_end DATE NOT NULL,
    summary TEXT NOT NULL,
    source_event_ids UUID[] NOT NULL DEFAULT '{}',
    model TEXT NOT NULL DEFAULT '',
    prompt_version TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (chat_id, period_start, period_end)
);

CREATE TABLE IF NOT EXISTS llm_runs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    chat_id UUID REFERENCES chats(id) ON DELETE SET NULL,
    run_type TEXT NOT NULL,
    model TEXT NOT NULL,
    prompt_version TEXT NOT NULL DEFAULT '',
    input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL DEFAULT 0 CHECK (output_tokens >= 0),
    cost_usd NUMERIC(12, 6),
    status TEXT NOT NULL DEFAULT 'ok',
    error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('ok', 'failed', 'skipped'))
);

CREATE INDEX IF NOT EXISTS idx_llm_runs_chat_created
    ON llm_runs(chat_id, created_at DESC);

COMMIT;
