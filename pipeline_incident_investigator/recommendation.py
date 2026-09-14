"""Generates a corrective-action recommendation from matched log patterns (REQ-005)."""

from __future__ import annotations

from dataclasses import dataclass

from pipeline_incident_investigator.pattern_matcher import MatchedPattern

RECOMMENDED_ACTIONS: dict[str, str] = {
    "schema_mismatch": (
        "Update the transformation to use the renamed/current column, validate "
        "downstream compatibility, then rerun the failed stage."
    ),
    "resource_exhaustion": (
        "Increase executor memory or reduce the shuffle/join size for this stage, "
        "clear any partially-written output, then rerun the failed stage."
    ),
}


class RecommendationGenerationError(Exception):
    """Raised when a matched pattern has no known corrective action to recommend."""


@dataclass(frozen=True)
class Recommendation:
    pattern_id: str
    category: str
    root_cause: str
    recommended_action: str
    evidence: list[str]


def generate_recommendation(matches: list[MatchedPattern]) -> Recommendation | None:
    """Return a recommendation for the strongest matched pattern, or None if none matched."""
    if not matches:
        return None

    top_match = matches[0]
    action = RECOMMENDED_ACTIONS.get(top_match.id)
    if action is None:
        raise RecommendationGenerationError(
            f"No recommended action configured for matched pattern '{top_match.id}'"
        )

    return Recommendation(
        pattern_id=top_match.id,
        category=top_match.category,
        root_cause=top_match.description,
        recommended_action=action,
        evidence=top_match.evidence,
    )
