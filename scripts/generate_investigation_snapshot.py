"""Generate the Command Center's Investigations tab data (STORY-007).

Runs the real pipeline_incident_investigator code -- investigate(), then
submit_investigation_recommendation() for a certain root cause or
notify_if_uncertain() for an uncertain one -- against the three real incident
fixtures already in the repo root. Writes two files under command-center/data/:

  investigations_audit_trail.jsonl -- the actual hash-chained audit trail this
    run produced (STORY-002's audit_log.py). Anyone can independently verify
    it with audit_log.verify_log_integrity() -- nothing here is fabricated.

  investigations_snapshot.json -- a small, browser-friendly summary derived
    from that trail (including each item's real audit timestamp), which
    command-center/assets/tabs.js fetches to render the Investigations tab.

Single responsibility, rerunnable: each run deletes and rebuilds both output
files from scratch rather than appending, so running it twice never leaves
stale or duplicated entries behind -- the idempotency guarantee here is
"always ends in the same regenerated state," which is the right shape for a
derived snapshot (not a source-of-truth ledger, where STORY-002's
dedup-on-replay is the right shape instead).

Usage: python scripts/generate_investigation_snapshot.py
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from pipeline_incident_investigator.approval_workflow import submit_investigation_recommendation
from pipeline_incident_investigator.audit_log import verify_log_integrity
from pipeline_incident_investigator.investigator import investigate
from pipeline_incident_investigator.notification_service import NotificationDeliveryError, notify_if_uncertain

FIXTURES = (
    "data_engineering_incident_test.json",
    "data_engineering_incident_test_2.json",
    "data_engineering_incident_test_3.json",
)

OUTPUT_DIR = REPO_ROOT / "command-center" / "data"
AUDIT_TRAIL_PATH = OUTPUT_DIR / "investigations_audit_trail.jsonl"
SNAPSHOT_PATH = OUTPUT_DIR / "investigations_snapshot.json"


def _fixture_metadata(fixture_path: Path) -> dict:
    raw = json.loads(fixture_path.read_text(encoding="utf-8"))
    return {
        "title": raw.get("incident_title", fixture_path.stem),
        "pipeline_name": raw.get("pipeline_metadata", {}).get("pipeline_name", "unknown"),
        "severity": raw.get("severity", "Unknown"),
        "reported_at": raw.get("reported_at"),
    }


def _audit_entries_for(audit_trail_path: Path, investigation_correlation_id: str, extra_correlation_ids: set) -> list:
    """Every audit entry belonging to one investigation.

    Matches by the entry's own correlation_id (how log_analysis/recommendation
    and recommendation_submitted entries are keyed) OR by
    details.investigation_correlation_id (how notify_if_uncertain's entries
    are keyed -- see notification_service.py's module docstring for why a
    notification can't reuse the investigation's correlation_id directly).
    """
    matches = []
    for e in verify_log_integrity(audit_trail_path):
        if e.correlation_id == investigation_correlation_id or e.correlation_id in extra_correlation_ids:
            matches.append(e)
        elif e.details.get("investigation_correlation_id") == investigation_correlation_id:
            matches.append(e)
    return [{"activity": e.activity, "outcome": e.outcome, "timestamp": e.timestamp} for e in matches]


def _investigate_one(fixture_name: str, audit_trail_path: Path) -> dict:
    fixture_path = REPO_ROOT / fixture_name
    meta = _fixture_metadata(fixture_path)

    investigation = investigate(fixture_path, audit_log_path=audit_trail_path)
    extra_correlation_ids = set()

    certain = investigation.recommendation is not None
    recommendation_summary = None
    notification_summary = None

    if certain:
        approval = submit_investigation_recommendation(investigation, audit_log_path=audit_trail_path)
        extra_correlation_ids.add(approval.decision_id)
        recommendation_summary = {
            "category": approval.category,
            "severity": approval.severity,
            "is_major": approval.is_major,
            "status": approval.status,
            "recommended_action": investigation.recommendation.recommended_action,
        }
    else:
        try:
            notification = notify_if_uncertain(investigation, audit_log_path=audit_trail_path)
            notification_summary = {"status": notification.status, "reason": notification.reason}
        except NotificationDeliveryError as exc:
            notification_summary = {"status": exc.record.status, "reason": exc.record.reason}

    return {
        "incident_id": investigation.incident_id,
        "title": meta["title"],
        "pipeline_name": meta["pipeline_name"],
        "severity": meta["severity"],
        "reported_at": meta["reported_at"],
        "certain": certain,
        "recommendation": recommendation_summary,
        "notification": notification_summary,
        "audit_entries": _audit_entries_for(audit_trail_path, investigation.correlation_id, extra_correlation_ids),
    }


def build_snapshot(audit_trail_path: Path = AUDIT_TRAIL_PATH) -> dict:
    """Run the real pipeline against all three fixtures and return the snapshot dict.

    audit_trail_path is overridable so tests can point it at a tempdir instead
    of overwriting the real committed audit trail as a side effect of testing.
    """
    audit_trail_path = Path(audit_trail_path)
    if audit_trail_path.exists():
        audit_trail_path.unlink()  # start every run from a clean, honest trail

    incidents = [_investigate_one(name, audit_trail_path) for name in FIXTURES]

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "incidents": incidents,
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    snapshot = build_snapshot(AUDIT_TRAIL_PATH)
    SNAPSHOT_PATH.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {SNAPSHOT_PATH} ({len(snapshot['incidents'])} incidents)")
    print(f"Wrote {AUDIT_TRAIL_PATH}")


if __name__ == "__main__":
    main()
