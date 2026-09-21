"""Meeting transcripts for Lola — long recordings into structured minutes.

WHY THIS IS A PLUGIN AND NOT JUST A VOICE NOTE
Telegram voice notes are already transcribed for free by the gateway before the
agent ever sees them. That covers a quick "note to self". It does NOT cover a
site meeting, a supplier negotiation or a walkthrough, because:

  - those run 30 to 120 minutes, well past a voice note, so the audio usually
    arrives as a FILE (an .m4a/.mp3/.ogg the phone recorded, forwarded in)
  - they have several speakers, and an unattributed wall of text is not minutes
  - the output that has value is not the transcript, it is the decisions, the
    action items and the open questions, plus who owns each one

So this plugin does three things: transcribe a long file with the real
transcriber, ask the model to structure it, and persist the result against an
event so it can be searched later.

WHAT IT DELIBERATELY DOES NOT DO
Speaker diarisation. faster-whisper does not do it locally, and inventing
"Speaker 1 / Speaker 2" labels that do not correspond to real people would be
worse than no labels at all: Hisham would act on minutes that attribute a
decision to the wrong person. The transcript is kept in order and the structuring
step is told to attribute only when the text itself makes the speaker clear, and
otherwise to say so.

Tools (toolset ``meetings``):
  meeting_transcribe   transcribe an audio file into a stored transcript
  meeting_minutes      structure a transcript into decisions, actions, questions
  meeting_list         stored meetings, optionally for one event
  meeting_get          one meeting in full, transcript and minutes
"""

from __future__ import annotations

from plugins.meetings import tools as _t

_TOOLS = (
    ("meeting_transcribe", _t.MEETING_TRANSCRIBE_SCHEMA, _t.handle_meeting_transcribe, "🎙️"),
    ("meeting_minutes",    _t.MEETING_MINUTES_SCHEMA,    _t.handle_meeting_minutes,    "🗒️"),
    ("meeting_list",       _t.MEETING_LIST_SCHEMA,       _t.handle_meeting_list,       "📚"),
    ("meeting_get",        _t.MEETING_GET_SCHEMA,        _t.handle_meeting_get,        "🔎"),
)


def register(ctx) -> None:
    """Register the meetings toolset. Called once by the plugin loader."""
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="meetings",
            schema=schema,
            handler=handler,
            check_fn=_t.check_meetings_available,
            emoji=emoji,
        )
