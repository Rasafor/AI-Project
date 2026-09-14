"""End-to-end investigation: log analysis to recommendation, with an audit trail.

Satisfies STORY-001: analyze an incident's logs (REQ-001), recommend a
corrective action for human approval (REQ-005), and log every investigation
activity for audit (REQ-011).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from pipeline_incident_investigator.audit_log import record_activity
from pipeline_incident_investigator.log_source import (
    LogsIncompleteError,
    LogsUnavailableError,
    load_incident,
    load_incident_logs,
)
from pipeline_incident_investigator.pattern_matcher import match_patterns
from pipeline_incident_investigator.recommendation import (
    Recommendation,
    RecommendationGenerationError,
    generate_recommendation,
)

DEFAULT_AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_trail.jsonl"


@dataclass(frozen=True)
class InvestigationResult:
    correlation_id: str
    incident_id: str
    recommendation: Recommendation | None


def investigate(
    incident_path: str | Path,
    *,
    audit_log_path: str | Path = DEFAULT_AUDIT_LOG_PATH,
    correlation_id: str | None = None,
) -> InvestigationResult:
    """Analyze one incident's logs and produce a recommendation, auditing every step.

    Raises LogsUnavailableError, LogsIncompleteError, or
    RecommendationGenerationError on failure -- each failure is audited before
    it is re-raised, so the trail covers unsuccessful investigations too.
    """
    correlation_id = correlation_id or str(uuid.uuid4())
    incident_id = str(incident_path)

    try:
        incident = load_incident(incident_path)
        incident_id = incident.get("incident_id", incident_id)
        logs = load_incident_logs(incident_path)
    except (LogsUnavailableError, LogsIncompleteError) as exc:
        record_activity(
            audit_log_path,
            correlation_id=correlation_id,
            incident_id=incident_id,
            activity="log_analysis",
            outcome="failure",
            details={"error_class": type(exc).__name__, "error": str(exc)},
        )
        raise

    matches = match_patterns(logs)
    record_activity(
        audit_log_path,
        correlation_id=correlation_id,
        incident_id=incident_id,
        activity="log_analysis",
        outcome="success",
        details={"patterns_matched": [m.id for m in matches]},
    )

    try:
        recommendation = generate_recommendation(matches)
    except RecommendationGenerationError as exc:
        record_activity(
            audit_log_path,
            correlation_id=correlation_id,
            incident_id=incident_id,
            activity="recommendation",
            outcome="failure",
            details={"error_class": type(exc).__name__, "error": str(exc)},
        )
        raise

    record_activity(
        audit_log_path,
        correlation_id=correlation_id,
        incident_id=incident_id,
        activity="recommendation",
        outcome="success" if recommendation else "no_recommendation",
        details={"pattern_id": recommendation.pattern_id} if recommendation else {},
    )

    return InvestigationResult(
        correlation_id=correlation_id,
        incident_id=incident_id,
        recommendation=recommendation,
    )
