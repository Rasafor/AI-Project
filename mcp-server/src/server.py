import json
import threading
import uuid
from datetime import datetime, timezone
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from pydantic import Field

import sql_adapter
from notes_store import load_notes, save_notes

# This name is what any connecting client (like the MCP Inspector) will show
# for this server.
mcp = MCPServer("ai-project-mcp-server")

# Notes are persisted to mcp-server/data/notes.json by notes_store, which
# fences every file access to that one directory (see notes_store.resolve_within
# and ADR-0001 Consequences). This list is the in-process working copy; each
# mutation is written straight back through save_notes.
#
# The SDK runs synchronous tool/resource functions on a thread pool, so two
# calls really can touch `notes` at the same time. `_notes_lock` serialises
# every read-modify-write of the pair (in-memory list + file) so a concurrent
# add_note cannot persist a stale snapshot and silently drop a note. See the
# README's "What this server assumes".
_notes_lock = threading.Lock()
notes: list[dict] = load_notes()


# --- TOOL: add_note ---------------------------------------------------------
# Tools are actions the MODEL decides to invoke. The type annotations below
# are the contract the model reads to know what arguments are valid — the
# SDK turns them into a JSON Schema automatically. Field(min_length=...)
# enforces that contract at the boundary, the same way a Zod schema does on
# the Node SDK: reject malformed input before it reaches business logic.
def _existing_note(title: str, content: str, idempotency_key: str | None) -> dict | None:
    """Return a note this call would duplicate, or None. Caller holds _notes_lock.

    With an idempotency_key: match that key (the key identifies the operation, so
    the stored note wins even if title/content now differ). Without one: match an
    exact title+content pair, so a plain retry does not create a second note.
    """
    for n in notes:
        if idempotency_key is not None:
            if n.get("idempotency_key") == idempotency_key:
                return n
        elif n["title"] == title and n["content"] == content:
            return n
    return None


@mcp.tool()
def add_note(
    title: Annotated[str, Field(min_length=1, max_length=200, description="Short title for the note")],
    content: Annotated[str, Field(min_length=1, max_length=5000, description="Body text of the note")],
    idempotency_key: Annotated[
        str | None,
        Field(
            default=None,
            max_length=200,
            description=(
                "Optional stable id for this add. Passing the same key again returns "
                "the note already stored under it instead of creating a duplicate — "
                "use it to make retries safe."
            ),
        ),
    ] = None,
) -> str:
    """Add a note to the store, or return the existing one if this add is a duplicate.

    A duplicate is: the same `idempotency_key` seen before, or (with no key) an
    identical title and content. Returns the note's id either way.
    """
    with _notes_lock:
        existing = _existing_note(title, content, idempotency_key)
        if existing is not None:
            return (
                f'Note "{existing["title"]}" already stored with id {existing["id"]} '
                f"(no duplicate created)."
            )
        note = {
            "id": str(uuid.uuid4()),
            "title": title,
            "content": content,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        if idempotency_key is not None:
            note["idempotency_key"] = idempotency_key
        # Persist first, then update memory. If save_notes raises, we return an
        # error without ever having reported the note as stored, and `notes`
        # still matches what is on disk. The lock keeps two concurrent calls
        # from interleaving their whole-file writes (or both passing the
        # duplicate check) and losing or double-adding a note.
        save_notes(notes + [note])
        notes.append(note)
    return f'Note "{title}" added with id {note["id"]}.'


# --- TOOL: run_sql_query --------------------------------------------------
# The adapter for the "SQL" system named in .colaberry/plan.json (REQ-008,
# STORY-003). The implementation lives in sql_adapter.py; this wrapper is just
# the MCP contract. Every argument is declared and bounded here (the SDK turns
# these annotations into JSON Schema), AND re-validated inside the adapter, so a
# direct caller gets the same guarantees. sql_adapter raises SqlAdapterError for
# any handled failure — the SDK surfaces it as is_error=True with the message,
# never a traceback.
@mcp.tool()
def run_sql_query(
    database: Annotated[
        str,
        Field(
            min_length=1,
            max_length=500,
            description=(
                "Path to a SQLite database file, relative to the SQL data root "
                "(env MCP_SQL_DATA_ROOT, default mcp-server/data/). Paths that "
                "resolve outside that directory are rejected."
            ),
        ),
    ],
    query: Annotated[
        str,
        Field(
            min_length=1,
            max_length=20_000,
            description=(
                "One read-only SQL statement (SELECT / WITH / EXPLAIN / PRAGMA). "
                "Write and DDL statements, multiple statements, and ATTACH are "
                "rejected."
            ),
        ),
    ],
    params: Annotated[
        list[str | int | float | bool | None] | None,
        Field(
            default=None,
            max_length=100,
            description=(
                "Optional positional values bound to '?' placeholders in the "
                "query. Use these instead of formatting values into the SQL."
            ),
        ),
    ] = None,
    timeout_seconds: Annotated[
        float,
        Field(default=5.0, gt=0, le=30, description="Abort the query if it runs longer than this."),
    ] = 5.0,
    max_rows: Annotated[
        int,
        Field(
            default=100,
            ge=1,
            le=1000,
            description="Max rows returned; extras are dropped and 'truncated' is set true.",
        ),
    ] = 100,
) -> str:
    """Run a read-only SQL query against a SQLite data source; return rows as JSON.

    Validates every argument, fences the database path, enforces the timeout,
    and returns a structured error (not a crash) when the database is missing,
    corrupt, locked, or the query is invalid.
    """
    try:
        result = sql_adapter.run_sql_query(
            database=database,
            query=query,
            params=params,
            timeout_seconds=timeout_seconds,
            max_rows=max_rows,
        )
    except sql_adapter.SqlAdapterError as exc:
        # A failure the adapter handled on purpose (bad input, path escape,
        # database unavailable, timeout, broken query). Re-raise as ToolError so
        # the SDK returns it to the caller as is_error=True with this message,
        # instead of logging it as an unexpected crash.
        raise ToolError(str(exc)) from exc
    return json.dumps(result, indent=2, default=str)


# --- RESOURCE: notes://all --------------------------------------------------
# Resources are DATA the host app can attach to context (e.g. a user picks
# it, or the app auto-attaches it). The model doesn't "call" this the way it
# calls a tool — it's exposed as addressable content behind a URI.
@mcp.resource(
    "notes://all",
    name="all-notes",
    description="JSON list of every note currently in the store",
    mime_type="application/json",
)
def get_all_notes() -> str:
    # Take the same lock as add_note so a read never sees the list mid-mutation
    # (returns a snapshot that is either wholly before or wholly after a write).
    with _notes_lock:
        return json.dumps(notes, indent=2)


# --- PROMPT: capture_note ---------------------------------------------------
# Prompts are USER-controlled workflow templates: they appear in the client
# UI (e.g. as a slash command) and are invoked explicitly by the person, not
# silently chosen by the model. This one packages the "correct" way to use
# add_note so the user doesn't have to know the tool's argument shape.
@mcp.prompt()
def capture_note(
    raw_text: Annotated[str, Field(min_length=1, description="Unstructured text to turn into a title + note body")],
) -> list[dict]:
    """Turn a raw block of text into a structured note and save it with add_note."""
    return [
        {
            "role": "user",
            "content": (
                "Read the text below. Derive a concise title (max 10 words) "
                "and a cleaned-up body (fix obvious typos, keep the meaning "
                "intact). Then call the add_note tool with that title and "
                f'content.\n\nText:\n"""\n{raw_text}\n"""'
            ),
        }
    ]


if __name__ == "__main__":
    # Transport is stdio: the client launches this file as a child process and
    # speaks JSON-RPC over its stdin/stdout. No network port, no listener, no
    # auth to manage — each person runs their own copy on their own machine.
    # This is a recorded, deliberate choice; see docs/ADR-0001-transport.md for
    # the rationale and the triggers that would justify switching to
    # streamable-http. Stated explicitly here rather than relying on the SDK's
    # default so the decision is visible at the point it takes effect.
    mcp.run(transport="stdio")
