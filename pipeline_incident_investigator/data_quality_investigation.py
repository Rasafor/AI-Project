"""End-to-end data-quality analysis for a pipeline incident, with an audit trail.

Satisfies STORY-004: analyze an incident's data-quality metrics to help
identify root causes (REQ-004), audited the same way STORY-001 and STORY-003
already are, reusing STORY-002's hash-chained audit trail unchanged.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from pipeline_incident_investigator.audit_log import record_activity
from pipeline_incident_investigator.data_quality_analyzer import DataQualityIssue, analyze_data_quality
from pipeline_incident_investigator.data_quality_source import (
    DataQualityInfoMissingError,
    DataQualitySourceUnavailableError,
    load_incident_data_quality,
)

DEFAULT_AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_trail.jsonl"


@dataclass(frozen=True)
class DataQualityInvestigationResult:
    correlation_id: str
    incident_id: str
    issues: list[DataQualityIssue]


def investigate_data_quality(
    incident_path: str | Path,
    *,
    audit_log_path: str | Path = DEFAULT_AUDIT_LOG_PATH,
    correlation_id: str | None = None,
) -> DataQualityInvestigationResult:
    """Analyze one incident's data-quality metrics, auditing the result.

    Raises DataQualitySourceUnavailableError or DataQualityInfoMissingError on
    failure -- both are audited before being re-raised, so the trail covers
    unsuccessful runs too.
    """
    correlation_id = correlation_id or str(uuid.uuid4())
    incident_id = str(incident_path)

    try:
        data_quality = load_incident_data_quality(incident_path)
        incident_id = data_quality.get("incident_id") or incident_id
    except (DataQualitySourceUnavailableError, DataQualityInfoMissingError) as exc:
        record_activity(
            audit_log_path,
            correlation_id=correlation_id,
            incident_id=incident_id,
            activity="data_quality_analysis",
            outcome="failure",
            details={"error_class": type(exc).__name__, "error": str(exc)},
        )
        raise

    issues = analyze_data_quality(data_quality["metrics"])

    record_activity(
        audit_log_path,
        correlation_id=correlation_id,
        incident_id=incident_id,
        activity="data_quality_analysis",
        outcome="issues_found" if issues else "no_issues",
        details={"issue_ids": [issue.id for issue in issues]},
    )

    return DataQualityInvestigationResult(
        correlation_id=correlation_id,
        incident_id=incident_id,
        issues=issues,
    )
