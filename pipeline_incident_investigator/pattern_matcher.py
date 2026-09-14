"""Classifies pipeline incident log lines into known failure patterns (REQ-001)."""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LogPattern:
    id: str
    category: str
    description: str
    matcher: re.Pattern[str]


@dataclass(frozen=True)
class MatchedPattern:
    id: str
    category: str
    description: str
    evidence: list[str]


KNOWN_PATTERNS: tuple[LogPattern, ...] = (
    LogPattern(
        id="schema_mismatch",
        category="Schema Change",
        description="A query references a column that no longer exists in the source schema.",
        matcher=re.compile(r"AnalysisException|Cannot resolve column", re.IGNORECASE),
    ),
    LogPattern(
        id="resource_exhaustion",
        category="Resource Exhaustion",
        description="An executor ran out of memory or another resource limit was exceeded.",
        matcher=re.compile(r"OutOfMemory|\bOOM\b|ExecutorLostFailure", re.IGNORECASE),
    ),
)


def match_patterns(log_lines: list[str]) -> list[MatchedPattern]:
    """Return every known pattern with at least one matching log line, most-evidence first."""
    matches: list[MatchedPattern] = []
    for pattern in KNOWN_PATTERNS:
        evidence = [line for line in log_lines if pattern.matcher.search(line)]
        if evidence:
            matches.append(
                MatchedPattern(pattern.id, pattern.category, pattern.description, evidence)
            )
    return sorted(matches, key=lambda m: len(m.evidence), reverse=True)
