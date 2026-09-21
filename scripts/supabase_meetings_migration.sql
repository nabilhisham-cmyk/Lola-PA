-- ─────────────────────────────────────────────────────────────────────
-- Lola PA — meeting transcripts (v4)
--
-- Stores long-form meeting recordings and their transcripts so minutes are
-- retrievable later. A transcript that lives only in one Telegram message is
-- lost the moment the conversation scrolls.
--
-- Note on scope: Telegram voice notes are already transcribed by the gateway
-- before the agent sees them, and are NOT stored here. This table is for real
-- meetings: a site walkthrough, a supplier negotiation, a coordination call.
-- Those arrive as audio or video files, run far longer, and are worth keeping.
--
-- Note on speaker attribution: faster-whisper does not diarise, so there are
-- deliberately no per-speaker columns. Inventing them would produce minutes that
-- attribute decisions to the wrong person, which is worse than no attribution.
-- Participants are recorded as a free-text list of who was present.
--
-- Safe to re-run.
-- ─────────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS meetings (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title            TEXT,
    event_id         UUID REFERENCES events(id) ON DELETE SET NULL,
    meeting_date     DATE,
    participants     TEXT,                  -- free text list of who was present
    language         TEXT,                  -- detected or supplied ISO code
    transcript       TEXT,                  -- the full transcript, verbatim
    minutes          TEXT,                  -- optional structured summary
    duration_seconds NUMERIC(10,1),
    source_file      TEXT,                  -- path the audio came from
    source           TEXT DEFAULT 'upload', -- upload | forwarded | other
    transcribed_at   TIMESTAMPTZ,
    created_at       TIMESTAMPTZ DEFAULT now(),
    updated_at       TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_meetings_event ON meetings(event_id);
CREATE INDEX IF NOT EXISTS idx_meetings_date  ON meetings(meeting_date DESC);
CREATE INDEX IF NOT EXISTS idx_meetings_tx    ON meetings USING gin (to_tsvector('english', coalesce(transcript, '')));

-- Full-text search across transcripts. The point of keeping them is being able
-- to answer "when did we agree the load-in time?" months later.
--
-- Two naming traps here, both caught by running the migration rather than
-- reading it:
--   1. `rank` is a reserved word in Postgres and cannot be used bare.
--   2. A RETURNS TABLE output column name is NOT a valid ORDER BY alias inside
--      the function body. Ordering must repeat the expression.
CREATE OR REPLACE FUNCTION search_meetings(
    search_query TEXT, result_limit INT DEFAULT 10
) RETURNS TABLE(
    id UUID, title TEXT, meeting_date DATE, event_name TEXT,
    snippet TEXT, match_rank REAL
) LANGUAGE sql STABLE AS $$
    SELECT m.id, m.title, m.meeting_date, e.name,
           ts_headline('english', coalesce(m.transcript, ''),
                       websearch_to_tsquery('english', search_query),
                       'MaxFragments=2, MaxWords=18'),
           ts_rank(to_tsvector('english', coalesce(m.transcript, '')),
                   websearch_to_tsquery('english', search_query))::REAL AS match_rank
    FROM meetings m
    LEFT JOIN events e ON e.id = m.event_id
    WHERE to_tsvector('english', coalesce(m.transcript, ''))
          @@ websearch_to_tsquery('english', search_query)
    ORDER BY ts_rank(to_tsvector('english', coalesce(m.transcript, '')),
                     websearch_to_tsquery('english', search_query)) DESC,
             m.meeting_date DESC NULLS LAST
    LIMIT result_limit;
$$;

DO $$
BEGIN
    EXECUTE 'DROP TRIGGER IF EXISTS trg_touch_meetings ON meetings;
             CREATE TRIGGER trg_touch_meetings BEFORE UPDATE ON meetings
             FOR EACH ROW EXECUTE FUNCTION touch_updated_at();';
END $$;
