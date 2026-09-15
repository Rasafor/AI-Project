"""Coordinate the specialized investigation agents for one incident, with an audit trail.

Satisfies STORY-010: run the log-analysis (STORY-001), SQL-analysis (STORY-003),
and data-quality-analysis (STORY-004) agents together against an incident's
pipeline dependencies (REQ-002), so a human gets one aggregated view instead of
invoking each agent by hand. Each agent's own failures are typed and already
audited internally by that agent -- the coordinator's job is to keep going when
one agent fails rather than abandon the others, and to record that the
coordination task itself ran.

Retries are external and idempotent, not internal: record_activity() already
dedups on (correlation_id, activity), for both this module's own audit entries
and each wrapped agent's. Re-calling coordinate_agents() with the same
correlation_id after a failure is safe -- already-recorded entries come back
unchanged instead of duplicating, and re-running a specialist's analysis is
side-effect-free.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from pipeline_incident_investigator.audit_log import AuditLoggingError, record_activity
from pipeline_incident_investigator.data_quality_investigation import (
    DataQualityInfoMissingError,
    DataQualitySourceUnavailableError,
    investigate_data_quality,
)
from pipeline_incident_investigator.investigator import (
    LogsIncompleteError,
    LogsUnavailableError,
    RecommendationGenerationError,
    investigate,
)
from pipeline_incident_investigator.sql_investigation import (
    SqlInfoMissingError,
    SqlSourceUnavailableError,
    investigate_sql,
)

DEFAULT_AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_trail.jsonl"


class CoordinationInitiationError(Exception):
    """Raised when agent coordination cannot even begin (its own audit write failed).

    Nothing has been dispatched to any agent yet, so no partial results exist to lose.
    """


class CoordinationAuditError(Exception):
    """Raised when the coordination summary could not be written to the audit trail.

    The analysis itself may have succeeded -- ``partial_result`` carries whatever
    was computed, so it is not silently discarded even though an unaudited
    coordination run is not returned as if it were trustworthy.
    """

    def __init__(self, message: str, partial_result: "CoordinationResult") -> None:
        super().__init__(message)
        self.partial_result = partial_result


@dataclass(frozen=True)
class AgentOutcome:
    agent: str
    status: str  # "succeeded" | "failed"
    result: Any = None
    error_class: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class CoordinationResult:
    correlation_id: str
    incident_id: str
    status: str  # "success" | "partial_failure" | "failure"
    agent_outcomes: list[AgentOutcome] = field(default_factory=list)


# Each entry: (agent name, entry-point function, exception types that function
# itself already typed and audited before re-raising).
_AGENT_SPECS: list[tuple[str, Callable[..., Any], tuple[type[Exception], ...]]] = [
    (
        "log_analysis",
        investigate,
        (LogsUnavailableError, LogsIncompleteError, RecommendationGenerationError),
    ),
    (
        "sql_analysis",
        investigate_sql,
        (SqlSourceUnavailableError, SqlInfoMissingError),
    ),
    (
        "data_quality_analysis",
        investigate_data_quality,
        (DataQualitySourceUnavailableError, DataQualityInfoMissingError),
    ),
]


def coordinate_agents(
    incident_path: str | Path,
    *,
    audit_log_path: str | Path = DEFAULT_AUDIT_LOG_PATH,
    correlation_id: str | None = None,
) -> CoordinationResult:
    """Run the log, SQL, and data-quality agents against one incident, auditing the run.

    One agent's typed failure does not stop the others -- the analysis is
    reported as "success", "partial_failure", or "failure" depending on how
    many of the three agents succeeded, rather than aborting at the first error.

    Raises CoordinationInitiationError if the initial audit write fails (before
    any agent runs), or CoordinationAuditError if the final summary audit write
    fails (after the agents have already run) -- the latter carries the computed
    results on its ``partial_result`` attribute.
    """
    correlation_id = correlation_id or str(uuid.uuid4())
    incident_id = str(incident_path)

    try:
        record_activity(
            audit_log_path,
            correlation_id=correlation_id,
            incident_id=incident_id,
            activity="coordination_initiated",
            outcome="started",
            details={"agents": [name for name, _, _ in _AGENT_SPECS]},
        )
    except AuditLoggingError as exc:
        raise CoordinationInitiationError(
            f"Could not initiate agent coordination for {incident_path}: {exc}"
        ) from exc

    agent_outcomes: list[AgentOutcome] = []

    for name, agent_fn, exception_types in _AGENT_SPECS:
        try:
            result = agent_fn(
                incident_path,
                audit_log_path=audit_log_path,
                correlation_id=correlation_id,
            )
        except exception_types as exc:
            agent_outcomes.append(
                AgentOutcome(
                    agent=name,
                    status="failed",
                    error_class=type(exc).__name__,
                    error=str(exc),
                )
            )
            continue

        incident_id = getattr(result, "incident_id", incident_id)
        agent_outcomes.append(AgentOutcome(agent=name, status="succeeded", result=result))

    succeeded_count = sum(1 for outcome in agent_outcomes if outcome.status == "succeeded")
    if succeeded_count == len(agent_outcomes):
        status = "success"
    elif succeeded_count == 0:
        status = "failure"
    else:
        status = "partial_failure"

    coordination_result = CoordinationResult(
        correlation_id=correlation_id,
        incident_id=incident_id,
        status=status,
        agent_outcomes=agent_outcomes,
    )

    try:
        record_activity(
            audit_log_path,
            correlation_id=correlation_id,
            incident_id=incident_id,
            activity="agent_coordination",
            outcome=status,
            details={
                "agent_outcomes": {
                    outcome.agent: outcome.status
                    if outcome.status == "succeeded"
                    else f"{outcome.status}:{outcome.error_class}"
                    for outcome in agent_outcomes
                }
            },
        )
    except AuditLoggingError as exc:
        raise CoordinationAuditError(
            f"Could not record agent coordination summary for {incident_path}: {exc}",
            partial_result=coordination_result,
        ) from exc

    return coordination_result
