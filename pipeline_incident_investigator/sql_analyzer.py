"""Analyzes a SQL query for known issue patterns (REQ-003).

'Incorrect issue identification' (a listed failure path for this story) is a
correctness concern, not a runtime failure -- it is addressed by testing each
check against real fixture queries with a known answer, not by a guard here.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class SqlIssue:
    id: str
    severity: str
    description: str
    evidence: str


def _select_star(query: str, schema_columns: list[str] | None) -> SqlIssue | None:
    if re.search(r"select\s+\*", query, re.IGNORECASE):
        return SqlIssue(
            id="select_star",
            severity="medium",
            description=(
                "Query selects all columns with SELECT * instead of naming them, "
                "which breaks silently on upstream schema changes."
            ),
            evidence=query.strip(),
        )
    return None


def _missing_where_on_mutation(query: str, schema_columns: list[str] | None) -> SqlIssue | None:
    if re.match(r"^\s*(update|delete)\b", query, re.IGNORECASE) and not re.search(
        r"\bwhere\b", query, re.IGNORECASE
    ):
        return SqlIssue(
            id="missing_where_on_mutation",
            severity="high",
            description="UPDATE/DELETE statement has no WHERE clause and would affect every row.",
            evidence=query.strip(),
        )
    return None


def _cartesian_join(query: str, schema_columns: list[str] | None) -> SqlIssue | None:
    join_count = len(re.findall(r"\bjoin\b", query, re.IGNORECASE))
    condition_count = len(re.findall(r"\b(on|using)\b", query, re.IGNORECASE))
    if join_count > 0 and condition_count < join_count:
        return SqlIssue(
            id="cartesian_join",
            severity="high",
            description="A JOIN has no matching ON/USING condition, risking an unintended cartesian product.",
            evidence=query.strip(),
        )
    return None


def _undefined_column(query: str, schema_columns: list[str] | None) -> SqlIssue | None:
    if not schema_columns:
        return None

    select_match = re.search(r"select\s+(.*?)\s+from\s", query, re.IGNORECASE | re.DOTALL)
    if not select_match:
        return None

    known = {col.lower() for col in schema_columns}
    unknown_refs = []
    for raw_col in select_match.group(1).split(","):
        col = raw_col.strip()
        if col == "*" or not col:
            continue
        col = col.split(".")[-1]
        col = re.split(r"\s+as\s+", col, flags=re.IGNORECASE)[0].strip()
        if col.lower() not in known:
            unknown_refs.append(col)

    if unknown_refs:
        return SqlIssue(
            id="undefined_column",
            severity="high",
            description=(
                "Query references column(s) not present in the current schema: "
                f"{', '.join(unknown_refs)}."
            ),
            evidence=query.strip(),
        )
    return None


_CHECKS = (_select_star, _missing_where_on_mutation, _cartesian_join, _undefined_column)


def analyze_query(query: str, current_schema_columns: list[str] | None = None) -> list[SqlIssue]:
    """Return every known issue pattern found in this SQL query, or [] if none apply."""
    return [issue for issue in (check(query, current_schema_columns) for check in _CHECKS) if issue]
