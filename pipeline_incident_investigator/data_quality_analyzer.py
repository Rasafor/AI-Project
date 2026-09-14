"""Analyzes data-quality metrics for known issue patterns (REQ-004).

'Incorrect root cause identification' (a listed failure path for this story)
is a correctness concern, not a runtime failure -- addressed by testing each
check against real fixture metrics with a known answer, not by a guard here.
"""

from __future__ import annotations

from dataclasses import dataclass

LAYER_ROW_COUNT_KEYS = ("source_row_count", "bronze_row_count", "silver_row_count", "gold_row_count_actual")
ROW_COUNT_SHORTFALL_THRESHOLD = 0.9
NULL_RATE_THRESHOLD = 0.01
DUPLICATE_RATE_THRESHOLD = 0.001


@dataclass(frozen=True)
class DataQualityIssue:
    id: str
    severity: str
    description: str
    evidence: str


def _reference_row_count(metrics: dict) -> float | None:
    """A denominator to compute null/duplicate rates against: the first positive,
    present row count among bronze, source, or silver, in that order of preference."""
    for key in ("bronze_row_count", "source_row_count", "silver_row_count"):
        value = metrics.get(key)
        if isinstance(value, (int, float)) and value > 0:
            return value
    return None


def _row_count_shortfall(metrics: dict) -> list[DataQualityIssue]:
    present = [
        (key, metrics[key]) for key in LAYER_ROW_COUNT_KEYS if isinstance(metrics.get(key), (int, float))
    ]

    issues = []
    for (upstream_key, upstream_count), (downstream_key, downstream_count) in zip(present, present[1:]):
        if upstream_count > 0 and downstream_count < ROW_COUNT_SHORTFALL_THRESHOLD * upstream_count:
            issues.append(
                DataQualityIssue(
                    id="row_count_shortfall",
                    severity="high",
                    description=(
                        f"{downstream_key} ({downstream_count}) is well below {upstream_key} "
                        f"({upstream_count}), suggesting rows were lost or never processed "
                        "between these two stages."
                    ),
                    evidence=f"{upstream_key}={upstream_count}, {downstream_key}={downstream_count}",
                )
            )
    return issues


def _null_rate_high(metrics: dict) -> list[DataQualityIssue]:
    total = _reference_row_count(metrics)
    if not total:
        return []

    issues = []
    for key, value in metrics.items():
        if key.startswith("null_") and key.endswith("_count") and isinstance(value, (int, float)):
            rate = value / total
            if rate > NULL_RATE_THRESHOLD:
                issues.append(
                    DataQualityIssue(
                        id="null_rate_high",
                        severity="high",
                        description=(
                            f"{key} is {value} out of {total} rows ({rate:.1%}), above the "
                            f"{NULL_RATE_THRESHOLD:.0%} threshold."
                        ),
                        evidence=f"{key}={value}, reference_row_count={total}",
                    )
                )
    return issues


def _duplicate_rate_high(metrics: dict) -> list[DataQualityIssue]:
    total = _reference_row_count(metrics)
    if not total:
        return []

    issues = []
    for key, value in metrics.items():
        if key.startswith("duplicate_") and key.endswith("_count") and isinstance(value, (int, float)):
            rate = value / total
            if rate > DUPLICATE_RATE_THRESHOLD:
                issues.append(
                    DataQualityIssue(
                        id="duplicate_rate_high",
                        severity="medium",
                        description=(
                            f"{key} is {value} out of {total} rows ({rate:.2%}), above the "
                            f"{DUPLICATE_RATE_THRESHOLD:.1%} threshold."
                        ),
                        evidence=f"{key}={value}, reference_row_count={total}",
                    )
                )
    return issues


def _schema_drift(metrics: dict) -> list[DataQualityIssue]:
    unexpected = metrics.get("unexpected_columns") or []
    missing = metrics.get("missing_expected_columns") or []
    if not unexpected and not missing:
        return []

    return [
        DataQualityIssue(
            id="schema_drift",
            severity="high",
            description=(
                "The observed schema does not match what was expected: "
                f"unexpected columns {unexpected}, missing columns {missing}."
            ),
            evidence=f"unexpected_columns={unexpected}, missing_expected_columns={missing}",
        )
    ]


def _freshness_violation(metrics: dict) -> list[DataQualityIssue]:
    actual = metrics.get("freshness_hours_actual")
    expected = metrics.get("freshness_hours_expected")
    if not isinstance(actual, (int, float)) or not isinstance(expected, (int, float)):
        return []
    if actual <= expected:
        return []

    return [
        DataQualityIssue(
            id="freshness_violation",
            severity="medium",
            description=f"Data is {actual}h old, exceeding the {expected}h freshness target.",
            evidence=f"freshness_hours_actual={actual}, freshness_hours_expected={expected}",
        )
    ]


_CHECKS = (
    _row_count_shortfall,
    _null_rate_high,
    _duplicate_rate_high,
    _schema_drift,
    _freshness_violation,
)


def analyze_data_quality(metrics: dict) -> list[DataQualityIssue]:
    """Return every data-quality issue found in these metrics, or [] if none apply."""
    issues: list[DataQualityIssue] = []
    for check in _CHECKS:
        issues.extend(check(metrics))
    return issues
