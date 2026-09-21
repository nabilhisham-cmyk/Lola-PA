-- Hermes Supabase memory — full schema (fresh project)
-- Run once in the Supabase SQL Editor (Dashboard → SQL Editor → New query → paste → Run).
-- Safe to re-run: everything is IF NOT EXISTS / OR REPLACE.

-- ── Extensions ───────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS vector;     -- pgvector (semantic search)
CREATE EXTENSION IF NOT EXISTS pg_trgm;    -- trigram (fast entity ILIKE)

-- ── Base tables ──────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS memories (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    content       TEXT NOT NULL,
    category      TEXT DEFAULT 'fact',     -- fact|preference|decision|conversation|project|person
    entities      TEXT[] DEFAULT '{}',
    keywords      TEXT[] DEFAULT '{}',
    importance    FLOAT DEFAULT 0.5,
    persona       TEXT DEFAULT 'shared',
    content_hash  TEXT,
    embedding     vector(768),             -- nomic-embed-text-v1.5
    created_at    TIMESTAMPTZ DEFAULT now(),
    -- full-text search vector, auto-maintained from content
    search_vector tsvector GENERATED ALWAYS AS (to_tsvector('english', coalesce(content, ''))) STORED
);

CREATE TABLE IF NOT EXISTS interactions (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    persona            TEXT DEFAULT 'shared',
    user_content       TEXT,
    assistant_content  TEXT,
    session_id         TEXT,
    created_at         TIMESTAMPTZ DEFAULT now()
);

-- ── Indexes ──────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_memories_search   ON memories USING gin (search_vector);
CREATE INDEX IF NOT EXISTS idx_memories_entities ON memories USING gin (entities);
CREATE INDEX IF NOT EXISTS idx_memories_keywords ON memories USING gin (keywords);
CREATE INDEX IF NOT EXISTS idx_memories_persona  ON memories(persona);
CREATE INDEX IF NOT EXISTS idx_memories_importance ON memories(importance);
CREATE INDEX IF NOT EXISTS idx_memories_created  ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_hash     ON memories(content_hash);
CREATE INDEX IF NOT EXISTS idx_memories_content_trgm ON memories USING gin (content gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_memories_embedding
    ON memories USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_interactions_persona ON interactions(persona);
CREATE INDEX IF NOT EXISTS idx_interactions_created ON interactions(created_at);

-- ── Keyword search (websearch_to_tsquery handles natural multi-word text) ──
CREATE OR REPLACE FUNCTION search_memories(
    search_query TEXT, result_limit INT DEFAULT 10,
    cat TEXT DEFAULT NULL, persona_filter TEXT DEFAULT NULL
) RETURNS TABLE(
    id UUID, content TEXT, category TEXT, entities TEXT[],
    importance FLOAT, created_at TIMESTAMPTZ, rank REAL
) LANGUAGE plpgsql AS $$
BEGIN
    RETURN QUERY
    SELECT m.id, m.content, m.category, m.entities, m.importance::FLOAT, m.created_at,
           ts_rank(m.search_vector, websearch_to_tsquery('english', search_query))::REAL
    FROM memories m
    WHERE m.search_vector @@ websearch_to_tsquery('english', search_query)
      AND (cat IS NULL OR m.category = cat)
      AND (persona_filter IS NULL OR m.persona = persona_filter)
    ORDER BY rank DESC, m.importance DESC
    LIMIT result_limit;
END; $$;

-- ── Hybrid search (semantic + keyword). Embedding passed as text, cast here ──
CREATE OR REPLACE FUNCTION hybrid_search_memories(
    search_query TEXT, query_embedding TEXT, result_limit INT DEFAULT 10,
    persona_filter TEXT DEFAULT NULL, semantic_weight FLOAT DEFAULT 0.6
) RETURNS TABLE(
    id UUID, content TEXT, category TEXT, persona TEXT,
    importance FLOAT, created_at TIMESTAMPTZ, score REAL
) LANGUAGE plpgsql AS $$
DECLARE
    qvec vector(768) := query_embedding::vector(768);
BEGIN
    RETURN QUERY
    SELECT m.id, m.content, m.category, m.persona, m.importance::FLOAT, m.created_at,
           (semantic_weight * (1 - (m.embedding <=> qvec))
            + (1 - semantic_weight) *
              COALESCE(ts_rank(m.search_vector, websearch_to_tsquery('english', search_query)), 0)
           )::REAL AS score
    FROM memories m
    WHERE (persona_filter IS NULL OR m.persona = persona_filter)
      AND m.embedding IS NOT NULL
    ORDER BY score DESC, m.importance DESC
    LIMIT result_limit;
END; $$;
