"""Append-only, tamper-evident audit trail for investigation activities (REQ-011).

Immutability is enforced by hash-chaining: every line embeds the previous
line's hash, so editing, deleting, or reordering any entry breaks the chain
and is caught by verify_log_integrity(). This does not prevent someone with
write access from truncating the *most recent* entries and re-chaining from
there -- true tamper-proofing needs an external anchor (e.g. publishing the
latest hash somewhere append-only outside this file), which is out of scope
for this walking skeleton.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

GENESIS_HASH = "0" * 64
_ENVELOPE_KEYS = ("prev_hash", "entry_hash")


class AuditLoggingError(Exception):
    """Raised when an investigation activity could not be recorded to the audit trail."""


class AuditLogTamperedError(Exception):
    """Raised when the audit trail's hash chain does not verify."""


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

    existing, prev_hash = _scan(log_path, correlation_id, activity)
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
    entry_fields = asdict(entry)

    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            **entry_fields,
            "prev_hash": prev_hash,
            "entry_hash": _compute_entry_hash(prev_hash, entry_fields),
        }
        with log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record) + "\n")
    except OSError as exc:
        raise AuditLoggingError(f"Could not write audit entry to {log_path}: {exc}") from exc

    return entry


def verify_log_integrity(log_path: str | Path) -> list[AuditEntry]:
    """Walk the hash chain and return the entries in order if it is intact.

    Raises AuditLogTamperedError, naming the line where the chain breaks, if
    any entry was edited, deleted, or reordered since it was written.
    """
    log_path = Path(log_path)
    if not log_path.exists():
        return []

    entries: list[AuditEntry] = []
    prev_hash = GENESIS_HASH

    with log_path.open("r", encoding="utf-8") as f:
        for line_number, line in enumerate(f, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise AuditLogTamperedError(
                    f"Audit trail line {line_number} is not valid JSON: {exc}"
                ) from exc

            if record.get("prev_hash") != prev_hash:
                raise AuditLogTamperedError(
                    f"Audit trail broken at line {line_number}: does not chain from the previous entry"
                )

            entry_fields = _entry_fields(record)
            expected_hash = _compute_entry_hash(prev_hash, entry_fields)
            if record.get("entry_hash") != expected_hash:
                raise AuditLogTamperedError(
                    f"Audit trail broken at line {line_number}: entry contents do not match its recorded hash"
                )

            entries.append(AuditEntry(**entry_fields))
            prev_hash = record["entry_hash"]

    return entries


def _scan(log_path: Path, correlation_id: str, activity: str) -> tuple[AuditEntry | None, str]:
    """One pass over the trail: the entry already recorded for (correlation_id, activity), if
    any, and the last entry's hash to chain the next write from.

    STORY-009 optimization: this replaces two separate full reads per write. It stops early
    on a dedup hit, where the hash is not needed. Output is byte-identical to the two-pass
    version (pinned by tests/golden_audit_trail.jsonl).
    """
    last_hash = GENESIS_HASH
    if not log_path.exists():
        return None, last_hash

    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            if record.get("correlation_id") == correlation_id and record.get("activity") == activity:
                return AuditEntry(**_entry_fields(record)), last_hash
            last_hash = record.get("entry_hash", last_hash)

    return None, last_hash


def _entry_fields(record: dict) -> dict:
    """Strip the hash-chain envelope, leaving just the AuditEntry fields."""
    return {k: v for k, v in record.items() if k not in _ENVELOPE_KEYS}


def _compute_entry_hash(prev_hash: str, entry_fields: dict) -> str:
    canonical = json.dumps(entry_fields, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((prev_hash + canonical).encode("utf-8")).hexdigest()
