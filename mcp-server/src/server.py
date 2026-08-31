import json
import uuid
from datetime import datetime, timezone
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

# This name is what any connecting client (like the MCP Inspector) will show
# for this server.
mcp = MCPServer("ai-project-mcp-server")

# In-memory store. A real server would back this with a file or DB — state
# must survive process restarts if the client expects persistence.
notes: list[dict] = [
    {
        "id": str(uuid.uuid4()),
        "title": "Welcome",
        "content": "This is the first note in the demo store.",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
]


# --- TOOL: add_note ---------------------------------------------------------
# Tools are actions the MODEL decides to invoke. The type annotations below
# are the contract the model reads to know what arguments are valid — the
# SDK turns them into a JSON Schema automatically. Field(min_length=...)
# enforces that contract at the boundary, the same way a Zod schema does on
# the Node SDK: reject malformed input before it reaches business logic.
@mcp.tool()
def add_note(
    title: Annotated[str, Field(min_length=1, max_length=200, description="Short title for the note")],
    content: Annotated[str, Field(min_length=1, max_length=5000, description="Body text of the note")],
) -> str:
    """Add a new note to the notes store. Returns the created note's id."""
    note = {
        "id": str(uuid.uuid4()),
        "title": title,
        "content": content,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    notes.append(note)
    return f'Note "{title}" added with id {note["id"]}.'


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
    mcp.run()
