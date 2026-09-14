"""Append-only audit trail for investigation activities (REQ-011)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path


class AuditLoggingError(Exception):
    """Raised when an investigation activity could not be recorded to the audit trail."""


@dataclass(frozen=True)
class AuditEntry:
    correlation_id: str
    incident_id: str
    activity: str
    outcome: str
    timestamp: str
    details: dict


def record_activity(
    log_path: str | Path,
    *,
    correlation_id: str,
    incident_id: str,
    activity: str,
    outcome: str,
    details: dict | None = None,
) -> AuditEntry:
    """Append one investigation activity to the audit trail.

    Idempotent: replaying the same (correlation_id, activity) returns the
    entry already on record instead of writing a duplicate line.
    """
    log_path = Path(log_path)

    existing = _find_existing(log_path, correlation_id, activity)
    if existing is not None:
        return existing

    entry = AuditEntry(
        correlation_id=correlation_id,
        incident_id=incident_id,
        activity=activity,
        outcome=outcome,
        timestamp=datetime.now(timezone.utc).isoformat(),
        details=details or {},
    )

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(asdict(entry)) + "\n")
    except OSError as exc:
        raise AuditLoggingError(f"Could not write audit entry to {log_path}: {exc}") from exc

    return entry


def _find_existing(log_path: Path, correlation_id: str, activity: str) -> AuditEntry | None:
    if not log_path.exists():
        return None

    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("correlation_id") == correlation_id and record.get("activity") == activity:
                return AuditEntry(**record)

    return None
