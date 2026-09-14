"""
Table-quality assessment — the data-gathering and reasoning-scaffold half of the
`assess_table_quality` tool in server.py.

Split out of server.py the same way sql_adapter.py and notes_store.py are: this
module never touches MCP. It does three jobs, none of which calls a model:

  1. `gather_table_stats()` — pulls real statistics about one table straight from
     SQLite through sql_adapter (row count, per-column null rate, duplicate
     counts on key-looking columns). No model, no network.
  2. `heuristic_verdict()` — turns those statistics into a PASS/WARN/FAIL verdict
     using fixed rules. This is both the "first pass" shown to the model and the
     degraded answer returned when the client cannot or will not do sampling.
  3. `build_sampling_prompt()` / `render*()` — build the short prompt the server
     hands to the *client's* model via MCP sampling, and fold the reply (or, on
     failure, the heuristic) into one stable JSON response shape.

No API key and no model name appear here or anywhere else in this server — the
model call belongs to the client (see server.py).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import sql_adapter

# A column whose name looks like a key. A key column with duplicate values is
# the classic partial-load / double-insert signature this tool exists to catch,
# so those columns get a dedicated duplicate count.
_KEY_NAME = re.compile(r"(?i)^(id|.*_id|.*_key|.*_pk|.*_sk|uuid|guid|hash)$")

# The only shape we will interpolate into SQL. There is no parameter binding for
# table or column names, so anything that is not a plain SQLite identifier is
# rejected before a query string is built.
_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

_MAX_COLUMNS = 80          # keep the stats query and the prompt bounded
_STATS_TIMEOUT_S = 15.0

# Null-rate thresholds for the rule-based verdict.
_WARN_NULL = 0.05
_FAIL_NULL = 0.20

_SYSTEM_PROMPT = (
    "You are a data-quality reviewer. You are given summary statistics for a "
    "single database table - never the raw rows. Decide whether the table is "
    "safe to publish to downstream consumers. Reply with ONLY a JSON object of "
    'the form {"verdict": "PASS" | "WARN" | "FAIL", "reasons": [string, ...], '
    '"suspect_columns": [string, ...]}. Judge only from the statistics given. '
    "Duplicate values in a key-like column, or unexpectedly high null rates in "
    "columns that should be populated, are WARN or FAIL depending on severity."
)


class QualityInputError(ValueError):
    """A bad argument to assess_table_quality (bad identifier, unknown table)."""


# --- 1. gather real statistics -------------------------------------------------

def _ident(name: str, kind: str) -> str:
    if not isinstance(name, str) or not _IDENT.match(name or ""):
        raise QualityInputError(
            f"{kind} {name!r} is not a plain SQLite identifier "
            f"(letters, digits and underscore; not starting with a digit)."
        )
    return name


def _rows(database: str, sql: str, data_root: Path | None = None) -> list:
    """One read-only query through the fenced adapter; return just the rows.

    sql_adapter enforces the path fence, read-only mode and a timeout, and
    raises sql_adapter.SqlAdapterError (never a bare sqlite3 error) for a
    missing / corrupt / locked database or a broken query.
    """
    return sql_adapter.run_sql_query(
        database=database,
        query=sql,
        params=None,
        timeout_seconds=_STATS_TIMEOUT_S,
        max_rows=_MAX_COLUMNS + 5,
        data_root=data_root,
    )["rows"]


# gather_table_stats() below is one call that returns the whole stats dict. It is
# also broken into the four steps a caller can drive one at a time, so a tool can
# report progress between them (see server.py's assess_table_quality). The
# one-shot wrapper just calls the four in order — behaviour and return shape are
# identical either way. `data_root` overrides the SQL data-root fence (tests
# only); left None it defaults to sql_adapter.SQL_DATA_ROOT, like run_sql_query.


def fetch_columns(database: str, table: str, data_root: Path | None = None) -> list[dict]:
    """Step 1: the table's columns as [{"name", "type"}, ...] (capped at _MAX_COLUMNS).

    Raises QualityInputError for a bad identifier or an unknown table, and
    sql_adapter.SqlAdapterError for a database that is missing / unreadable.
    """
    tbl = _ident(table, "table")
    cols = _rows(database, f"SELECT name, type FROM pragma_table_info('{tbl}')", data_root)
    if not cols:
        raise QualityInputError(
            f"table {tbl!r} was not found in {database!r} (it reported no columns)."
        )
    return [{"name": _ident(c[0], "column"), "type": (c[1] or "")} for c in cols[:_MAX_COLUMNS]]


def key_column_names(column_names: list[str]) -> list[str]:
    """The subset of column names that look like keys (checked for duplicates)."""
    return [n for n in column_names if _KEY_NAME.match(n)]


def null_counts(
    database: str, table: str, column_names: list[str], data_root: Path | None = None
) -> tuple[int, dict[str, int]]:
    """Step 2: (total row count, {column: non-null count}) in a single pass."""
    tbl = _ident(table, "table")
    names = [_ident(n, "column") for n in column_names]
    select = ", ".join(f'COUNT("{n}") AS "{n}"' for n in names)
    row = _rows(database, f'SELECT COUNT(*) AS _total, {select} FROM "{tbl}"', data_root)[0]
    return int(row[0]), {n: int(row[i + 1]) for i, n in enumerate(names)}


def duplicate_counts(
    database: str, table: str, key_names: list[str], data_root: Path | None = None
) -> dict[str, int]:
    """Step 3: {key column: how many values are duplicated} in a single pass.
    Empty when there are no key-like columns."""
    if not key_names:
        return {}
    tbl = _ident(table, "table")
    names = [_ident(n, "column") for n in key_names]
    select = ", ".join(f'COUNT("{n}") - COUNT(DISTINCT "{n}") AS "{n}"' for n in names)
    row = _rows(database, f'SELECT {select} FROM "{tbl}"', data_root)[0]
    return {n: int(row[i]) for i, n in enumerate(names)}


def assemble_stats(
    database: str,
    table: str,
    columns: list[dict],
    total_rows: int,
    non_null: dict[str, int],
    dup_counts: dict[str, int],
) -> dict:
    """Step 4: fold the three measurements into the stats dict the verdict uses."""
    key_names = key_column_names([c["name"] for c in columns])
    out_columns = []
    for c in columns:
        n = c["name"]
        missing = total_rows - non_null.get(n, total_rows) if total_rows else 0
        out_columns.append(
            {
                "name": n,
                "type": c["type"],
                "null_count": missing,
                "null_rate": round(missing / total_rows, 4) if total_rows else None,
            }
        )
    return {
        "database": database,
        "table": _ident(table, "table"),
        "row_count": total_rows,
        "columns": out_columns,
        "key_columns": [
            {"name": n, "duplicate_count": dup_counts.get(n, 0)} for n in key_names
        ],
    }


def gather_table_stats(database: str, table: str, data_root: Path | None = None) -> dict:
    """Collect the statistics the verdict is based on, in one call. No model involved.

    Equivalent to running fetch_columns -> null_counts -> duplicate_counts ->
    assemble_stats in order; use those directly when you need to report progress
    between the steps.
    """
    columns = fetch_columns(database, table, data_root)
    names = [c["name"] for c in columns]
    total, non_null = null_counts(database, table, names, data_root)
    key_names = key_column_names(names)
    dup_counts = (
        duplicate_counts(database, table, key_names, data_root)
        if (key_names and total)
        else {}
    )
    return assemble_stats(database, table, columns, total, non_null, dup_counts)


# --- 2. rule-based verdict (also the degraded answer) ------------------------

def heuristic_verdict(stats: dict) -> dict:
    """PASS / WARN / FAIL from the statistics alone, with reasons."""
    total = stats["row_count"]
    reasons: list[str] = []
    suspect: list[str] = []

    dup_keys = [k for k in stats["key_columns"] if k["duplicate_count"] > 0]
    for k in dup_keys:
        suspect.append(k["name"])
        reasons.append(
            f'key-like column "{k["name"]}" has {k["duplicate_count"]} duplicate '
            f"value(s) where every value should be unique"
        )

    worst = 0.0
    for c in stats["columns"]:
        rate = c["null_rate"]
        if rate is None:
            continue
        worst = max(worst, rate)
        if rate >= _WARN_NULL:
            suspect.append(c["name"])
            reasons.append(
                f'column "{c["name"]}" is {rate:.1%} null ({c["null_count"]} of {total})'
            )

    if total == 0:
        reasons.append("table has no rows")

    if dup_keys or worst >= _FAIL_NULL:
        verdict = "FAIL"
    elif worst >= _WARN_NULL or total == 0:
        verdict = "WARN"
    else:
        verdict = "PASS"
        reasons.append(
            f"no duplicate keys and every column is less than {_WARN_NULL:.0%} null"
        )

    return {"verdict": verdict, "reasons": reasons, "suspect_columns": sorted(set(suspect))}


# --- 3. sampling prompt + response shaping ---------------------------------

def build_sampling_prompt(stats: dict, heuristic: dict) -> tuple[str, str]:
    """Return (system_prompt, user_text) for the client sampling request."""
    payload = {
        "table": stats["table"],
        "row_count": stats["row_count"],
        "columns": stats["columns"],
        "key_columns": stats["key_columns"],
        "rule_based_first_pass": heuristic,
    }
    user_text = (
        "Assess this table's data quality.\n\n"
        + json.dumps(payload, indent=2, default=str)
        + "\n\nReturn only the JSON object described in your instructions."
    )
    return _SYSTEM_PROMPT, user_text


def render(
    stats: dict,
    verdict: dict,
    *,
    assessed_by: str,
    sampling_ms: float | None = None,
    model_note: str | None = None,
) -> str:
    """The one response shape the tool returns, whichever path produced it."""
    out = {
        "table": stats["table"],
        "database": stats["database"],
        "row_count": stats["row_count"],
        "verdict": verdict["verdict"],
        "reasons": verdict["reasons"],
        "suspect_columns": verdict["suspect_columns"],
        "assessed_by": assessed_by,
        "statistics": {
            "columns": stats["columns"],
            "key_columns": stats["key_columns"],
        },
    }
    if sampling_ms is not None:
        out["sampling_ms"] = sampling_ms
    if model_note:
        out["model_note"] = model_note
    return json.dumps(out, indent=2, default=str)


def render_from_model(stats: dict, heuristic: dict, reply, *, sampling_ms: float) -> str:
    """Fold the model's reply into the response; fall back to the heuristic if
    the reply cannot be parsed. Never returns an empty answer."""
    text = _reply_text(reply)
    parsed = _parse_verdict(text)
    if parsed is None:
        return render(
            stats,
            heuristic,
            assessed_by="rule-based (model reply could not be parsed)",
            sampling_ms=sampling_ms,
            model_note=(text[:500] if text else "the client returned an empty reply"),
        )
    return render(
        stats,
        parsed,
        assessed_by="client model via MCP sampling",
        sampling_ms=sampling_ms,
        model_note=f"model={getattr(reply, 'model', None)!r}",
    )


def _reply_text(reply) -> str:
    content = getattr(reply, "content", None)
    if content is None:
        return ""
    if isinstance(content, list):
        return "\n".join(getattr(b, "text", "") or "" for b in content).strip()
    return (getattr(content, "text", "") or "").strip()


def _parse_verdict(text: str) -> dict | None:
    """Pull the {verdict, reasons, suspect_columns} object out of the reply, or
    None if it is missing / malformed / not one of the three verdicts."""
    if not text:
        return None
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        return None
    try:
        obj = json.loads(text[start : end + 1])
    except (ValueError, TypeError):
        return None
    if not isinstance(obj, dict):
        return None
    verdict = str(obj.get("verdict", "")).strip().upper()
    if verdict not in {"PASS", "WARN", "FAIL"}:
        return None
    reasons = obj.get("reasons") or []
    suspect = obj.get("suspect_columns") or []
    if not isinstance(reasons, list):
        reasons = [str(reasons)]
    if not isinstance(suspect, list):
        suspect = [str(suspect)]
    return {
        "verdict": verdict,
        "reasons": [str(r) for r in reasons][:20],
        "suspect_columns": [str(s) for s in suspect][:20],
    }
