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


# STORY-009 follow-up 2: general wordings from pilot/context_fix_spec.json (regex, not plain text).
CONTEXT_WORDINGS: dict[str, tuple[str, ...]] = {
    "Resource Exhaustion": (r"\bOut of memory\b", r"\bquota\b.{0,80}\bexceeded\b"),
    "Schema Change": (),
}


# STORY-009 follow-up 3: wordings from pilot/followup3_changes.json. Unlike the two lists above,
# these were added AFTER seeing every pilot case, so pilot cases passing because of them is not
# independent evidence.
SEEN_CASE_WORDINGS: dict[str, tuple[str, ...]] = {
    "Resource Exhaustion": (r"\blow on resource: memory\b",),
    "Schema Change": (r'column \\?"?[\w.]+\\?"? does not exist',),
}


def _matcher(base_patterns: list[str], category: str) -> re.Pattern[str]:
    alternatives = (
        base_patterns
        + [re.escape(w) for w in FOLLOW_UP_WORDINGS[category]]
        + list(CONTEXT_WORDINGS[category])
        + list(SEEN_CASE_WORDINGS[category])
    )
    return re.compile("|".join(alternatives), re.IGNORECASE)


# STORY-009 follow-up 2 context rule (pilot/context_fix_spec.json): only lines that show something
# going wrong count as evidence. Levels are matched uppercase, exactly as the committed plan says.
_LEVEL = re.compile(r"\b(INFO|WARN|WARNING|ERROR|FATAL)\b")
# Follow-up 3: a logfmt level field (level=error) wins over bare words, case-insensitively.
_LOGFMT_LEVEL = re.compile(r"\blevel=(info|warn|warning|error|fatal)\b", re.IGNORECASE)
_WARN_KILL = re.compile(r"\b(killed|terminated|lost|exited|evicted)\b|ExecutorLostFailure|OOMKilled", re.IGNORECASE)


def line_level(line: str) -> str:
    """The line's log level: a logfmt level=... field if present, else the first whole-word
    uppercase INFO/WARN/WARNING/ERROR/FATAL, else INFO."""
    found = _LOGFMT_LEVEL.search(line)
    if found:
        return found.group(1).upper()
    found = _LEVEL.search(line)
    return found.group(1) if found else "INFO"


def counts_as_evidence(line: str) -> bool:
    """ERROR/FATAL always; WARN only when it reports something killed/terminated/lost/exited/evicted; INFO never."""
    level = line_level(line)
    if level in ("ERROR", "FATAL"):
        return True
    if level in ("WARN", "WARNING"):
        return bool(_WARN_KILL.search(line))
    return False


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
    """Return every known pattern with at least one matching evidence line, most-evidence first.

    Only lines that pass counts_as_evidence() are considered (STORY-009 follow-up 2), so a keyword
    on an INFO line or a non-fatal warning cannot decide the root cause.
    """
    candidate_lines = [line for line in log_lines if counts_as_evidence(line)]
    matches: list[MatchedPattern] = []
    for pattern in KNOWN_PATTERNS:
        evidence = [line for line in candidate_lines if pattern.matcher.search(line)]
        if evidence:
            matches.append(
                MatchedPattern(pattern.id, pattern.category, pattern.description, evidence)
            )
    return sorted(matches, key=lambda m: len(m.evidence), reverse=True)
