"""Run the same profile update three times and print the end state after each run.

    python idempotency-lab/demo.py

Part 1 is a naive update: append tags, always bump the version, always emit an
event. Its state changes on every run. Part 2 is update_profile(): its state is
identical after run 1, 2 and 3. Part 3 shows a late retry not undoing a newer change.
"""

from __future__ import annotations

import json
import sqlite3

from profile_store import connect, create_profile, get_profile, state_fingerprint, update_profile

REQUEST = {"email": "  Ada.Lovelace@Example.COM ", "add_tags": ["vip", "beta"]}


def naive_update(conn: sqlite3.Connection, user_id: str, changes: dict) -> None:
    """What NOT to do: deltas instead of desired state, with no dedup."""
    profile = get_profile(conn, user_id)
    conn.execute(
        "UPDATE profiles SET email=?, tags=?, version=version+1 WHERE user_id=?",
        (changes["email"].strip().lower(), json.dumps(profile["tags"] + changes["add_tags"]), user_id),
    )
    conn.execute(
        "INSERT INTO outbox (event_key, user_id, event_type, payload) VALUES (hex(randomblob(8)), ?, 'email_changed', '{}')",
        (user_id,),
    )


def show(conn: sqlite3.Connection, label: str) -> None:
    p = get_profile(conn, "u-1")
    events = conn.execute("SELECT COUNT(*) FROM outbox").fetchone()[0]
    print(f"  {label}: version={p['version']} tags={p['tags']} events={events} "
          f"fingerprint={state_fingerprint(conn)[:12]}")


def main() -> None:
    print("Part 1 - naive update, run 3 times:")
    conn = connect()
    create_profile(conn, "u-1", "Ada", "ada@old.example")
    for run in (1, 2, 3):
        naive_update(conn, "u-1", REQUEST)
        show(conn, f"run {run}")
    print("  -> a different state every run: duplicate tags, 3 versions, 3 'email changed' emails.\n")

    print("Part 2 - update_profile with one idempotency key, run 3 times:")
    conn = connect()
    create_profile(conn, "u-1", "Ada", "ada@old.example")
    for run in (1, 2, 3):
        result = update_profile(conn, "u-1", REQUEST, idempotency_key="req-7f3a")
        show(conn, f"run {run} (replayed={result.replayed})")
    print("  -> identical fingerprint after every run: one change, one version bump, one event.\n")

    print("Part 3 - a retry that arrives after a newer change:")
    update_profile(conn, "u-1", {"email": "ada@new.example"}, idempotency_key="req-8b21")
    show(conn, "after newer change")
    update_profile(conn, "u-1", REQUEST, idempotency_key="req-7f3a")  # the delayed retry of req-7f3a
    show(conn, "after late retry ")
    print(f"  -> email is still {get_profile(conn, 'u-1')['email']!r}: the stale retry was replayed, not re-applied.")


if __name__ == "__main__":
    main()
