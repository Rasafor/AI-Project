"""Notification system for uncertain root causes, with an audit trail.

Satisfies STORY-006: flag an investigation whose root cause is uncertain and
notify a human to review it (REQ-006).

"Uncertain root cause" is anchored to the same fork STORY-001's investigate()
already makes: it either matches a known failure pattern and returns a
Recommendation (a "certain" root cause -- STORY-005 routes that to approval),
or it finds no known pattern and returns recommendation=None. Recommendation
is the only place "root cause" is used anywhere in this codebase, so that is
the signal this module keys off, not SQL/data-quality issue counts.

Each delivery *attempt* is audited under its own fresh correlation id, not a
single id per investigation. This is deliberate, not an oversight: unlike an
approval decision (which is final once made), a notification can legitimately
move from "failed" to "sent" across separate calls -- if attempts were keyed
by the investigation's own correlation_id, record_activity's
(correlation_id, activity) dedup would freeze the audit trail at "failed"
forever, even after a real, successful retry, which would violate this
project's idempotency rule the other way (silently losing a real state
change instead of preventing a duplicate). To avoid resending after a
previous attempt already succeeded, notify_if_uncertain first scans for the
latest recorded attempt for this investigation and short-circuits if it was
already "sent".

Known gap: that scan-then-write is not atomic. Two truly concurrent calls for
the same investigation could both see "not yet sent" and both send. This
walking skeleton has no locking around the audit trail (the same class of gap
STORY-002 already documents for tamper-truncation) -- fine for a single
investigator process working incidents one at a time, not fine for a
concurrent worker pool without more.

Authorization here is a small allow-list, not the full role-based access
control REQ-018 describes -- that requirement is not yet fulfilled by any
story. This is enough to make "unauthorized access to notifications" a real,
audited failure path now, mirroring approval_workflow.decide_approval exactly.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from pipeline_incident_investigator.audit_log import AuditLoggingError, record_activity, verify_log_integrity
from pipeline_incident_investigator.investigator import InvestigationResult

DEFAULT_AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_trail.jsonl"

ALLOWED_VIEWER_ROLES = {"data_engineer", "ops_lead", "incident_commander"}

SENT = "sent"
FAILED = "failed"


class NotificationChannelError(Exception):
    """Raised by a send_fn implementation when one delivery attempt could not
    reach the notification channel (e.g. an ops-tool integration erroring or
    timing out)."""


class NotificationDeliveryError(Exception):
    """Raised when every retry attempt to send a notification failed.

    Carries the computed NotificationRecord (status="failed") on .record, so
    the fact that an uncertain case was detected and audited is not lost even
    though delivery itself failed.
    """

    def __init__(self, message: str, record: "NotificationRecord") -> None:
        super().__init__(message)
        self.record = record


class NotificationAuditError(Exception):
    """Raised when a notification, or a denied access attempt, could not be
    written to the audit trail."""


class NotificationNotFoundError(Exception):
    """Raised when no notification has been recorded for the given investigation."""


class UnauthorizedNotificationAccessError(Exception):
    """Raised when the viewer's role is not permitted to view notifications."""


@dataclass(frozen=True)
class NotificationRecord:
    incident_id: str
    investigation_correlation_id: str
    reason: str
    status: str  # "sent" | "failed"
    attempts: int


def _default_send(payload: dict, *, timeout: float) -> None:
    """Placeholder ops-tool integration (REQ-014).

    Stands in for a real Slack/PagerDuty/email call -- this project has no
    external notification credentials to integrate with. Always succeeds.
    Swap in a real client here without changing notify_if_uncertain's
    retry/audit logic; a real implementation would honor `timeout` on its
    outbound call.
    """
    return None


def _latest_notification(
    investigation_correlation_id: str, audit_log_path: str | Path
) -> NotificationRecord | None:
    """Reconstruct the most recent delivery attempt recorded for one investigation."""
    latest = None
    for entry in verify_log_integrity(audit_log_path):
        if entry.activity != "notification_sent":
            continue
        if entry.details.get("investigation_correlation_id") != investigation_correlation_id:
            continue
        latest = entry

    if latest is None:
        return None

    return NotificationRecord(
        incident_id=latest.incident_id,
        investigation_correlation_id=investigation_correlation_id,
        reason=latest.details["reason"],
        status=latest.outcome,
        attempts=latest.details["attempts"],
    )


def notify_if_uncertain(
    investigation: InvestigationResult,
    *,
    send_fn: Callable[..., None] = _default_send,
    max_attempts: int = 3,
    timeout_seconds: float = 5.0,
    audit_log_path: str | Path = DEFAULT_AUDIT_LOG_PATH,
) -> NotificationRecord | None:
    """Notify a human when an investigation's root cause is uncertain.

    Returns None (and logs nothing) when investigation.recommendation is not
    None -- the root cause is certain, so there is nothing to flag. Otherwise
    calls send_fn up to max_attempts times before giving up. Raises
    NotificationDeliveryError if every attempt fails, or NotificationAuditError
    if the outcome could not be written to the audit trail.
    """
    if investigation.recommendation is not None:
        return None

    already_sent = _latest_notification(investigation.correlation_id, audit_log_path)
    if already_sent is not None and already_sent.status == SENT:
        return already_sent  # do not resend -- idempotent retry

    reason = (
        "No known failure pattern matched this incident's logs; the root cause "
        "is uncertain and needs manual review."
    )
    payload = {"incident_id": investigation.incident_id, "reason": reason}

    status = FAILED
    attempts = 0
    last_error: NotificationChannelError | None = None
    for attempts in range(1, max_attempts + 1):
        try:
            send_fn(payload, timeout=timeout_seconds)
            status = SENT
            break
        except NotificationChannelError as exc:
            last_error = exc

    try:
        record_activity(
            audit_log_path,
            correlation_id=str(uuid.uuid4()),
            incident_id=investigation.incident_id,
            activity="notification_sent",
            outcome=status,
            details={
                "reason": reason,
                "attempts": attempts,
                "investigation_correlation_id": investigation.correlation_id,
            },
        )
    except AuditLoggingError as exc:
        raise NotificationAuditError(
            f"Could not record notification for investigation '{investigation.correlation_id}': {exc}"
        ) from exc

    record = NotificationRecord(
        incident_id=investigation.incident_id,
        investigation_correlation_id=investigation.correlation_id,
        reason=reason,
        status=status,
        attempts=attempts,
    )

    if status == FAILED:
        raise NotificationDeliveryError(
            f"Could not deliver notification for incident '{investigation.incident_id}' "
            f"after {attempts} attempt(s)",
            record=record,
        ) from last_error

    return record


def get_notification(
    investigation_correlation_id: str,
    *,
    viewer: str,
    viewer_role: str,
    audit_log_path: str | Path = DEFAULT_AUDIT_LOG_PATH,
) -> NotificationRecord:
    """Look up the current notification state for one investigation.

    Authorization is checked before anything is looked up -- an unauthorized
    viewer learns nothing about whether a notification exists, and the denied
    attempt is audited under its own correlation id.
    """
    if viewer_role not in ALLOWED_VIEWER_ROLES:
        try:
            record_activity(
                audit_log_path,
                correlation_id=str(uuid.uuid4()),
                incident_id=investigation_correlation_id,
                activity="notification_access_denied",
                outcome="unauthorized",
                details={
                    "investigation_correlation_id": investigation_correlation_id,
                    "attempted_by": viewer,
                    "attempted_role": viewer_role,
                },
            )
        except AuditLoggingError as exc:
            raise NotificationAuditError(f"Could not record denied notification access: {exc}") from exc
        raise UnauthorizedNotificationAccessError(
            f"Role '{viewer_role}' is not permitted to view notifications (viewer: '{viewer}')"
        )

    record = _latest_notification(investigation_correlation_id, audit_log_path)
    if record is None:
        raise NotificationNotFoundError(
            f"No notification was recorded for investigation '{investigation_correlation_id}'"
        )
    return record
