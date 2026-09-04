"""
Unit tests for quality_review.py — the data-gathering + rule-based-verdict half
of the assess_table_quality tool. No MCP, no model: builds throwaway SQLite
files, checks the statistics and the heuristic, and checks the model-reply
parser against good and malformed input.

Run from the mcp-server/ folder:
    python src/test_quality_review.py
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

import quality_review


def _make_db(root: Path) -> str:
    path = root / "wh.db"
    conn = sqlite3.connect(path)
    conn.executescript(
        """
        CREATE TABLE clean_orders (order_id INTEGER, amount REAL, region TEXT);
        CREATE TABLE bad_orders   (order_id INTEGER, amount REAL, region TEXT);
        CREATE TABLE empty_orders (order_id INTEGER, amount REAL);
        """
    )
    # clean: 100 rows, unique keys, no nulls
    conn.executemany(
        "INSERT INTO clean_orders VALUES (?,?,?)",
        [(i, i * 1.5, "us") for i in range(100)],
    )
    # bad: 100 rows, ~30% null amount, and order_id 1 repeated 5 times
    rows = [(i, (None if i % 10 < 3 else i * 2.0), "us") for i in range(96)]
    rows += [(1, 9.0, "us")] * 4
    conn.executemany("INSERT INTO bad_orders VALUES (?,?,?)", rows)
    conn.commit()
    conn.close()
    return "wh.db"


def test_stats_and_heuristic() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        db = _make_db(root)

        clean = quality_review.gather_table_stats(db, "clean_orders", data_root=root)
        assert clean["row_count"] == 100, clean
        assert all(c["null_count"] == 0 for c in clean["columns"]), clean
        assert [k["name"] for k in clean["key_columns"]] == ["order_id"], clean
        assert clean["key_columns"][0]["duplicate_count"] == 0, clean
        v = quality_review.heuristic_verdict(clean)
        assert v["verdict"] == "PASS", v

        bad = quality_review.gather_table_stats(db, "bad_orders", data_root=root)
        amount = next(c for c in bad["columns"] if c["name"] == "amount")
        assert amount["null_count"] > 0 and amount["null_rate"] >= 0.2, bad
        assert bad["key_columns"][0]["duplicate_count"] == 4, bad
        v = quality_review.heuristic_verdict(bad)
        assert v["verdict"] == "FAIL", v
        assert "order_id" in v["suspect_columns"] and "amount" in v["suspect_columns"], v
        assert any("duplicate" in r for r in v["reasons"]), v

        empty = quality_review.gather_table_stats(db, "empty_orders", data_root=root)
        assert empty["row_count"] == 0, empty
        assert quality_review.heuristic_verdict(empty)["verdict"] == "WARN", empty

    print("PASS: gather_table_stats + heuristic_verdict")


def test_rejects_bad_identifier_and_unknown_table() -> None:
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        db = _make_db(root)
        for bad in ["orders; drop table x", "orders WHERE 1", "1abc", ""]:
            try:
                quality_review.gather_table_stats(db, bad, data_root=root)
            except quality_review.QualityInputError:
                pass
            else:
                raise AssertionError(f"expected QualityInputError for table={bad!r}")
        try:
            quality_review.gather_table_stats(db, "no_such_table", data_root=root)
        except quality_review.QualityInputError:
            pass
        else:
            raise AssertionError("expected QualityInputError for an unknown table")
    print("PASS: bad identifiers and unknown tables are rejected")


def test_reply_parser() -> None:
    good = 'Here is my call:\n{"verdict":"warn","reasons":["x"],"suspect_columns":["amount"]}\ndone'
    p = quality_review._parse_verdict(good)
    assert p and p["verdict"] == "WARN" and p["suspect_columns"] == ["amount"], p

    for junk in ["", "no json here", "{not json}", '{"verdict":"MAYBE"}', '{"reasons":[]}']:
        assert quality_review._parse_verdict(junk) is None, junk

    # render_from_model must fall back to the heuristic, not raise or go empty
    stats = {
        "database": "wh.db", "table": "t", "row_count": 1,
        "columns": [{"name": "a", "type": "TEXT", "null_count": 0, "null_rate": 0.0}],
        "key_columns": [],
    }
    heur = quality_review.heuristic_verdict(stats)

    class _Blob:
        text = "the model said no"

    class _Reply:
        content = _Blob()
        model = "test"

    out = quality_review.render_from_model(stats, heur, _Reply(), sampling_ms=1.0)
    assert '"verdict"' in out and "could not be parsed" in out, out
    print("PASS: _parse_verdict + render_from_model fallback")


def test_step_functions_compose_to_gather_table_stats() -> None:
    """The four stepped functions, run in order, must build exactly the dict the
    one-shot gather_table_stats returns (server.py drives the steps to report
    progress between them)."""
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        db = _make_db(root)
        for table in ("clean_orders", "bad_orders", "empty_orders"):
            one_shot = quality_review.gather_table_stats(db, table, data_root=root)

            columns = quality_review.fetch_columns(db, table, data_root=root)
            names = [c["name"] for c in columns]
            total, non_null = quality_review.null_counts(db, table, names, data_root=root)
            keys = quality_review.key_column_names(names)
            dups = quality_review.duplicate_counts(db, table, keys, data_root=root) if (keys and total) else {}
            stepped = quality_review.assemble_stats(db, table, columns, total, non_null, dups)

            assert stepped == one_shot, (table, stepped, one_shot)
    print("PASS: stepped fetch/null/dup/assemble == gather_table_stats")


if __name__ == "__main__":
    try:
        test_stats_and_heuristic()
        test_rejects_bad_identifier_and_unknown_table()
        test_reply_parser()
        test_step_functions_compose_to_gather_table_stats()
        print("ALL PASS: quality_review gathers stats, scores them, and parses replies safely.")
    except Exception as exc:  # noqa: BLE001 - top-level test entry point
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
