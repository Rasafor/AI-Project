"""
Unit tests for sql_adapter: input validation, the path fence, the timeout, and
graceful failure when the SQLite "system" is missing, corrupt, locked, or the
query is bad.

Run from the mcp-server/ folder:
    python src/test_sql_adapter.py

No framework — assertions plus an exit code, same gating role as the other
tests here. Each interesting failure is printed so you can see the exact
message a caller would get.
"""

import sqlite3
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sql_adapter import (  # noqa: E402
    MAX_TIMEOUT_SECONDS,
    SqlAdapterError,
    run_sql_query,
)


def _run(name, fn):
    try:
        fn()
    except AssertionError as exc:
        print(f"FAIL: {name}: {exc}", file=sys.stderr)
        sys.exit(1)
    print(f"PASS: {name}")


def _make_db(dirpath: Path, name: str = "incidents.db") -> str:
    con = sqlite3.connect(dirpath / name)
    con.executescript(
        """
        CREATE TABLE incidents (id INTEGER PRIMARY KEY, severity TEXT, service TEXT);
        INSERT INTO incidents (severity, service) VALUES
            ('high', 'ingest'), ('low', 'ingest'), ('high', 'transform'),
            ('medium', 'load'), ('high', 'load');
        """
    )
    con.commit()
    con.close()
    return name


def _expect_error(fn, error_class):
    try:
        fn()
    except SqlAdapterError as exc:
        assert exc.error_class == error_class, f"expected {error_class}, got {exc.error_class}: {exc}"
        return exc
    raise AssertionError(f"expected SqlAdapterError[{error_class}], nothing was raised")


def test_validation_runs_before_any_db_access():
    # data_root points nowhere real; validation must still fire first.
    missing_root = Path(tempfile.gettempdir()) / "definitely-not-here-xyz"
    cases = [
        ("empty query", dict(database="x.db", query="   ")),
        ("write statement", dict(database="x.db", query="DELETE FROM incidents")),
        ("DDL statement", dict(database="x.db", query="DROP TABLE incidents")),
        ("two statements", dict(database="x.db", query="SELECT 1; SELECT 2")),
        ("bad timeout (0)", dict(database="x.db", query="SELECT 1", timeout_seconds=0)),
        ("bad timeout (too big)", dict(database="x.db", query="SELECT 1", timeout_seconds=999)),
        ("bad max_rows", dict(database="x.db", query="SELECT 1", max_rows=0)),
        ("params not a list", dict(database="x.db", query="SELECT 1", params="nope")),
        ("param wrong type", dict(database="x.db", query="SELECT ?", params=[{"a": 1}])),
    ]
    for label, kwargs in cases:
        exc = _expect_error(lambda k=kwargs: run_sql_query(data_root=missing_root, **k), "ValidationError")
        print(f"       {label}: {exc}")


def test_happy_path_with_parameter():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        db = _make_db(root)
        out = run_sql_query(
            database=db,
            query="SELECT service, COUNT(*) AS n FROM incidents WHERE severity = ? GROUP BY service ORDER BY service",
            params=["high"],
            data_root=root,
        )
        assert out["columns"] == ["service", "n"], out["columns"]
        assert out["rows"] == [["ingest", 1], ["load", 1], ["transform", 1]], out["rows"]
        assert out["row_count"] == 3 and out["truncated"] is False
        assert isinstance(out["elapsed_ms"], float)
        print(f"       rows={out['rows']} elapsed_ms={out['elapsed_ms']}")


def test_max_rows_truncates():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        db = _make_db(root)
        out = run_sql_query(database=db, query="SELECT id FROM incidents ORDER BY id", max_rows=2, data_root=root)
        assert out["row_count"] == 2 and out["truncated"] is True, out


def test_missing_database_is_useful_error():
    with tempfile.TemporaryDirectory() as d:
        exc = _expect_error(
            lambda: run_sql_query(database="nope.db", query="SELECT 1", data_root=Path(d)),
            "Unavailable",
        )
        assert "not found" in str(exc).lower()
        print(f"       {exc}")


def test_corrupt_database_is_useful_error():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        (root / "bad.db").write_bytes(b"this is definitely not a sqlite file")
        exc = _expect_error(
            lambda: run_sql_query(database="bad.db", query="SELECT 1", data_root=root),
            "Unavailable",
        )
        print(f"       {exc}")


def test_path_fence_rejects_escape():
    with tempfile.TemporaryDirectory() as d:
        exc = _expect_error(
            lambda: run_sql_query(
                database="../../../../etc/passwd", query="SELECT 1", data_root=Path(d)
            ),
            "ValidationError",
        )
        assert "escapes" in str(exc)
        print(f"       {exc}")


def test_attach_is_denied_at_engine():
    # Leading verb is ATTACH -> rejected by the verb check.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        db = _make_db(root)
        exc = _expect_error(
            lambda: run_sql_query(
                database=db, query="ATTACH DATABASE '/etc/hosts' AS evil", data_root=root
            ),
            "ValidationError",
        )
        print(f"       {exc}")


def test_write_that_slips_past_the_verb_check_is_blocked_by_mode_ro():
    # Leading verb is WITH (allowed), but the statement writes -> mode=ro stops it.
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        db = _make_db(root)
        exc = _expect_error(
            lambda: run_sql_query(
                database=db,
                query="WITH x AS (SELECT 1) DELETE FROM incidents",
                data_root=root,
            ),
            "ValidationError",
        )
        assert "read-only" in str(exc)
        print(f"       {exc}")


def test_broken_query_is_query_error_not_crash():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        db = _make_db(root)
        exc = _expect_error(
            lambda: run_sql_query(database=db, query="SELECT * FROM no_such_table", data_root=root),
            "QueryError",
        )
        print(f"       {exc}")


def test_slow_query_times_out_and_does_not_hang():
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        db = _make_db(root)
        slow = (
            "WITH RECURSIVE c(x) AS (SELECT 1 UNION ALL SELECT x + 1 FROM c WHERE x < 1000000000) "
            "SELECT COUNT(*) FROM c"
        )
        start = time.monotonic()
        exc = _expect_error(
            lambda: run_sql_query(database=db, query=slow, timeout_seconds=0.5, data_root=root),
            "Timeout",
        )
        elapsed = time.monotonic() - start
        assert elapsed < MAX_TIMEOUT_SECONDS, f"took {elapsed:.1f}s — watchdog did not fire"
        print(f"       cancelled after {elapsed:.2f}s: {exc}")


if __name__ == "__main__":
    _run("validation runs before any DB access", test_validation_runs_before_any_db_access)
    _run("happy path with a bound parameter", test_happy_path_with_parameter)
    _run("max_rows truncates", test_max_rows_truncates)
    _run("missing database -> Unavailable", test_missing_database_is_useful_error)
    _run("corrupt database -> Unavailable", test_corrupt_database_is_useful_error)
    _run("path fence rejects escape", test_path_fence_rejects_escape)
    _run("ATTACH rejected", test_attach_is_denied_at_engine)
    _run("write via WITH blocked by mode=ro", test_write_that_slips_past_the_verb_check_is_blocked_by_mode_ro)
    _run("broken query -> QueryError", test_broken_query_is_query_error_not_crash)
    _run("slow query times out, no hang", test_slow_query_times_out_and_does_not_hang)
    print("\nALL PASS: sql_adapter validates, fences, times out, and fails gracefully.")
