"""Connects to the SQL data source for a pipeline incident (REQ-003)."""

from __future__ import annotations

import json
from pathlib import Path


class SqlSourceUnavailableError(Exception):
    """The SQL data source itself could not be reached or read."""


class SqlInfoMissingError(Exception):
    """The source was read but has no usable SQL query to analyze."""


def load_incident_sql(path: str | Path) -> dict:
    """Load the SQL query -- and, when available, the current schema -- for an incident."""
    path = Path(path)

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise SqlSourceUnavailableError(f"No SQL source found at {path}") from exc
    except OSError as exc:
        raise SqlSourceUnavailableError(f"Could not read SQL source at {path}: {exc}") from exc

    try:
        incident = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SqlSourceUnavailableError(f"SQL source at {path} is not valid JSON: {exc}") from exc

    sql_info = incident.get("sql_info") or {}
    query = sql_info.get("query")
    if not isinstance(query, str) or not query.strip():
        raise SqlInfoMissingError(f"SQL source at {path} has no usable sql_info.query")

    schema_history = incident.get("schema_history") or {}
    current_schema = schema_history.get("current_schema")
    current_schema_columns = None
    if isinstance(current_schema, list):
        current_schema_columns = [
            col["column"] for col in current_schema if isinstance(col, dict) and "column" in col
        ]

    return {
        "incident_id": incident.get("incident_id"),
        "query": query,
        "current_schema_columns": current_schema_columns,
    }
