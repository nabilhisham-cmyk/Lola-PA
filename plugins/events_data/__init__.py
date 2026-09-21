"""Events data layer for Lola — El Gouna events in Supabase Postgres.

The Supabase memory plugin (``plugins/memory/supabase/``) exposes only memory
tools (search/remember/forget/...). It has no path to the events tables, so
without this plugin Lola would have to hand-write raw SQL through ``terminal``
for every single question about an event: slow, unchecked, and easy to get
silently wrong.

This plugin registers a small, *validated* tool surface over the events tables
instead. It deliberately does not expose arbitrary SQL: every tool takes
structured arguments, the column set is fixed, and writes are limited to the
event domain. That keeps the agent's blast radius inside the events schema.

Tools (toolset ``events``):
  events_list        query events in a date window
  events_upcoming    the next N events
  events_get         one event with its contacts and tasks
  events_create      create an event
  events_update      update fields on an event
  events_clashes     venue clashes, including build/get-out overlap
  events_at_risk     events near, with open critical work or missing permits
  venues_list        venues, optionally by zone
  venues_save        create or update a venue
  suppliers_list     suppliers, optionally by category
  suppliers_save     create or update a supplier
  tasks_list         tasks for an event, or all open tasks
  tasks_save         create or update a task

Connection uses the standard Supabase pooler/direct DSN from
``SUPABASE_DB_URL``, or is assembled from ``SUPABASE_MEMORY_URL`` +
``SUPABASE_DB_PASSWORD`` when only those are present. Never reads
``DATABASE_URL`` — on this host that variable pointed at an unrelated client's
database, so trusting it is how you write into the wrong system.
"""

from __future__ import annotations

from plugins.events_data import tools as _t

_TOOLS = (
    ("events_list",      _t.EVENTS_LIST_SCHEMA,      _t.handle_events_list,      "📅"),
    ("events_upcoming",  _t.EVENTS_UPCOMING_SCHEMA,  _t.handle_events_upcoming,  "⏭️"),
    ("events_get",       _t.EVENTS_GET_SCHEMA,       _t.handle_events_get,       "🔎"),
    ("events_create",    _t.EVENTS_CREATE_SCHEMA,    _t.handle_events_create,    "➕"),
    ("events_update",    _t.EVENTS_UPDATE_SCHEMA,    _t.handle_events_update,    "✏️"),
    ("events_clashes",   _t.EVENTS_CLASHES_SCHEMA,   _t.handle_events_clashes,   "⚠️"),
    ("events_at_risk",   _t.EVENTS_AT_RISK_SCHEMA,   _t.handle_events_at_risk,   "🚨"),
    ("venues_list",      _t.VENUES_LIST_SCHEMA,      _t.handle_venues_list,      "📍"),
    ("venues_save",      _t.VENUES_SAVE_SCHEMA,      _t.handle_venues_save,      "🏛️"),
    ("suppliers_list",   _t.SUPPLIERS_LIST_SCHEMA,   _t.handle_suppliers_list,   "🚚"),
    ("suppliers_save",   _t.SUPPLIERS_SAVE_SCHEMA,   _t.handle_suppliers_save,   "📦"),
    ("tasks_list",       _t.TASKS_LIST_SCHEMA,       _t.handle_tasks_list,       "✅"),
    ("tasks_save",       _t.TASKS_SAVE_SCHEMA,       _t.handle_tasks_save,       "📝"),
)


def register(ctx) -> None:
    """Register the events toolset. Called once by the plugin loader."""
    for name, schema, handler, emoji in _TOOLS:
        ctx.register_tool(
            name=name,
            toolset="events",
            schema=schema,
            handler=handler,
            check_fn=_t.check_events_available,
            emoji=emoji,
        )
