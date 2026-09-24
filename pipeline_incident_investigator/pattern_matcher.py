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


# STORY-009 follow-up 1: plain-text wordings learned from pilot/pattern_fix_spec.json, which was
# committed before the round-2 held-out cases were written. Keep these tuples identical to that
# file -- test_pattern_matcher checks they match it exactly, so nothing off-list slips in.
FOLLOW_UP_WORDINGS: dict[str, tuple[str, ...]] = {
    "Resource Exhaustion": (
        "OOMKilled", "exit code 137", "Java heap space", "memory limit exceeded",
        "No space left on device", "ENOSPC", "disk quota exceeded",
    ),
    "Schema Change": (
        "invalid identifier", "Unrecognized name", "Unknown column", "Invalid column name", "no such column",
    ),
}


def _matcher(base_patterns: list[str], category: str) -> re.Pattern[str]:
    alternatives = base_patterns + [re.escape(w) for w in FOLLOW_UP_WORDINGS[category]]
    return re.compile("|".join(alternatives), re.IGNORECASE)


KNOWN_PATTERNS: tuple[LogPattern, ...] = (
    LogPattern(
        id="schema_mismatch",
        category="Schema Change",
        description="A query references a column that no longer exists in the source schema.",
        # `column "x" does not exist` is Postgres's wording (added after the STORY-009 baseline pilot).
        matcher=_matcher(
            [r"AnalysisException", r"Cannot resolve column", r"column \"?[\w.]+\"? does not exist"], "Schema Change"
        ),
    ),
    LogPattern(
        id="resource_exhaustion",
        category="Resource Exhaustion",
        description="An executor ran out of memory or another resource limit was exceeded.",
        # STORY-009 baseline pilot: "exceeding memory limits" is YARN's wording, and a bare OOM
        # must not match inside a dotted config key such as memory.oom.kill_disable.
        matcher=_matcher(
            [r"OutOfMemory", r"(?<![\w.])OOM(?![\w.])", r"ExecutorLostFailure", r"exceeding memory limits"],
            "Resource Exhaustion",
        ),
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
