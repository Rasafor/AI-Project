"""End-to-end SQL analysis for a pipeline incident, with an audit trail.

Satisfies STORY-003: analyze the SQL involved in an incident (REQ-003) and
record the result for audit, reusing the same tamper-evident audit trail
STORY-002 hardened rather than building a second one.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from pipeline_incident_investigator.audit_log import record_activity
from pipeline_incident_investigator.sql_analyzer import SqlIssue, analyze_query
from pipeline_incident_investigator.sql_source import (
    SqlInfoMissingError,
    SqlSourceUnavailableError,
    load_incident_sql,
)

DEFAULT_AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_trail.jsonl"


@dataclass(frozen=True)
class SqlInvestigationResult:
    correlation_id: str
    incident_id: str
    issues: list[SqlIssue]


def investigate_sql(
    incident_path: str | Path,
    *,
    audit_log_path: str | Path = DEFAULT_AUDIT_LOG_PATH,
    correlation_id: str | None = None,
) -> SqlInvestigationResult:
    """Analyze one incident's SQL query for known issues, auditing the result.

    Raises SqlSourceUnavailableError or SqlInfoMissingError on failure -- both
    are audited before being re-raised, so the trail covers unsuccessful runs too.
    """
    correlation_id = correlation_id or str(uuid.uuid4())
    incident_id = str(incident_path)

    try:
        sql = load_incident_sql(incident_path)
        incident_id = sql.get("incident_id") or incident_id
    except (SqlSourceUnavailableError, SqlInfoMissingError) as exc:
        record_activity(
            audit_log_path,
            correlation_id=correlation_id,
            incident_id=incident_id,
            activity="sql_analysis",
            outcome="failure",
            details={"error_class": type(exc).__name__, "error": str(exc)},
        )
        raise

    issues = analyze_query(sql["query"], sql["current_schema_columns"])

    record_activity(
        audit_log_path,
        correlation_id=correlation_id,
        incident_id=incident_id,
        activity="sql_analysis",
        outcome="issues_found" if issues else "no_issues",
        details={"issue_ids": [issue.id for issue in issues]},
    )

    return SqlInvestigationResult(
        correlation_id=correlation_id,
        incident_id=incident_id,
        issues=issues,
    )
