"""
File-backed persistence for the notes store, fenced to ``mcp-server/data/``.

Why this exists
---------------
``server.py`` previously held notes in a module-level list that vanished when
the process exited. ADR-0001 (Consequences) states that persistence, when it is
added, must be an external store. This is that store.

The fence
---------
Every path this module opens is first run through :func:`resolve_within`, which
refuses anything resolving outside :data:`DATA_ROOT` (``mcp-server/data/``) by
raising ``ValueError`` that names the offending input. Today no client-supplied
path reaches this module -- the notes file name is hardcoded -- so the guard is
belt-and-braces on the real code path. Its real purpose is to be the single
reusable check that any future path-taking surface (``import_notes(path)``,
``attach_file(path)``, ...) must call. It is tested directly against traversal
payloads in ``test_notes_store.py``.

No ``print()`` anywhere in this module: on the stdio transport, stdout is the
MCP protocol stream (ADR-0001). Failures raise; the SDK surfaces them to the
client as errors rather than as a silent empty result.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fs_fence import resolve_within  # re-exported for callers importing it from here

# The narrowest root that still lets the job run: this server's own data
# directory. Located relative to THIS FILE, never the process working
# directory -- cwd varies with how the server is launched and is influenceable
# by whatever spawns it, so it is not a trustworthy base for a security check.
#
# MCP_NOTES_DATA_ROOT overrides it (config from env, 12-factor). Tests point it
# at a temp dir so they never touch the real store; a future move to a shared
# datastore (ADR-0001 migration outline) sets it too. Whatever it points at,
# resolve_within() still fences every access to that directory.
DATA_ROOT = Path(os.environ.get("MCP_NOTES_DATA_ROOT") or Path(__file__).resolve().parent.parent / "data")

# The only file this store ever reads or writes. Not a parameter, not derived
# from any input.
NOTES_FILENAME = "notes.json"


def _seed_notes() -> list[dict]:
    """The starting store, written once when no notes file exists yet."""
    return [
        {
            "id": str(uuid.uuid4()),
            "title": "Welcome",
            "content": "This is the first note in the demo store.",
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
    ]


# resolve_within now lives in fs_fence.py and is imported above so the notes
# store and the SQL adapter share one implementation. It stays importable from
# this module (`from notes_store import resolve_within`) for existing callers.


def notes_path(root: Path = DATA_ROOT) -> Path:
    """The absolute, fully-resolved path this store reads and writes.

    Exposed so server.py can route it through the roots containment check
    before add_note writes — even though the filename is hardcoded here, the
    roots gate has to see every path the server touches.
    """
    return resolve_within(root, NOTES_FILENAME)


def load_notes(root: Path = DATA_ROOT) -> list[dict]:
    """Return the persisted notes list, creating a seeded store on first run.

    A store that exists but cannot be read or parsed raises ``RuntimeError``
    rather than being treated as empty -- returning ``[]`` here would let the
    next :func:`save_notes` overwrite a file we simply failed to read.
    """
    path = resolve_within(root, NOTES_FILENAME)
    if not path.exists():
        notes = _seed_notes()
        _atomic_write(path, notes)
        return notes
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"notes store at {path} could not be read ({exc}); refusing to "
            f"continue with an empty store that would overwrite it"
        ) from exc
    if not isinstance(data, list):
        raise RuntimeError(
            f"notes store at {path} is not a JSON list (found {type(data).__name__})"
        )
    return data


def save_notes(notes: list[dict], root: Path = DATA_ROOT) -> None:
    """Persist ``notes`` to the fenced store. Idempotent: same list, same file."""
    path = resolve_within(root, NOTES_FILENAME)
    _atomic_write(path, notes)


def _atomic_write(path: Path, notes: list[dict]) -> None:
    """Write via a temp file in the same directory, then rename over the target.

    A crash mid-write leaves the previous good store intact rather than a
    truncated file. Concurrent server processes (not the deployed case -- see
    ADR-0001) still last-writer-wins; this guards corruption, not lost updates.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Unique per write (not just per process) so two writers can never scribble
    # on the same temp file. server.py serialises notes writes with a lock, but
    # this keeps _atomic_write correct on its own.
    tmp = path.with_name(f"{path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}")
    tmp.write_text(json.dumps(notes, indent=2), encoding="utf-8")
    os.replace(tmp, path)
