"""Pilot test: run real investigations over labeled cases, measure errors and time, audit it all.

Satisfies STORY-009: a successful pilot with low error rates before autonomous
operation (REQ-012), and investigation time within the 1-hour target (REQ-009).

The cases and their correct verdicts live in pilot/expected.json, committed
before this runner existed so the answers could not be tuned to the results.
A verdict is the root-cause category the system asserts (from the log-analysis
agent's recommendation) or "uncertain" when it asserts none and escalates.

For each case the runner times the full path a person waits on -- all three
specialist agents (STORY-010) plus the detailed report (STORY-008) -- and
compares the verdict with the expected one. A case that crashes is recorded as
an error for that case; it never aborts the rest of the pilot. The pilot passes
only if the error rate is at or under the threshold AND every case finishes
within the time budget.

What "investigation time" means here: automated machine time from start to a
ready report. Human approval time is not included, and the 4-hour baseline is
the requirement's figure, not a measurement.

Access reuses the report roles (ALLOWED_REPORT_ROLES): the pilot generates
reports under the operator's own role, so a role that may not view reports may
not run the pilot either. Denials are audited.

Idempotency: every audit key derives from run_id, including each case's
investigation correlation id. Replaying a run with the same run_id re-measures
but writes no duplicate audit entries -- the first record stands.
"""

from __future__ import annotations

import json
import statistics
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Callable

from pipeline_incident_investigator.agent_coordinator import (
    CoordinationAuditError,
    CoordinationInitiationError,
    coordinate_agents,
)
from pipeline_incident_investigator.audit_log import AuditLoggingError, record_activity
from pipeline_incident_investigator.investigation_report import (
    ALLOWED_REPORT_ROLES,
    ReportAuditError,
    generate_report,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_AUDIT_LOG_PATH = Path(__file__).resolve().parent / "audit_trail.jsonl"
UNCERTAIN = "uncertain"
ERROR = "error"


class PilotConfigError(Exception):
    """Raised when the expected-verdicts file is missing or malformed."""


class UnauthorizedPilotAccessError(Exception):
    """Raised when the operator's role may not run the pilot."""


class PilotAuditError(Exception):
    """Raised when a pilot result, investigation, or denial could not be audited.
    Unaudited pilot results are never returned."""


@dataclass(frozen=True)
class CaseResult:
    path: str
    synthetic: bool
    expected: str
    verdict: str  # a category, "uncertain", or "error" (the case crashed)
    correct: bool
    duration_seconds: float
    within_budget: bool
    investigation_id: str  # not "investigation_correlation_id": that key would pull this entry into the report
    error_class: str | None = None


@dataclass(frozen=True)
class PilotResult:
    run_id: str
    operator: str
    total: int
    errors: int
    error_rate: float
    error_rate_threshold: float
    time_budget_seconds: float
    max_seconds: float
    median_seconds: float
    all_within_budget: bool
    passed: bool
    cases: list[CaseResult] = field(default_factory=list)


def run_pilot(
    expected_path: str | Path,
    *,
    operator: str,
    operator_role: str,
    audit_log_path: str | Path = DEFAULT_AUDIT_LOG_PATH,
    run_id: str | None = None,
    base_dir: str | Path = REPO_ROOT,
    clock: Callable[[], float] = time.perf_counter,
) -> PilotResult:
    """Run every case in expected_path and return the audited pilot result.

    Raises UnauthorizedPilotAccessError, PilotConfigError, or PilotAuditError.
    """
    run_id = run_id or str(uuid.uuid4())
    if operator_role not in ALLOWED_REPORT_ROLES:
        _audit(audit_log_path, correlation_id=str(uuid.uuid4()), incident_id=f"pilot:{run_id}",
               activity="pilot_access_denied", outcome="unauthorized",
               details={"run_id": run_id, "attempted_by": operator, "attempted_role": operator_role})
        raise UnauthorizedPilotAccessError(
            f"Role '{operator_role}' is not permitted to run the pilot (operator: '{operator}')"
        )

    config = _load_expected(expected_path)
    cases = [
        _run_case(case, run_id=run_id, operator=operator, operator_role=operator_role,
                  budget=config["time_budget_seconds"], audit_log_path=audit_log_path,
                  base_dir=Path(base_dir), clock=clock)
        for case in config["cases"]
    ]

    errors = sum(not c.correct for c in cases)
    durations = [c.duration_seconds for c in cases]
    result = PilotResult(
        run_id=run_id,
        operator=operator,
        total=len(cases),
        errors=errors,
        error_rate=errors / len(cases),
        error_rate_threshold=config["error_rate_threshold"],
        time_budget_seconds=config["time_budget_seconds"],
        max_seconds=max(durations),
        median_seconds=statistics.median(durations),
        all_within_budget=all(c.within_budget for c in cases),
        passed=errors / len(cases) <= config["error_rate_threshold"] and all(c.within_budget for c in cases),
        cases=cases,
    )

    summary = {k: v for k, v in asdict(result).items() if k != "cases"}
    _audit(audit_log_path, correlation_id=run_id, incident_id=f"pilot:{run_id}",
           activity="pilot_completed", outcome="passed" if result.passed else "failed", details=summary)
    return result


def _run_case(case: dict, *, run_id: str, operator: str, operator_role: str, budget: float,
              audit_log_path: str | Path, base_dir: Path, clock: Callable[[], float]) -> CaseResult:
    correlation_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"pilot:{run_id}:{case['path']}"))
    verdict, error_class = ERROR, None

    start = clock()
    try:
        coordination = coordinate_agents(base_dir / case["path"], audit_log_path=audit_log_path,
                                         correlation_id=correlation_id)
        generate_report(correlation_id, viewer=operator, viewer_role=operator_role, audit_log_path=audit_log_path)
        verdict, error_class = _verdict(coordination)
    except (CoordinationInitiationError, CoordinationAuditError, ReportAuditError) as exc:
        raise PilotAuditError(f"Audit failed during pilot case '{case['path']}': {exc}") from exc
    except Exception as exc:  # noqa: BLE001 -- a pilot records any crash as that case's error and keeps going
        error_class = type(exc).__name__
    duration = clock() - start

    result = CaseResult(
        path=case["path"],
        synthetic=bool(case.get("synthetic")),
        expected=case["expected"],
        verdict=verdict,
        correct=verdict == case["expected"],
        duration_seconds=round(duration, 6),
        within_budget=duration <= budget,
        investigation_id=correlation_id,
        error_class=error_class,
    )
    # Keyed apart from the investigation's own id: otherwise this entry becomes part of that
    # investigation's report, the report's content changes, and a replay logs a second report.
    case_audit_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"pilot-case:{run_id}:{case['path']}"))
    _audit(audit_log_path, correlation_id=case_audit_id, incident_id=case["path"], activity="pilot_case",
           outcome="correct" if result.correct else "wrong", details={"run_id": run_id, **asdict(result)})
    return result


def _verdict(coordination) -> tuple[str, str | None]:
    """The log-analysis agent's asserted category, "uncertain", or "error" if that agent failed."""
    log_outcome = next(o for o in coordination.agent_outcomes if o.agent == "log_analysis")
    if log_outcome.status != "succeeded":
        return ERROR, log_outcome.error_class
    recommendation = log_outcome.result.recommendation
    return (recommendation.category if recommendation else UNCERTAIN), None


def _load_expected(expected_path: str | Path) -> dict:
    try:
        config = json.loads(Path(expected_path).read_text(encoding="utf-8"))
        threshold = float(config["error_rate_threshold"])
        budget = float(config["time_budget_seconds"])
        cases = config["cases"]
        if not cases or not all("path" in c and "expected" in c for c in cases):
            raise ValueError("every case needs 'path' and 'expected', and there must be at least one")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise PilotConfigError(f"Invalid pilot definition at {expected_path}: {exc}") from exc
    return {"error_rate_threshold": threshold, "time_budget_seconds": budget, "cases": cases}


def _audit(audit_log_path: str | Path, **kwargs) -> None:
    try:
        record_activity(audit_log_path, **kwargs)
    except AuditLoggingError as exc:
        raise PilotAuditError(f"Could not record {kwargs['activity']} to the audit trail: {exc}") from exc
