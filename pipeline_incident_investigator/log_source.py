"""Connects to the logging data source for a pipeline incident (REQ-008, REQ-001)."""

from __future__ import annotations

import json
from pathlib import Path


class LogsUnavailableError(Exception):
    """The log source itself could not be reached or read."""


class LogsIncompleteError(Exception):
    """The log source was read but has no usable execution logs."""


def load_incident(path: str | Path) -> dict:
    """Load the full incident record from its JSON source file."""
    path = Path(path)

    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise LogsUnavailableError(f"No log source found at {path}") from exc
    except OSError as exc:
        raise LogsUnavailableError(f"Could not read log source at {path}: {exc}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise LogsUnavailableError(f"Log source at {path} is not valid JSON: {exc}") from exc


def load_incident_logs(path: str | Path) -> list[str]:
    """Load the execution log lines for an incident from its JSON source file."""
    incident = load_incident(path)

    logs = incident.get("execution_logs")
    if not isinstance(logs, list) or not logs:
        raise LogsIncompleteError(f"Log source at {path} has no execution_logs entries")

    return logs
