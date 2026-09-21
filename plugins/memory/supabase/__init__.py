"""Supabase memory plugin — MemoryProvider interface.

Persona-scoped persistent memory with hybrid (keyword + vector) recall, backed by
a Supabase Postgres project. Embeddings are generated locally with fastembed
(nomic-embed-text-v1.5, 768 dims) — no embedding API needed.

Config via environment variables (.env):
  SUPABASE_MEMORY_URL   — https://<ref>.supabase.co   (required)
  SUPABASE_MEMORY_KEY   — service_role / sb_secret key (required)
  EMBED_MODEL           — informational (default: nomic-embed-text)

Requires the schema in scripts/supabase_migration.sql (memories + interactions
tables, search_memories + hybrid_search_memories functions).

Tools exposed:
  supabase_search        Hybrid keyword+vector search, persona-scoped
  supabase_remember      Store a fact/preference/decision/project
  supabase_forget        Delete a memory by id
  supabase_entities      List memories mentioning an entity
  supabase_interactions  Recent interaction history
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import threading
from typing import Any, Dict, List, Optional

from agent.memory_provider import MemoryProvider
from tools.registry import tool_error

logger = logging.getLogger(__name__)

_EMBED_DIM = 768
_EMBED_MODEL = "nomic-ai/nomic-embed-text-v1.5"

# Module-level embedder singleton — model load is slow, share across instances.
_embedder = None
_embedder_lock = threading.Lock()


def _get_embedder():
    global _embedder
    if _embedder is not None:
        return _embedder
    with _embedder_lock:
        if _embedder is None:
            from fastembed import TextEmbedding
            _embedder = TextEmbedding(model_name=_EMBED_MODEL)
    return _embedder


def _embed(text: str) -> List[float]:
    vecs = list(_get_embedder().embed([text]))
    return [float(x) for x in vecs[0]]


def _vec_literal(vec: List[float]) -> str:
    """pgvector text literal: '[0.1,0.2,...]'."""
    return "[" + ",".join(repr(float(x)) for x in vec) + "]"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    return {
        "url": (os.environ.get("SUPABASE_MEMORY_URL", "") or "").rstrip("/"),
        "key": os.environ.get("SUPABASE_MEMORY_KEY", ""),
    }


# ---------------------------------------------------------------------------
# Tool schemas (§12)
# ---------------------------------------------------------------------------

SEARCH_SCHEMA = {
    "name": "supabase_search",
    "description": (
        "Search long-term memory by meaning (hybrid keyword + vector). Returns "
        "relevant stored facts, preferences, decisions, and project notes, scoped "
        "to the active persona. Use when you need to recall something the user told "
        "you in a past session."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "What to recall."},
            "top_k": {"type": "integer", "description": "Max results (default 8, max 25)."},
        },
        "required": ["query"],
    },
}

REMEMBER_SCHEMA = {
    "name": "supabase_remember",
    "description": (
        "Store a durable fact about the user/business in long-term memory. Use for "
        "explicit preferences, decisions, project facts, or people worth remembering "
        "across sessions. Stored verbatim under the active persona."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "The fact to store."},
            "category": {
                "type": "string",
                "description": "fact | preference | decision | project | person | conversation",
            },
            "entities": {
                "type": "array", "items": {"type": "string"},
                "description": "Named entities mentioned (people, companies, projects).",
            },
            "importance": {
                "type": "number",
                "description": "0.0–1.0 importance (default 0.5).",
            },
        },
        "required": ["content"],
    },
}

FORGET_SCHEMA = {
    "name": "supabase_forget",
    "description": "Delete a memory by its id (destructive — confirm first).",
    "parameters": {
        "type": "object",
        "properties": {"id": {"type": "string", "description": "Memory UUID to delete."}},
        "required": ["id"],
    },
}

ENTITIES_SCHEMA = {
    "name": "supabase_entities",
    "description": "List stored memories that mention a given entity (person, company, project).",
    "parameters": {
        "type": "object",
        "properties": {
            "entity": {"type": "string", "description": "Entity name to look up."},
            "top_k": {"type": "integer", "description": "Max results (default 10)."},
        },
        "required": ["entity"],
    },
}

INTERACTIONS_SCHEMA = {
    "name": "supabase_interactions",
    "description": "Show recent interaction history for the active persona (pattern analysis).",
    "parameters": {
        "type": "object",
        "properties": {
            "top_k": {"type": "integer", "description": "How many recent turns (default 10)."},
        },
        "required": [],
    },
}

ADD_RULE_SCHEMA = {
    "name": "supabase_add_rule",
    "description": (
        "Save a standing RULE/instruction for how you should behave for this user "
        "(e.g. 'always use UK English', 'never deploy on Fridays', 'prefer pnpm'). "
        "Rules are high-priority and are injected into every future session for this "
        "persona. Use when the user corrects you or states a durable preference."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "rule": {"type": "string", "description": "The standing rule/instruction."},
        },
        "required": ["rule"],
    },
}


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------

class SupabaseMemoryProvider(MemoryProvider):
    """Persona-scoped Supabase memory with hybrid recall + local embeddings."""

    def __init__(self):
        self._url = ""
        self._key = ""
        self._persona = "shared"
        self._read_all = True
        self._session_id = ""
        self._rules = []
        self._extract_model = ""
        self._ollama_base = ""
        self._ollama_key = ""
        self._prefetch_result = ""
        self._prefetch_lock = threading.Lock()
        self._prefetch_thread = None
        self._sync_thread = None

    @property
    def name(self) -> str:
        return "supabase"

    def is_available(self) -> bool:
        cfg = _load_config()
        if not (cfg["url"] and cfg["key"]):
            return False
        try:
            import fastembed  # noqa: F401
            import requests  # noqa: F401
        except ImportError:
            return False
        return True

    def get_config_schema(self):
        return [
            {"key": "url", "description": "Supabase project URL", "secret": False,
             "required": True, "env_var": "SUPABASE_MEMORY_URL",
             "url": "https://supabase.com/dashboard"},
            {"key": "key", "description": "Supabase service_role / sb_secret key",
             "secret": True, "required": True, "env_var": "SUPABASE_MEMORY_KEY"},
        ]

    def initialize(self, session_id: str, **kwargs) -> None:
        cfg = _load_config()
        self._url = cfg["url"]
        self._key = cfg["key"]
        self._session_id = session_id
        raw = (kwargs.get("agent_identity") or "").strip().lower()
        if raw in ("", "default", "concierge"):
            self._persona = "shared" if raw in ("", "default") else "concierge"
            self._read_all = True
        else:
            self._persona = raw
            self._read_all = False
        # Adaptive-learning config (session-end extraction uses an Ollama model).
        self._ollama_base = (os.environ.get("OLLAMA_BASE_URL", "") or "https://ollama.com/v1").rstrip("/")
        self._ollama_key = os.environ.get("OLLAMA_API_KEY", "")
        self._extract_model = os.environ.get("EXTRACT_MODEL", "gpt-oss:20b")
        # Load standing rules for this persona into the system prompt.
        try:
            self._refresh_rules()
        except Exception as e:
            logger.debug("supabase rule load failed: %s", e)
        # Warm the embedder in the background so the first turn isn't slow.
        threading.Thread(target=_get_embedder, daemon=True, name="supa-embed-warm").start()

    def _refresh_rules(self) -> None:
        """Fetch standing rules (category='rule') for this persona + shared scope."""
        path = ("memories?category=eq.rule&select=content,persona"
                "&order=importance.desc,created_at.desc&limit=50")
        if not self._read_all:
            # persona's own rules plus shared rules
            path += f"&or=(persona.eq.{self._persona},persona.eq.shared)"
        r = self._rest("GET", path)
        if r.status_code < 300:
            self._rules = [row.get("content", "") for row in (r.json() or []) if row.get("content")]

    # -- REST helpers -------------------------------------------------------

    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }
        if extra:
            h.update(extra)
        return h

    def _rest(self, method: str, path: str, **kw):
        import requests
        url = f"{self._url}/rest/v1/{path}"
        return requests.request(method, url, headers=self._headers(kw.pop("headers", None)),
                                timeout=20, **kw)

    def _persona_filter(self) -> Optional[str]:
        return None if self._read_all else self._persona

    # -- Lifecycle ----------------------------------------------------------

    def system_prompt_block(self) -> str:
        scope = "all personas" if self._read_all else f"persona '{self._persona}'"
        block = (
            "# Supabase Memory\n"
            f"Active. Long-term recall scoped to {scope}.\n"
            "Use supabase_search to recall past facts; supabase_remember to store "
            "durable facts/preferences/decisions; supabase_add_rule when the user "
            "states a standing preference or corrects you. Deleting memory needs confirmation."
        )
        if self._rules:
            block += "\n\n## Standing rules (learned from this user — follow them)\n"
            block += "\n".join(f"- {r}" for r in self._rules)
        return block

    def _hybrid_search(self, query: str, limit: int) -> list:
        emb = _embed(query)
        body = {
            "search_query": query,
            "query_embedding": _vec_literal(emb),
            "result_limit": limit,
            "persona_filter": self._persona_filter(),
            "semantic_weight": 0.6,
        }
        r = self._rest("POST", "rpc/hybrid_search_memories", json=body)
        if r.status_code >= 300:
            raise RuntimeError(f"search HTTP {r.status_code}: {r.text[:200]}")
        return r.json() or []

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        if self._prefetch_thread and self._prefetch_thread.is_alive():
            self._prefetch_thread.join(timeout=3.0)
        with self._prefetch_lock:
            result = self._prefetch_result
            self._prefetch_result = ""
        return f"## Recalled from memory\n{result}" if result else ""

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        if not query:
            return

        def _run():
            try:
                rows = self._hybrid_search(query, 5)
                lines = [f"- {row.get('content','')}" for row in rows if row.get("content")]
                if lines:
                    with self._prefetch_lock:
                        self._prefetch_result = "\n".join(lines)
            except Exception as e:
                logger.debug("supabase prefetch failed: %s", e)

        self._prefetch_thread = threading.Thread(target=_run, daemon=True, name="supa-prefetch")
        self._prefetch_thread.start()

    def sync_turn(self, user_content: str, assistant_content: str, *,
                  session_id: str = "", messages=None) -> None:
        def _sync():
            try:
                self._rest("POST", "interactions", json={
                    "persona": self._persona,
                    "user_content": user_content[:8000],
                    "assistant_content": assistant_content[:8000],
                    "session_id": session_id or self._session_id,
                })
            except Exception as e:
                logger.debug("supabase sync_turn failed: %s", e)

        if self._sync_thread and self._sync_thread.is_alive():
            self._sync_thread.join(timeout=5.0)
        self._sync_thread = threading.Thread(target=_sync, daemon=True, name="supa-sync")
        self._sync_thread.start()

    # -- Tools --------------------------------------------------------------

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return [SEARCH_SCHEMA, REMEMBER_SCHEMA, FORGET_SCHEMA,
                ENTITIES_SCHEMA, INTERACTIONS_SCHEMA, ADD_RULE_SCHEMA]

    def _exists_hash(self, chash: str) -> bool:
        try:
            r = self._rest("GET", f"memories?content_hash=eq.{chash}&select=id&limit=1")
            return r.status_code < 300 and bool(r.json())
        except Exception:
            return False

    def _store(self, content: str, category: str, entities: list, importance: float) -> dict:
        chash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        if self._exists_hash(chash):
            return {"deduped": True}
        emb = _embed(content)
        row = {
            "content": content,
            "category": category or "fact",
            "entities": entities or [],
            "importance": importance,
            "persona": self._persona,
            "content_hash": chash,
            "embedding": _vec_literal(emb),
        }
        r = self._rest("POST", "memories", json=row,
                       headers={"Prefer": "return=representation"})
        if r.status_code >= 300:
            raise RuntimeError(f"store HTTP {r.status_code}: {r.text[:200]}")
        data = r.json()
        return data[0] if isinstance(data, list) and data else {}

    def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str:
        try:
            if tool_name == "supabase_search":
                query = args.get("query", "")
                if not query:
                    return tool_error("Missing required parameter: query")
                top_k = min(int(args.get("top_k", 8)), 25)
                rows = self._hybrid_search(query, top_k)
                if not rows:
                    return json.dumps({"result": "No relevant memories found."})
                items = [{"id": r.get("id"), "content": r.get("content"),
                          "category": r.get("category"), "score": round(r.get("score", 0), 3)}
                         for r in rows]
                return json.dumps({"results": items, "count": len(items)})

            if tool_name == "supabase_remember":
                content = args.get("content", "")
                if not content:
                    return tool_error("Missing required parameter: content")
                rec = self._store(
                    content,
                    args.get("category", "fact"),
                    args.get("entities", []),
                    float(args.get("importance", 0.5)),
                )
                return json.dumps({"result": "Stored.", "id": rec.get("id"),
                                   "persona": self._persona})

            if tool_name == "supabase_add_rule":
                rule = args.get("rule", "")
                if not rule:
                    return tool_error("Missing required parameter: rule")
                rec = self._store(rule, "rule", [], 1.0)
                self._refresh_rules()
                return json.dumps({"result": "Rule saved and now active.",
                                   "id": rec.get("id"), "persona": self._persona})

            if tool_name == "supabase_forget":
                mid = args.get("id", "")
                if not mid:
                    return tool_error("Missing required parameter: id")
                r = self._rest("DELETE", f"memories?id=eq.{mid}")
                if r.status_code >= 300:
                    return tool_error(f"delete HTTP {r.status_code}: {r.text[:200]}")
                return json.dumps({"result": "Deleted.", "id": mid})

            if tool_name == "supabase_entities":
                entity = args.get("entity", "")
                if not entity:
                    return tool_error("Missing required parameter: entity")
                top_k = min(int(args.get("top_k", 10)), 50)
                # ILIKE on content (trigram-indexed); persona-scoped.
                path = (f"memories?content=ilike.*{entity}*"
                        f"&select=id,content,category,entities,created_at"
                        f"&order=importance.desc&limit={top_k}")
                if not self._read_all:
                    path += f"&persona=eq.{self._persona}"
                r = self._rest("GET", path)
                if r.status_code >= 300:
                    return tool_error(f"entities HTTP {r.status_code}: {r.text[:200]}")
                rows = r.json() or []
                return json.dumps({"results": rows, "count": len(rows)})

            if tool_name == "supabase_interactions":
                top_k = min(int(args.get("top_k", 10)), 50)
                path = (f"interactions?select=user_content,assistant_content,created_at"
                        f"&order=created_at.desc&limit={top_k}")
                if not self._read_all:
                    path += f"&persona=eq.{self._persona}"
                r = self._rest("GET", path)
                if r.status_code >= 300:
                    return tool_error(f"interactions HTTP {r.status_code}: {r.text[:200]}")
                rows = r.json() or []
                return json.dumps({"results": rows, "count": len(rows)})

            return tool_error(f"Unknown tool: {tool_name}")
        except Exception as e:
            return tool_error(str(e))

    # -- Adaptive learning: end-of-session extraction ----------------------

    _EXTRACT_SYS = (
        "You extract durable, reusable facts from a conversation for an assistant's "
        "long-term memory. Return ONLY a JSON array (no prose). Each item: "
        '{"content": str, "category": one of '
        '"fact"|"preference"|"decision"|"project"|"person", "importance": 0.0-1.0}. '
        "Include only things worth remembering across future sessions: stable user "
        "preferences, decisions made, project facts, people. EXCLUDE: chit-chat, "
        "transient task details, anything already obvious, and secrets/credentials. "
        "If nothing is worth saving, return []."
    )

    def _llm_extract(self, transcript: str) -> list:
        if not self._ollama_key:
            return []
        import requests
        body = {
            "model": self._extract_model,
            "messages": [
                {"role": "system", "content": self._EXTRACT_SYS},
                {"role": "user", "content": transcript[:24000]},
            ],
            "temperature": 0,
        }
        r = requests.post(
            f"{self._ollama_base}/chat/completions",
            headers={"Authorization": f"Bearer {self._ollama_key}",
                     "Content-Type": "application/json"},
            json=body, timeout=60,
        )
        if r.status_code >= 300:
            raise RuntimeError(f"extract HTTP {r.status_code}: {r.text[:200]}")
        text = r.json()["choices"][0]["message"]["content"].strip()
        # tolerate code fences / stray prose around the JSON array
        if "```" in text:
            text = text.split("```")[1].lstrip("json").strip()
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end == -1:
            return []
        try:
            items = json.loads(text[start:end + 1])
        except Exception:
            return []
        return items if isinstance(items, list) else []

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Distill the session into durable memories (handoff §12)."""
        try:
            turns = []
            for m in messages or []:
                role = m.get("role")
                content = m.get("content")
                if role in ("user", "assistant") and isinstance(content, str) and content.strip():
                    turns.append(f"{role.upper()}: {content.strip()}")
            if len(turns) < 2:
                return
            transcript = "\n".join(turns)
            items = self._llm_extract(transcript)
            stored = 0
            for it in items:
                content = (it.get("content") or "").strip()
                if not content:
                    continue
                cat = it.get("category", "fact")
                imp = float(it.get("importance", 0.5))
                rec = self._store(content, cat, [], imp)
                if not rec.get("deduped"):
                    stored += 1
            if stored:
                logger.info("supabase: extracted %d memories at session end", stored)
        except Exception as e:
            logger.debug("supabase session-end extraction failed: %s", e)

    def shutdown(self) -> None:
        for t in (self._prefetch_thread, self._sync_thread):
            if t and t.is_alive():
                t.join(timeout=5.0)


def register(ctx) -> None:
    ctx.register_memory_provider(SupabaseMemoryProvider())
