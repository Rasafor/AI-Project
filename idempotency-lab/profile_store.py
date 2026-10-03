"""Idempotent user-profile update, backed by SQLite.

update_profile() can be run any number of times with the same idempotency key
and leaves the system in exactly the same state as running it once: the same
profile row, the same version number, one "email changed" event, one key record.

Four mechanisms make that true. Each one closes a different way a repeat run
could diverge:

1. Set semantics, not deltas. Every change says what a field should BE
   ("email = ada@example.com", "tags include vip"), never what to DO to it
   ("append a tag", "increment a counter"). Applying "be X" twice still gives X.
2. Normalize, then diff. Inputs are normalized ("  Ada@Example.COM " becomes
   "ada@example.com") and compared to what is stored. If nothing would change,
   nothing is written: no version bump, no updated_at change, no event.
3. Idempotency key. The first result for a key is stored. A repeat with the
   same key returns that stored result without re-running anything. This is
   what stops a late retry from undoing a newer change made in between. The
   same key with a different payload is rejected: it is a client bug, not a retry.
4. One transaction. The profile write, the outbox event and the key record
   commit together or not at all. A crash halfway leaves no trace, so the retry
   starts from a clean state.

Failure-first answers (CLAUDE.md "Failure-First Design"):
- On failure: any error rolls back the whole transaction and is re-raised.
  Validation errors are raised before the transaction starts.
- Retry: none inside this function. The caller retries with the SAME key, and
  that retry is safe because of (3) and (4).
- Recovery: none needed. A rolled-back run left nothing behind.
- Not handled: key expiry (keys are kept forever here; production systems
  usually expire them after 24h-7d) and authorization (who may edit whom).
"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

SCHEMA = """
CREATE TABLE IF NOT EXISTS profiles (
    user_id      TEXT PRIMARY KEY,
    display_name TEXT NOT NULL,
    email        TEXT NOT NULL,
    timezone     TEXT NOT NULL,
    tags         TEXT NOT NULL,          -- JSON array, kept sorted
    version      INTEGER NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS idempotency_keys (
    idempotency_key TEXT PRIMARY KEY,
    request_hash    TEXT NOT NULL,
    response        TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS outbox (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    event_key  TEXT NOT NULL UNIQUE,     -- second line of defence against duplicate events
    user_id    TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload    TEXT NOT NULL
);
"""

ALLOWED_FIELDS = {"display_name", "email", "timezone", "add_tags", "remove_tags"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MAX_NAME_LENGTH = 100
MAX_TAGS = 20


class ProfileValidationError(ValueError):
    """The requested change is malformed. Nothing was written."""


class ProfileNotFoundError(LookupError):
    """No profile exists for this user_id. Nothing was written."""


class IdempotencyKeyConflictError(Exception):
    """This key was already used for a DIFFERENT request. Nothing was written."""


@dataclass(frozen=True)
class UpdateResult:
    profile: dict
    changed_fields: list[str]
    replayed: bool  # True when this result came from the key store, not from running the update


def connect(path: str = ":memory:") -> sqlite3.Connection:
    """Open a store with the schema in place. isolation_level=None lets us issue
    BEGIN IMMEDIATE ourselves, so concurrent writers queue instead of interleaving."""
    conn = sqlite3.connect(path, isolation_level=None, timeout=5.0)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def create_profile(conn: sqlite3.Connection, user_id: str, display_name: str, email: str, tz: str = "UTC") -> None:
    """Seed a profile. INSERT OR IGNORE makes re-seeding a no-op, not an error or a duplicate."""
    conn.execute(
        "INSERT OR IGNORE INTO profiles VALUES (?, ?, ?, ?, '[]', 1, ?)",
        (user_id, display_name.strip(), _normalize_email(email), tz, _utc_now()),
    )


def get_profile(conn: sqlite3.Connection, user_id: str) -> dict:
    row = conn.execute("SELECT * FROM profiles WHERE user_id = ?", (user_id,)).fetchone()
    if row is None:
        raise ProfileNotFoundError(f"no profile for user '{user_id}'")
    return {**dict(row), "tags": json.loads(row["tags"])}


def update_profile(
    conn: sqlite3.Connection,
    user_id: str,
    changes: dict,
    *,
    idempotency_key: str,
    now: Callable[[], str] | None = None,
    before_commit: Callable[[], None] | None = None,
) -> UpdateResult:
    """Apply `changes` to one profile, exactly once per idempotency_key.

    `changes` may hold display_name, email, timezone (set to this value) and
    add_tags / remove_tags (ensure present / ensure absent). `before_commit` is
    a test hook for simulating a crash after the writes but before COMMIT.
    """
    if not idempotency_key or not idempotency_key.strip():
        raise ProfileValidationError("idempotency_key is required")
    normalized = _validate_and_normalize(changes)
    request_hash = _hash({"user_id": user_id, "changes": normalized})
    now = now or _utc_now

    conn.execute("BEGIN IMMEDIATE")
    try:
        result = _apply_once(conn, user_id, normalized, idempotency_key, request_hash, now)
        if before_commit is not None and not result.replayed:
            before_commit()
        conn.execute("COMMIT")
        return result
    except BaseException:
        conn.execute("ROLLBACK")
        raise


def _apply_once(conn, user_id, changes, idempotency_key, request_hash, now) -> UpdateResult:
    seen = conn.execute(
        "SELECT request_hash, response FROM idempotency_keys WHERE idempotency_key = ?", (idempotency_key,)
    ).fetchone()
    if seen is not None:
        if seen["request_hash"] != request_hash:
            raise IdempotencyKeyConflictError(f"key '{idempotency_key}' was already used for a different request")
        stored = json.loads(seen["response"])
        return UpdateResult(profile=stored["profile"], changed_fields=stored["changed_fields"], replayed=True)

    current = get_profile(conn, user_id)
    desired = _desired_state(current, changes)
    changed = sorted(field for field in desired if desired[field] != current[field])

    if changed:
        updated = {**current, **desired, "version": current["version"] + 1, "updated_at": now()}
        conn.execute(
            "UPDATE profiles SET display_name=?, email=?, timezone=?, tags=?, version=?, updated_at=? WHERE user_id=?",
            (updated["display_name"], updated["email"], updated["timezone"], json.dumps(updated["tags"]),
             updated["version"], updated["updated_at"], user_id),
        )
        if "email" in changed:
            conn.execute(
                "INSERT INTO outbox (event_key, user_id, event_type, payload) VALUES (?, ?, 'email_changed', ?)"
                " ON CONFLICT(event_key) DO NOTHING",
                (f"{idempotency_key}:email_changed", user_id,
                 json.dumps({"old": current["email"], "new": updated["email"]})),
            )
    else:
        updated = current  # nothing to change: write nothing, bump nothing, emit nothing

    conn.execute(
        "INSERT INTO idempotency_keys VALUES (?, ?, ?)",
        (idempotency_key, request_hash, json.dumps({"profile": updated, "changed_fields": changed})),
    )
    return UpdateResult(profile=updated, changed_fields=changed, replayed=False)


def _desired_state(current: dict, changes: dict) -> dict:
    desired = {key: changes[key] for key in ("display_name", "email", "timezone") if key in changes}
    if "add_tags" in changes or "remove_tags" in changes:
        tags = (set(current["tags"]) | set(changes.get("add_tags", []))) - set(changes.get("remove_tags", []))
        if len(tags) > MAX_TAGS:
            raise ProfileValidationError(f"a profile may have at most {MAX_TAGS} tags")
        desired["tags"] = sorted(tags)
    return desired


def _validate_and_normalize(changes: dict) -> dict:
    if not isinstance(changes, dict) or not changes:
        raise ProfileValidationError("changes must be a non-empty object")
    unknown = set(changes) - ALLOWED_FIELDS
    if unknown:
        raise ProfileValidationError(f"unknown field(s): {', '.join(sorted(unknown))}")

    out: dict = {}
    if "display_name" in changes:
        name = _require_str(changes, "display_name").strip()
        if not name or len(name) > MAX_NAME_LENGTH:
            raise ProfileValidationError(f"display_name must be 1-{MAX_NAME_LENGTH} characters")
        out["display_name"] = name
    if "email" in changes:
        out["email"] = _normalize_email(_require_str(changes, "email"))
    if "timezone" in changes:
        out["timezone"] = _require_str(changes, "timezone").strip()
    for key in ("add_tags", "remove_tags"):
        if key in changes:
            tags = changes[key]
            if not isinstance(tags, list) or not all(isinstance(t, str) and t.strip() for t in tags):
                raise ProfileValidationError(f"{key} must be a list of non-empty strings")
            out[key] = sorted({t.strip().lower() for t in tags})  # sorted set: order and repeats don't matter
    if set(out.get("add_tags", [])) & set(out.get("remove_tags", [])):
        raise ProfileValidationError("a tag cannot be both added and removed in one request")
    return out


def _require_str(changes: dict, key: str) -> str:
    if not isinstance(changes[key], str):
        raise ProfileValidationError(f"{key} must be a string")
    return changes[key]


def _normalize_email(email: str) -> str:
    email = email.strip().lower()
    if not EMAIL_RE.match(email):
        raise ProfileValidationError(f"'{email}' is not a valid email address")
    return email


def _hash(payload: dict) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def state_fingerprint(conn: sqlite3.Connection) -> str:
    """SHA-256 over every row of every table: equal fingerprints mean identical end states."""
    tables = {
        "profiles": "SELECT * FROM profiles ORDER BY user_id",
        "idempotency_keys": "SELECT * FROM idempotency_keys ORDER BY idempotency_key",
        "outbox": "SELECT * FROM outbox ORDER BY id",
    }
    return _hash({name: [list(row) for row in conn.execute(sql)] for name, sql in tables.items()})
