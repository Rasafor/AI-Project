"""Approval workflow for corrective-action recommendations, with an audit trail.

Satisfies STORY-005: classify a recommendation from any specialist agent (log,
SQL, or data-quality) as major or minor by severity, auto-approve minor ones,
and require an explicit, authorized human decision for major ones (REQ-005,
REQ-010).

Every recommendation and every approval decision is journaled through STORY-002's
hash-chained audit_log.record_activity, keyed by a per-recommendation decision_id
rather than the parent investigation's correlation_id. Reusing the investigation's
correlation_id here would collide on record_activity's (correlation_id, activity)
dedup key the moment one coordinated run produced more than one recommendation --
the second and third would silently vanish instead of being recorded. The
investigation's correlation_id is still carried in the submitted entry's details
for traceability.

Authorization here is a small allow-list, not the full role-based access control
REQ-018 describes -- that requirement is not yet fulfilled by any story. This is
enough to make "unauthorized approvals" a real, audited failure path now.

"Approval delays" (a listed failure path) is addressed by the workflow's shape
rather than by code: it is pull-based, not blocking. A major recommendation sits
in pending_approval for as long as it takes; get_approval() lets anyone check its
state at any time, and nothing here waits on or times out a human decision.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from pipeline_incident_investigator.audit_log import AuditLoggingError, record_activity, verify_log_integrity
from pipeline_incident_investigator.investigator import InvestigationResult

DEFAULT_AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_trail.jsonl"

MAJOR_SEVERITIES = {"high"}

# The one gap left by the existing specialists: SqlIssue and DataQualityIssue
# already carry their own `.severity`, but the log-based Recommendation
# (STORY-001) does not. This maps its two known categories to a severity
# without touching recommendation.py or its tests.
CATEGORY_SEVERITY: dict[str, str] = {
    "Schema Change": "high",
    "Resource Exhaustion": "medium",
}

ALLOWED_APPROVER_ROLES = {"ops_lead", "incident_commander"}

PENDING = "pending_approval"
AUTO_APPROVED = "auto_approved"
APPROVED = "approved"
REJECTED = "rejected"
_FINAL_DECISIONS = (APPROVED, REJECTED)


class RecommendationCategorizationError(Exception):
    """Raised when a recommendation's category has no known severity mapping."""


class ApprovalAuditError(Exception):
    """Raised when a recommendation submission or approval decision could not be
    written to the audit trail."""


class ApprovalNotFoundError(Exception):
    """Raised when a decision_id has no recommendation submitted under it."""


class ApprovalNotPendingError(Exception):
    """Raised when deciding a recommendation that was auto-approved and so was
    never pending a human decision."""


class ApprovalConflictError(Exception):
    """Raised when a decision_id already has a final decision that disagrees with
    the one being requested now. Reopening a finalized decision needs a new
    recommendation (a new decision_id), not a repeat call with a different answer."""


class UnauthorizedApprovalError(Exception):
    """Raised when the calling approver's role is not permitted to decide approvals."""


def severity_for_category(category: str) -> str:
    """Look up the severity for a log-based recommendation's category.

    Raises RecommendationCategorizationError for a category with no known
    mapping, rather than silently defaulting -- this is what makes "incorrect
    recommendation categorization" a typed, audited failure instead of a guess.
    """
    severity = CATEGORY_SEVERITY.get(category)
    if severity is None:
        raise RecommendationCategorizationError(
            f"No known severity mapping for recommendation category '{category}'"
        )
    return severity


@dataclass(frozen=True)
class ApprovalRecord:
    decision_id: str
    incident_id: str
    source: str
    category: str
    severity: str
    is_major: bool
    status: str
    decided_by: str | None = None


def submit_recommendation_for_approval(
    *,
    incident_id: str,
    source: str,
    category: str,
    severity: str,
    description: str,
    recommended_action: str,
    audit_log_path: str | Path = DEFAULT_AUDIT_LOG_PATH,
    investigation_correlation_id: str | None = None,
    decision_id: str | None = None,
) -> ApprovalRecord:
    """Submit one recommendation for approval: auto-approved if minor, pending if major.

    decision_id is this recommendation's own audit key -- pass a stable one to
    make a retried submission idempotent; a fresh one is generated when omitted.
    Raises ApprovalAuditError if the submission cannot be written to the audit trail.
    """
    decision_id = decision_id or str(uuid.uuid4())
    is_major = severity in MAJOR_SEVERITIES
    status = PENDING if is_major else AUTO_APPROVED

    try:
        record_activity(
            audit_log_path,
            correlation_id=decision_id,
            incident_id=incident_id,
            activity="recommendation_submitted",
            outcome=status,
            details={
                "source": source,
                "category": category,
                "severity": severity,
                "description": description,
                "recommended_action": recommended_action,
                "investigation_correlation_id": investigation_correlation_id,
            },
        )
    except AuditLoggingError as exc:
        raise ApprovalAuditError(f"Could not record submission for decision '{decision_id}': {exc}") from exc

    return ApprovalRecord(
        decision_id=decision_id,
        incident_id=incident_id,
        source=source,
        category=category,
        severity=severity,
        is_major=is_major,
        status=status,
        decided_by=None if is_major else "system",
    )


def submit_investigation_recommendation(
    investigation: InvestigationResult,
    *,
    audit_log_path: str | Path = DEFAULT_AUDIT_LOG_PATH,
    decision_id: str | None = None,
) -> ApprovalRecord | None:
    """Submit a log-analysis investigation's recommendation for approval, if it has one.

    Returns None when the investigation found no recommendation (STORY-001's
    "no common pattern matched" case) -- there is nothing to route for approval.
    Raises RecommendationCategorizationError if the recommendation's category has
    no known severity mapping.
    """
    recommendation = investigation.recommendation
    if recommendation is None:
        return None

    severity = severity_for_category(recommendation.category)

    return submit_recommendation_for_approval(
        incident_id=investigation.incident_id,
        source="log_analysis",
        category=recommendation.category,
        severity=severity,
        description=recommendation.root_cause,
        recommended_action=recommendation.recommended_action,
        audit_log_path=audit_log_path,
        investigation_correlation_id=investigation.correlation_id,
        decision_id=decision_id,
    )


def get_approval(decision_id: str, *, audit_log_path: str | Path = DEFAULT_AUDIT_LOG_PATH) -> ApprovalRecord:
    """Reconstruct one recommendation's current approval state from the audit trail."""
    submitted = None
    decided = None
    for entry in verify_log_integrity(audit_log_path):
        if entry.correlation_id != decision_id:
            continue
        if entry.activity == "recommendation_submitted":
            submitted = entry
        elif entry.activity == "approval_decision":
            decided = entry

    if submitted is None:
        raise ApprovalNotFoundError(f"No recommendation was submitted under decision_id '{decision_id}'")

    details = submitted.details
    status = decided.outcome if decided else submitted.outcome
    if decided:
        decided_by = decided.details.get("approver")
    elif submitted.outcome == AUTO_APPROVED:
        decided_by = "system"
    else:
        decided_by = None

    return ApprovalRecord(
        decision_id=decision_id,
        incident_id=submitted.incident_id,
        source=details["source"],
        category=details["category"],
        severity=details["severity"],
        is_major=submitted.outcome == PENDING,
        status=status,
        decided_by=decided_by,
    )


def decide_approval(
    decision_id: str,
    decision: str,
    *,
    approver: str,
    approver_role: str,
    audit_log_path: str | Path = DEFAULT_AUDIT_LOG_PATH,
) -> ApprovalRecord:
    """Record a human's approve/reject decision for one recommendation.

    Authorization is checked before anything else -- an approver_role outside
    ALLOWED_APPROVER_ROLES is rejected regardless of the recommendation's current
    state, and the attempt is itself audited (under its own correlation id, so it
    cannot occupy the audit slot a later legitimate decision needs).

    Idempotent when replayed with the same outcome by anyone; raises
    ApprovalConflictError if a different outcome is requested for a
    recommendation that was already finally decided.
    """
    if decision not in _FINAL_DECISIONS:
        raise ValueError(f"decision must be one of {_FINAL_DECISIONS}, got {decision!r}")

    current = get_approval(decision_id, audit_log_path=audit_log_path)

    if approver_role not in ALLOWED_APPROVER_ROLES:
        try:
            record_activity(
                audit_log_path,
                correlation_id=str(uuid.uuid4()),
                incident_id=current.incident_id,
                activity="approval_decision_denied",
                outcome="unauthorized",
                details={
                    "decision_id": decision_id,
                    "attempted_by": approver,
                    "attempted_role": approver_role,
                    "attempted_decision": decision,
                },
            )
        except AuditLoggingError as exc:
            raise ApprovalAuditError(
                f"Could not record denied approval attempt for decision '{decision_id}': {exc}"
            ) from exc
        raise UnauthorizedApprovalError(
            f"Role '{approver_role}' is not permitted to decide approvals (approver: '{approver}')"
        )

    if current.status == AUTO_APPROVED:
        raise ApprovalNotPendingError(
            f"Recommendation '{decision_id}' was auto-approved as minor and was never pending a human decision"
        )

    if current.status in _FINAL_DECISIONS:
        if current.status != decision:
            raise ApprovalConflictError(
                f"Recommendation '{decision_id}' was already decided as '{current.status}' "
                f"by '{current.decided_by}'; cannot now decide '{decision}' by '{approver}'"
            )
        return current  # idempotent replay of the same final decision

    try:
        record_activity(
            audit_log_path,
            correlation_id=decision_id,
            incident_id=current.incident_id,
            activity="approval_decision",
            outcome=decision,
            details={"approver": approver, "approver_role": approver_role},
        )
    except AuditLoggingError as exc:
        raise ApprovalAuditError(f"Could not record decision for decision '{decision_id}': {exc}") from exc

    return ApprovalRecord(
        decision_id=decision_id,
        incident_id=current.incident_id,
        source=current.source,
        category=current.category,
        severity=current.severity,
        is_major=True,
        status=decision,
        decided_by=approver,
    )
