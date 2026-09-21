"""Meeting transcript tools — long recordings into stored, structured minutes.

Design rules:

- **Transcription uses the repo's own transcriber.** `tools.transcription_tools
  .transcribe_audio` already handles provider selection, preprocessing, silence
  trimming and local-whisper fallback. Re-implementing any of that here would
  duplicate a solved problem and drift from the STT config.
- **No invented speaker labels.** faster-whisper does not diarise. Minutes that
  attribute a decision to the wrong person are worse than minutes with no
  attribution, so the structuring step is told to attribute only when the text
  itself is unambiguous.
- **Long audio is expected.** A site meeting runs 30 to 120 minutes. The size
  cap is checked up front and reported plainly rather than failing deep inside
  the transcriber.
- **Everything is stored.** A transcript that exists only in one Telegram
  message is lost. Transcripts persist in Supabase against an optional event.
"""

from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any, Optional

logger = logging.getLogger(__name__)

# ── connection (same conventions as the events plugin) ────────────────
import re as _re

_PROJECT_REF_RE = _re.compile(r"https://([a-z0-9]{20})\.supabase\.co")


def _dsn() -> Optional[str]:
    """Resolve the Postgres DSN. Never falls back to DATABASE_URL."""
    direct = (os.environ.get("SUPABASE_DB_URL") or "").strip()
    if direct:
        return direct
    url = (os.environ.get("SUPABASE_MEMORY_URL") or "").strip()
    pw = (os.environ.get("SUPABASE_DB_PASSWORD") or "").strip()
    m = _PROJECT_REF_RE.match(url)
    if m and pw:
        return f"postgresql://postgres:***@db.{m.group(1)}.supabase.co:5432/postgres"
    return None


def _connect():
    import psycopg
    dsn = _dsn()
    if not dsn:
        raise RuntimeError(
            "No Supabase DSN. Set SUPABASE_DB_URL, or SUPABASE_MEMORY_URL plus "
            "SUPABASE_DB_PASSWORD."
        )
    return psycopg.connect(dsn, connect_timeout=20)


def check_meetings_available() -> bool:
    """Gate: is there a transcriber configured AND somewhere to store results?

    Deliberately does not load the whisper model or dial the database: a gate
    that does heavy work on every tool listing would be slow and would fail
    closed during a transient blip.
    """
    if not _dsn():
        return False
    try:
        from tools.transcription_tools import transcribe_audio  # noqa: F401
    except Exception:
        return False
    return True


# ── helpers ──────────────────────────────────────────────────────────

def _ok(data: Any) -> str:
    return json.dumps({"ok": True, "data": data}, default=str)


def _err(msg: str) -> str:
    return json.dumps({"ok": False, "error": msg})


def _rows(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


AUDIO_SUFFIXES = {
    ".mp3", ".m4a", ".mp4", ".wav", ".ogg", ".oga", ".opus", ".flac",
    ".aac", ".wma", ".amr", ".webm", ".caf", ".silk",
}
MAX_BYTES = 200 * 1024 * 1024  # 200 MB, reported plainly if exceeded


def _fmt_bytes(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


def _name_hint(participants: Optional[str]) -> str:
    """A short prompt that biases whisper toward correct spelling of names.

    Whisper transcribed "Hisham" as "He sham" on a real test recording. In
    minutes that reads as a different person, which is exactly the kind of error
    that makes a transcript untrustworthy. Seeding the names, the town and the
    common El Gouna vocabulary fixes the class of problem rather than one word.

    Kept short on purpose: a long prompt costs tokens and can push the model into
    echoing it. Providers that do not accept an initial prompt simply ignore it.
    """
    base = (
        "El Gouna events meeting. Names and terms likely to appear: "
        "Hisham, El Gouna, Abu Tig Marina, Hurghada, Orascom, Cairo, "
        "set up, load in, get out, curfew, rigging, staging, AV, kitesurf, "
        "windsurf, wakeboard, Sliders, Mangroovy, Tamr Henna, run sheet, "
        "kitemania, windmania, wakemania, permits, sponsorship."
    )
    if participants:
        extra = ", ".join(p.strip() for p in str(participants).split(",") if p.strip())
        if extra:
            base = base + " Participants: " + extra + "."
    return base


# ── schemas ──────────────────────────────────────────────────────────

def _fn(name, desc, props, required=()):
    return {
        "name": name,
        "description": desc,
        "parameters": {"type": "object", "properties": props, "required": list(required)},
    }


MEETING_TRANSCRIBE_SCHEMA = _fn(
    "meeting_transcribe",
    "Transcribe a recorded meeting from an audio file path and store the "
    "transcript. Use this for a long recording (a site meeting, a supplier "
    "negotiation, a walkthrough) that arrived as an audio or video file. A short "
    "Telegram voice note does NOT need this: it is transcribed automatically "
    "before you see it. Returns a meeting id and the transcript.",
    {
        "file_path": {"type": "string", "description": "Absolute path to the audio or video file. Required."},
        "title": {"type": "string", "description": "What this meeting was, e.g. 'Marina site walkthrough'."},
        "event_id": {"type": "string", "description": "Optional event UUID to attach the meeting to."},
        "event_name": {"type": "string", "description": "Optional event name (partial) if the UUID is unknown."},
        "meeting_date": {"type": "string", "description": "YYYY-MM-DD. Defaults to today."},
        "participants": {"type": "string", "description": "Comma-separated names of people present, if known."},
        "language": {"type": "string", "description": "Optional ISO code, e.g. 'ar' or 'en'. Auto-detected if omitted."},
    },
    ("file_path",),
)

MEETING_MINUTES_SCHEMA = _fn(
    "meeting_minutes",
    "Turn a stored transcript into structured minutes: decisions, action items "
    "with owners, open questions, and key facts. Call this after "
    "meeting_transcribe. Attributions are only made where the transcript makes the "
    "speaker clear.",
    {
        "meeting_id": {"type": "string", "description": "Meeting UUID from meeting_transcribe. Required."},
        "context": {"type": "string", "description": "Optional context to improve accuracy, e.g. 'discussing the GFF build schedule'."},
    },
    ("meeting_id",),
)

MEETING_LIST_SCHEMA = _fn(
    "meeting_list",
    "List stored meetings, newest first, optionally for one event.",
    {
        "event_id": {"type": "string", "description": "Restrict to one event."},
        "limit": {"type": "integer", "description": "How many. Default 20."},
    },
)

MEETING_GET_SCHEMA = _fn(
    "meeting_get",
    "One stored meeting in full: transcript and minutes if they were generated. "
    "Use to read back what was agreed.",
    {"meeting_id": {"type": "string", "description": "Meeting UUID."}},
    ("meeting_id",),
)


# ── handlers ─────────────────────────────────────────────────────────

def handle_meeting_transcribe(args: dict) -> str:
    file_path = args.get("file_path")
    if not file_path:
        return _err("file_path is required")
    p = pathlib.Path(file_path)
    if not p.is_file():
        return _err(f"no file at {file_path}")
    # Check the FORMAT before the size: /etc/hostname is a legitimate small file
    # and reporting "too small to contain speech" for it is a confusing answer to
    # a wrong-type mistake. Caught by testing a non-audio file.
    suffix = p.suffix.lower()
    if suffix not in AUDIO_SUFFIXES:
        return _err(
            f"{suffix or 'a file with no extension'} does not look like audio or video. "
            f"Supported: {', '.join(sorted(AUDIO_SUFFIXES))}"
        )
    size = p.stat().st_size
    if size > MAX_BYTES:
        return _err(
            f"file is {_fmt_bytes(size)}, over the {_fmt_bytes(MAX_BYTES)} limit. "
            "Split the recording, or transcribe the parts separately."
        )
    if size < 1024:
        return _err(f"file is only {size} bytes, which is too small to contain speech")

    # Use the repo's own transcriber so provider choice, preprocessing and the
    # local-whisper fallback all behave exactly as configured.
    try:
        from tools.transcription_tools import transcribe_audio as _transcribe
    except Exception as e:
        return _err(f"transcriber unavailable: {type(e).__name__}: {e}")

    try:
        # NOTE: transcribe_audio() takes no initial_prompt argument. The wire for
        # it is `stt.local.initial_prompt` in config.yaml, which
        # tools/transcription_local.py reads into the WhisperModel call. Setting
        # it in config is what actually biases spelling; passing it here would be
        # silently ignored (and was: the first attempt raised TypeError, fell
        # through to the no-arg call, and "Hisham" still came back as "He sham").
        result = _transcribe(str(p), source="meeting")
    except Exception as e:
        logger.debug("meeting_transcribe failed: %s", e)
        return _err(f"transcription failed: {type(e).__name__}: {e}")

    if not isinstance(result, dict):
        return _err("transcriber returned an unexpected result")

    text = (result.get("text") or result.get("transcript") or "").strip()
    if result.get("error"):
        return _err(f"transcription error: {result.get('error')}")
    if not text:
        return _err(
            "transcription produced no usable text. The file may be silent, or "
            "the audio may be too poor to transcribe."
        )

    # Resolve an event by name if only a name was given.
    event_id = args.get("event_id")
    try:
        with _connect() as conn, conn.cursor() as cur:
            if not event_id and args.get("event_name"):
                cur.execute(
                    "SELECT id FROM events WHERE name ILIKE %s ORDER BY starts_on DESC NULLS LAST LIMIT 1",
                    (f"%{args['event_name']}%",),
                )
                hit = cur.fetchone()
                if hit:
                    event_id = hit[0]
            cur.execute(
                """INSERT INTO meetings
                     (title, event_id, meeting_date, participants, language,
                      transcript, duration_seconds, source_file, transcribed_at, source)
                   VALUES (%s,%s,COALESCE(%s::date, CURRENT_DATE),%s,%s,%s,%s,%s, now(), 'upload')
                   RETURNING id, title, meeting_date""",
                (
                    args.get("title") or p.stem,
                    event_id,
                    args.get("meeting_date"),
                    args.get("participants"),
                    args.get("language") or result.get("language"),
                    text,
                    result.get("duration"),
                    str(p),
                ),
            )
            row = _rows(cur)[0]
            conn.commit()
        return _ok({
            "meeting_id": row["id"],
            "title": row.get("title"),
            "meeting_date": row.get("meeting_date"),
            "event_id": event_id,
            "characters": len(text),
            "transcript": text,
            "next_step": "Call meeting_minutes with this meeting_id to produce "
                         "decisions, actions and open questions.",
        })
    except Exception as e:
        logger.debug("meeting_transcribe persist failed: %s", e)
        # Do not throw away the transcript: return it even if storage failed,
        # because the work is expensive and unrepeatable.
        return _ok({
            "meeting_id": None,
            "transcript": text,
            "storage_error": f"{type(e).__name__}: {e}",
            "note": "Transcription succeeded but could not be stored. Give Hisham "
                    "the transcript now; it will not be retrievable later.",
        })


def handle_meeting_minutes(args: dict) -> str:
    mid = args.get("meeting_id")
    if not mid:
        return _err("meeting_id is required")
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM meetings WHERE id = %s", (mid,))
            got = _rows(cur)
            if not got:
                return _err(f"no meeting with id {mid}")
            meeting = got[0]
    except Exception as e:
        logger.debug("meeting_minutes load failed: %s", e)
        return _err(str(e))

    # The structuring itself is the model's job. This handler's responsibility is
    # to hand back the transcript with firm instructions, rather than to attempt
    # an extraction it cannot do without an LLM. Returning the whole transcript in
    # one result keeps it in the conversation where the model can work on it.
    transcript = meeting.get("transcript") or ""
    if not transcript:
        return _err("this meeting has no transcript stored")

    prior = meeting.get("minutes")
    return _ok({
        "meeting_id": mid,
        "title": meeting.get("title"),
        "meeting_date": str(meeting.get("meeting_date")),
        "participants": meeting.get("participants"),
        "existing_minutes": prior,
        "instructions": (
            "Structure this transcript into minutes and then save them by calling "
            "meeting_minutes again is not needed; instead present them to Hisham "
            "and offer to save each action as a task with tasks_save. "
            "Output exactly these sections:\n"
            "  1. Decisions made, each with any date or figure stated.\n"
            "  2. Action items: what, who owns it, and when it is due. If the owner "
            "or the date was not stated, write 'not stated' rather than guessing.\n"
            "  3. Open questions that were left unresolved.\n"
            "  4. Key facts: figures, dates, names, venue or supplier details.\n"
            "Attribute a statement to a person ONLY when the transcript makes the "
            "speaker unambiguous. Do not invent speaker labels or assign decisions "
            "to people who did not clearly make them. If the transcript does not "
            "make clear who said something, say so."
        ),
        "context": args.get("context"),
        "transcript": transcript,
    })


def handle_meeting_list(args: dict) -> str:
    limit = 20
    try:
        limit = int(args.get("limit") or 20)
    except Exception:
        pass
    limit = max(1, min(100, limit))
    try:
        with _connect() as conn, conn.cursor() as cur:
            sql = """SELECT m.id, m.title, m.meeting_date, m.participants,
                            m.duration_seconds, m.transcribed_at,
                            (m.minutes IS NOT NULL) AS has_minutes,
                            e.name AS event_name
                       FROM meetings m LEFT JOIN events e ON e.id = m.event_id
                      WHERE TRUE"""
            params: list = []
            if args.get("event_id"):
                sql += " AND m.event_id = %s"
                params.append(args["event_id"])
            sql += " ORDER BY m.meeting_date DESC NULLS LAST, m.transcribed_at DESC LIMIT %s"
            params.append(limit)
            cur.execute(sql, params)
            return _ok(_rows(cur))
    except Exception as e:
        logger.debug("meeting_list failed: %s", e)
        return _err(str(e))


def handle_meeting_get(args: dict) -> str:
    mid = args.get("meeting_id")
    if not mid:
        return _err("meeting_id is required")
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("""SELECT m.*, e.name AS event_name FROM meetings m
                           LEFT JOIN events e ON e.id = m.event_id WHERE m.id = %s""", (mid,))
            got = _rows(cur)
            if not got:
                return _err(f"no meeting with id {mid}")
            return _ok(got[0])
    except Exception as e:
        logger.debug("meeting_get failed: %s", e)
        return _err(str(e))
