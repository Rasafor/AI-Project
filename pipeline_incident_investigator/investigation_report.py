"""Detailed reports of investigation outcomes, rebuilt from the audit trail.

Satisfies STORY-008: give a data engineer a detailed, machine-readable report
of one investigation's outcome -- including full failure details when the
investigation (or any agent in it) failed -- and log every report generated
(REQ-017, REQ-011).

The report is rebuilt from the hash-chained audit trail rather than from an
in-memory result object, so it can be regenerated at any time, picks up
approvals and notifications recorded after the investigation itself ran, and
refuses to report on a trail whose hash chain does not verify (the "incorrect
report data" failure path).

An audit entry belongs to an investigation when its correlation_id is the
investigation's, or when details.investigation_correlation_id points at it
(notification_service and approval_workflow key their entries by their own
ids and link back this way -- the same match STORY-007's snapshot needed).
Approval decisions are one hop further: they are keyed by the decision_id of
a linked recommendation_submitted entry.

Idempotency: report_hash is a SHA-256 over the report's content, excluding
generated_at and the report_* entries themselves, and the report_generated
audit entry's correlation id is derived from (investigation id, report_hash).
Regenerating an unchanged report is therefore logged once; a report whose
content changed (e.g. an approval landed since) is logged as a new entry.

Performance: one integrity-verifying pass over the audit trail per report,
O(entries in the trail). There is no index -- fine for this walking
skeleton's trail sizes, the first thing to revisit if trails grow large.

Authorization is a small allow-list, not the full RBAC of REQ-018 (still
unfulfilled by any story), mirroring notification_service.get_notification.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from pipeline_incident_investigator.audit_log import (
    AuditEntry,
    AuditLoggingError,
    AuditLogTamperedError,
    record_activity,
    verify_log_integrity,
)

DEFAULT_AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_trail.jsonl"

ALLOWED_REPORT_ROLES = {"data_engineer", "ops_lead", "incident_commander"}

# Report bookkeeping entries are not part of a report's own content -- including
# them would make every regeneration change the hash it is keyed by.
_REPORT_ACTIVITIES = {"report_generated", "report_access_denied"}
_FAILURE_OUTCOMES = {"failure", "failed"}


class ReportNotFoundError(Exception):
    """Raised when the audit trail has no entries for the given investigation."""


class UnauthorizedReportAccessError(Exception):
    """Raised when the viewer's role is not permitted to generate reports."""


class ReportDataIntegrityError(Exception):
    """Raised when the audit trail's hash chain does not verify, so any report
    built from it could contain incorrect data."""


class ReportAuditError(Exception):
    """Raised when a generated report, or a denied attempt, could not be
    written to the audit trail. An unaudited report is not returned."""


@dataclass(frozen=True)
class FailureDetail:
    activity: str
    timestamp: str
    outcome: str
    error_class: str | None
    error: str | None
    details: dict


@dataclass(frozen=True)
class InvestigationReport:
    investigation_correlation_id: str
    incident_id: str
    status: str  # "success" | "partial_failure" | "failure" | "incomplete"
    activities: list[dict] = field(default_factory=list)
    failures: list[FailureDetail] = field(default_factory=list)
    recommendations: list[dict] = field(default_factory=list)
    approvals: list[dict] = field(default_factory=list)
    notifications: list[dict] = field(default_factory=list)
    report_hash: str = ""
    generated_at: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def generate_report(
    investigation_correlation_id: str,
    *,
    viewer: str,
    viewer_role: str,
    audit_log_path: str | Path = DEFAULT_AUDIT_LOG_PATH,
) -> InvestigationReport:
    """Build a detailed report of one investigation's outcome and audit it.

    Authorization is checked first; a denied viewer learns nothing about
    whether the investigation exists, and the denial is audited. Raises
    UnauthorizedReportAccessError, ReportDataIntegrityError,
    ReportNotFoundError, or ReportAuditError.
    """
    if viewer_role not in ALLOWED_REPORT_ROLES:
        _audit(
            audit_log_path,
            correlation_id=str(uuid.uuid4()),
            incident_id=investigation_correlation_id,
            activity="report_access_denied",
            outcome="unauthorized",
            details={
                "investigation_correlation_id": investigation_correlation_id,
                "attempted_by": viewer,
                "attempted_role": viewer_role,
            },
        )
        raise UnauthorizedReportAccessError(
            f"Role '{viewer_role}' is not permitted to view reports (viewer: '{viewer}')"
        )

    try:
        trail = verify_log_integrity(audit_log_path)
    except AuditLogTamperedError as exc:
        raise ReportDataIntegrityError(f"Refusing to report on an unverifiable audit trail: {exc}") from exc

    entries = _entries_for(investigation_correlation_id, trail)
    if not entries:
        raise ReportNotFoundError(
            f"No audit entries were recorded for investigation '{investigation_correlation_id}'"
        )

    report = _build_report(investigation_correlation_id, entries)
    report_hash = _hash_content(report.to_dict())

    _audit(
        audit_log_path,
        correlation_id=str(uuid.uuid5(uuid.NAMESPACE_URL, f"report:{investigation_correlation_id}:{report_hash}")),
        incident_id=report.incident_id,
        activity="report_generated",
        outcome="success",
        details={
            "investigation_correlation_id": investigation_correlation_id,
            "report_hash": report_hash,
            "status": report.status,
            "generated_by": viewer,
            "generated_role": viewer_role,
        },
    )

    return InvestigationReport(
        **{**report.__dict__, "report_hash": report_hash, "generated_at": datetime.now(timezone.utc).isoformat()}
    )


def _entries_for(investigation_correlation_id: str, trail: list[AuditEntry]) -> list[AuditEntry]:
    """Every non-report entry linked to the investigation, in trail order."""
    decision_ids = {
        e.correlation_id
        for e in trail
        if e.activity == "recommendation_submitted"
        and e.details.get("investigation_correlation_id") == investigation_correlation_id
    }
    return [
        e
        for e in trail
        if e.activity not in _REPORT_ACTIVITIES
        and (
            e.correlation_id == investigation_correlation_id
            or e.details.get("investigation_correlation_id") == investigation_correlation_id
            or e.correlation_id in decision_ids
        )
    ]


def _build_report(investigation_correlation_id: str, entries: list[AuditEntry]) -> InvestigationReport:
    failures = [
        FailureDetail(
            activity=e.activity,
            timestamp=e.timestamp,
            outcome=e.outcome,
            error_class=e.details.get("error_class"),
            error=e.details.get("error"),
            details=e.details,
        )
        for e in entries
        if e.outcome in _FAILURE_OUTCOMES
    ]
    return InvestigationReport(
        investigation_correlation_id=investigation_correlation_id,
        incident_id=entries[-1].incident_id,
        status=_status(investigation_correlation_id, entries),
        activities=[asdict(e) for e in entries],
        failures=failures,
        recommendations=[asdict(e) for e in entries if e.activity == "recommendation_submitted"],
        approvals=[asdict(e) for e in entries if e.activity == "approval_decision"],
        notifications=[asdict(e) for e in entries if e.activity == "notification_sent"],
    )


def _status(investigation_correlation_id: str, entries: list[AuditEntry]) -> str:
    """Coordinated runs report the coordinator's own verdict; a coordinated run
    with no summary never finished; a standalone agent run fails if any of its
    own steps did. Linked entries (e.g. a failed notification) are reported as
    failures but do not change the investigation's own status."""
    own = [e for e in entries if e.correlation_id == investigation_correlation_id]
    activities = {e.activity: e for e in own}
    if "agent_coordination" in activities:
        return activities["agent_coordination"].outcome
    if "coordination_initiated" in activities:
        return "incomplete"
    return "failure" if any(e.outcome in _FAILURE_OUTCOMES for e in own) else "success"


def _hash_content(report_fields: dict) -> str:
    content = {k: v for k, v in report_fields.items() if k not in ("report_hash", "generated_at")}
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _audit(audit_log_path: str | Path, **kwargs) -> None:
    try:
        record_activity(audit_log_path, **kwargs)
    except AuditLoggingError as exc:
        raise ReportAuditError(f"Could not record {kwargs['activity']} to the audit trail: {exc}") from exc
