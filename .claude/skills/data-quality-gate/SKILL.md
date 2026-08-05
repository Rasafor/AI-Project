---
name: data-quality-gate
description: Use when the user asks to validate a dataset, CSV, ETL output, or query result for data-quality issues, or asks whether a dataset, dashboard, or report is ready to publish (PASS/WARN/FAIL, PUBLISH/BLOCK framing). Checks the data against a quality contract and returns evidence-backed results. Do NOT use for ordinary requests to write or debug SQL, calculate/define a metric, or design or build a dashboard — those alone are not data-quality-gate requests unless the user is also asking whether the underlying data is clean or safe to publish.
---

# Data Quality Gate

## When to use
Trigger this skill when the user asks to:
- Validate a dataset, CSV, ETL output, or query result for quality issues.
- Run a data-quality check ahead of publishing or sharing data.
- Determine whether a dataset, dashboard, or report is ready to publish — i.e. any "is this safe/ready to publish," "PASS or FAIL," or "PUBLISH or BLOCK" framing.

## When NOT to use
Do not trigger for ordinary engineering/analytics requests, even if they touch data:
- Writing, debugging, or optimizing a SQL query.
- Calculating, defining, or explaining a metric.
- Designing, building, or styling a dashboard or report layout.

Handle these directly. If a request mixes the two ("write this SQL, then tell me if the result is safe to publish"), only the publish-readiness half invokes this skill — do the SQL work as a normal request first.

## Required input
1. **Dataset path** — ask for it if not supplied. Do not proceed without a concrete path to the file or query result.
2. **Quality contract** — look for a contract file (e.g. `quality-contract.md`) alongside the dataset, or ask the user for one. If none exists or is supplied, fall back to default thresholds (see reference) and note in the report that no contract was supplied.

## Procedure
1. Read the dataset. Never modify it — this skill is read-only against the source data under all circumstances.
2. Read the quality contract if available; extract its explicit rules (uniqueness keys, required fields, freshness threshold, expected row count, numeric rules).
3. Run the standard checks: schema, freshness, expected volume, key uniqueness, duplicates, required fields, nulls, numeric rules.
   **Before scoring any check, read `references/quality-checks.md`** — it defines what each check verifies, what evidence to capture, and the exact PASS/WARN/FAIL criteria and defaults to use when the contract is silent.
4. For each check, capture concrete evidence (row numbers, values, counts) rather than a vague pass/fail assertion.

## Output format
Return a Markdown table with these exact columns:

| Check | Evidence | Status | Recommended Action |
|---|---|---|---|
| ... | ... | PASS / WARN / FAIL | ... |

Then close the report with exactly two final lines:
1. Overall result — **PASS**, **WARN**, or **FAIL** (FAIL if any check fails; WARN if no failures but at least one warning; PASS only if every check passes).
2. Recommendation — **PUBLISH** or **BLOCK** (BLOCK on any FAIL; PUBLISH only when the overall result is PASS, or WARN with no contract rule actually violated — state the reasoning for WARN-only cases).

## Constraints
- Never modify, sort, delete, reorder, or rewrite the source dataset. This skill only reads and reports.
- Do not skip a check because the contract is silent on it — apply the default check list from the reference and mark it WARN-eligible when no contract threshold exists.
- Keep the report procedural and evidence-based. Do not editorialize beyond the Recommended Action column and the two closing lines.
