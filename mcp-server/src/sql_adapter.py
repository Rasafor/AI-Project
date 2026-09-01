"""
SQL query adapter — the project's integration with the "SQL" data source named
in .colaberry/plan.json.

Plan references: REQ-008 ("connect to data sources for log and SQL analysis",
must), REQ-003 / STORY-003 ("analyze SQL queries to identify potential issues",
r1). `derived.systems` lists exactly one system: "SQL".

Backend: SQLite via the standard-library `sqlite3` module — no extra
dependencies. The "system" is a database file reachable by path, fenced to
SQL_DATA_ROOT. The tool contract (declared inputs, up-front validation, an
explicit timeout, a structured error instead of a crash) is identical for a
networked warehouse; swapping SQLite for psycopg/pyodbc later is a change inside
this module, not a change to the tool.

Safety posture:
  - Read-only: the connection is opened `mode=ro`, an authorizer denies
    ATTACH/DETACH (so a query cannot reach a file outside the fence), and
    obvious write/DDL verbs are rejected up front with a friendly message.
  - Fenced: the database path must resolve inside SQL_DATA_ROOT (shared guard
    in fs_fence.py).
  - Parameterised: `params` are bound by the driver, never formatted into SQL.
  - Bounded: an explicit per-call timeout aborts a slow query via a watchdog
    thread; `max_rows` caps the result size.

No print(): stdout is the MCP protocol stream (ADR-0001). Failures raise
SqlAdapterError; server.py lets that surface as an MCP tool error
(is_error=True) — a useful message, never an unhandled traceback.
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
import time
from pathlib import Path

from fs_fence import resolve_within

# Narrowest root that still does the job: this server's data directory, resolved
# from THIS FILE (never process cwd). Override with MCP_SQL_DATA_ROOT.
SQL_DATA_ROOT = Path(
    os.environ.get("MCP_SQL_DATA_ROOT") or Path(__file__).resolve().parent.parent / "data"
)

DEFAULT_TIMEOUT_SECONDS = 5.0
MAX_TIMEOUT_SECONDS = 30.0
DEFAULT_MAX_ROWS = 100
MAX_MAX_ROWS = 1000
MAX_QUERY_CHARS = 20_000
MAX_PARAMS = 100

# Leading keywords that can never be read-only. The `mode=ro` connection is the
# real enforcement; this set just produces a clearer message for the common case
# than "attempt to write a readonly database".
_WRITE_VERBS = frozenset(
    {
        "insert", "update", "delete", "replace", "upsert",
        "drop", "create", "alter", "truncate", "rename",
        "attach", "detach", "vacuum", "reindex", "analyze",
        "begin", "commit", "end", "rollback", "savepoint",
        "grant", "revoke",
    }
)

_ALLOWED_PARAM_TYPES = (str, int, float, bool)


class SqlAdapterError(Exception):
    """A failure the adapter handled deliberately, tagged with a stable class.

    error_class is one of: ValidationError, Unavailable, Timeout, QueryError.
    """

    def __init__(self, error_class: str, message: str) -> None:
        super().__init__(message)
        self.error_class = error_class

    def __str__(self) -> str:  # what the MCP client ultimately sees
        return f"[{self.error_class}] {super().__str__()}"


def _validate(database, query, params, timeout_seconds, max_rows) -> list:
    """Check every argument before any connection or file access happens."""
    if not isinstance(database, str) or not database.strip():
        raise SqlAdapterError(
            "ValidationError",
            "`database` must be a non-empty string: a path to a SQLite file "
            "under the SQL data root.",
        )
    if not isinstance(query, str) or not query.strip():
        raise SqlAdapterError("ValidationError", "`query` must be a non-empty SQL string.")
    if len(query) > MAX_QUERY_CHARS:
        raise SqlAdapterError(
            "ValidationError",
            f"`query` is {len(query)} characters; the limit is {MAX_QUERY_CHARS}.",
        )

    body = query.strip().rstrip(";").strip()
    if ";" in body:
        raise SqlAdapterError(
            "ValidationError",
            "one SQL statement per call; multiple ';'-separated statements were found.",
        )
    first = re.split(r"\s+", body.lower(), maxsplit=1)[0] if body else ""
    if not first:
        raise SqlAdapterError("ValidationError", "could not read a leading SQL keyword from `query`.")
    if first in _WRITE_VERBS:
        raise SqlAdapterError(
            "ValidationError",
            f"this adapter is read-only; a statement beginning with "
            f"'{first.upper()}' is rejected. Use SELECT, WITH, EXPLAIN or PRAGMA.",
        )

    if params is None:
        params = []
    if not isinstance(params, (list, tuple)):
        raise SqlAdapterError("ValidationError", "`params` must be a list when provided.")
    if len(params) > MAX_PARAMS:
        raise SqlAdapterError(
            "ValidationError", f"`params` has {len(params)} items; the limit is {MAX_PARAMS}."
        )
    for i, value in enumerate(params):
        if value is not None and not isinstance(value, _ALLOWED_PARAM_TYPES):
            raise SqlAdapterError(
                "ValidationError",
                f"`params[{i}]` is {type(value).__name__}; only string, number, "
                "boolean and null are allowed.",
            )

    if isinstance(timeout_seconds, bool) or not isinstance(timeout_seconds, (int, float)):
        raise SqlAdapterError("ValidationError", "`timeout_seconds` must be a number.")
    if not 0 < float(timeout_seconds) <= MAX_TIMEOUT_SECONDS:
        raise SqlAdapterError(
            "ValidationError",
            f"`timeout_seconds` must be greater than 0 and at most {MAX_TIMEOUT_SECONDS}.",
        )

    if isinstance(max_rows, bool) or not isinstance(max_rows, int):
        raise SqlAdapterError("ValidationError", "`max_rows` must be an integer.")
    if not 1 <= max_rows <= MAX_MAX_ROWS:
        raise SqlAdapterError(
            "ValidationError", f"`max_rows` must be between 1 and {MAX_MAX_ROWS}."
        )

    return list(params)


def _deny_attach(action, *_args):
    """SQLite authorizer: hard-deny ATTACH/DETACH so a query cannot open another
    file and step outside the path fence. Everything else is allowed (the
    connection is already read-only)."""
    if action in (sqlite3.SQLITE_ATTACH, sqlite3.SQLITE_DETACH):
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _classify_operational_error(exc: sqlite3.Error, db_path: Path, timeout_seconds: float,
                                timed_out: bool) -> SqlAdapterError:
    msg = str(exc).lower()
    if timed_out or "interrupted" in msg:
        return SqlAdapterError(
            "Timeout",
            f"the query was cancelled after exceeding the {timeout_seconds}s timeout. "
            f"Narrow the query or raise timeout_seconds (max {MAX_TIMEOUT_SECONDS}).",
        )
    if "locked" in msg or "busy" in msg:
        return SqlAdapterError(
            "Unavailable",
            "the database is locked by another process; try again shortly.",
        )
    if "not authorized" in msg:
        return SqlAdapterError(
            "ValidationError", "ATTACH/DETACH is not permitted by this adapter."
        )
    if "readonly" in msg or "attempt to write" in msg:
        return SqlAdapterError(
            "ValidationError",
            "this adapter is read-only; the statement tried to modify the database.",
        )
    if "unable to open database file" in msg or "not a database" in msg:
        return SqlAdapterError(
            "Unavailable",
            f"the database at {db_path} could not be opened ({exc}). It may be "
            "missing, unreadable, or not a SQLite file.",
        )
    if "no such table" in msg or "no such column" in msg or "syntax error" in msg:
        return SqlAdapterError("QueryError", f"the query could not run: {exc}.")
    return SqlAdapterError("QueryError", f"the query failed: {exc}.")


def run_sql_query(
    database: str,
    query: str,
    params: list | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_rows: int = DEFAULT_MAX_ROWS,
    data_root: Path | None = None,
) -> dict:
    """Run one read-only SQL statement against a fenced SQLite file.

    Returns a dict: database, columns, rows, row_count, truncated, elapsed_ms.
    Raises SqlAdapterError (never a bare sqlite3 exception, never a hang) for a
    bad argument, a path escape, a missing/corrupt/locked database, a write
    attempt, a broken query, or a timeout.
    """
    params = _validate(database, query, params, timeout_seconds, max_rows)
    root = data_root or SQL_DATA_ROOT

    try:
        db_path = resolve_within(root, database, what="database path")
    except ValueError as exc:
        raise SqlAdapterError("ValidationError", str(exc)) from exc

    if not db_path.exists():
        raise SqlAdapterError(
            "Unavailable",
            f"database file not found: {db_path} (looked under the SQL data root "
            f"{root}). The SQL system is unreachable.",
        )
    if not db_path.is_file():
        raise SqlAdapterError("Unavailable", f"the database path is not a file: {db_path}.")

    started = time.monotonic()
    conn: sqlite3.Connection | None = None
    timer: threading.Timer | None = None
    timed_out = {"flag": False}

    # Open the connection and force a read of the database header/schema. Any
    # failure here means the system itself is unreachable (missing, corrupt,
    # locked, not a SQLite file) rather than the query being wrong.
    try:
        conn = sqlite3.connect(
            f"file:{db_path}?mode=ro",
            uri=True,
            timeout=min(float(timeout_seconds), MAX_TIMEOUT_SECONDS),
            isolation_level=None,
        )
        conn.set_authorizer(_deny_attach)
        conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone()
    except sqlite3.Error as exc:
        if conn is not None:
            conn.close()
        low = str(exc).lower()
        if "locked" in low or "busy" in low:
            raise SqlAdapterError(
                "Unavailable", "the database is locked by another process; try again shortly."
            ) from exc
        raise SqlAdapterError(
            "Unavailable",
            f"the database at {db_path} could not be opened ({exc}). It may be "
            "missing, unreadable, or not a SQLite file.",
        ) from exc

    try:
        # Watchdog: interrupt() is safe from another thread and makes the running
        # execute()/fetch raise OperationalError("interrupted"). This is what
        # stops a slow database from hanging the server indefinitely.
        def _abort() -> None:
            timed_out["flag"] = True
            conn.interrupt()

        timer = threading.Timer(float(timeout_seconds), _abort)
        timer.start()

        cursor = conn.execute(query, params)
        rows = cursor.fetchmany(max_rows + 1)
        timer.cancel()  # query finished in time; stop the watchdog now
        columns = [d[0] for d in cursor.description] if cursor.description else []
    except (sqlite3.OperationalError, sqlite3.DatabaseError) as exc:
        raise _classify_operational_error(
            exc, db_path, float(timeout_seconds), timed_out["flag"]
        ) from exc
    finally:
        if timer is not None:
            timer.cancel()
        if conn is not None:
            conn.close()

    truncated = len(rows) > max_rows
    rows = rows[:max_rows]
    return {
        "database": str(db_path),
        "columns": columns,
        "rows": [list(r) for r in rows],
        "row_count": len(rows),
        "truncated": truncated,
        "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
    }
