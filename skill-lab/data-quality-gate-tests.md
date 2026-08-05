# data-quality-gate Trigger Tests

Manual test prompts for verifying the `data-quality-gate` skill triggers reliably on data-validation / publish-readiness requests, and stays silent on ordinary SQL, metric, and dashboard-design requests.

## Should trigger the skill

1. "Before this feeds the executive dashboard, validate `skill-lab/orders.csv` against `skill-lab/quality-contract.md` and tell me PUBLISH or BLOCK."
2. "Can you run a data-quality check on this ETL output before we publish it downstream?"
3. "Is this CSV export ready to publish, or are there data-quality issues I should know about first?"

**Expected behavior for all three:** the skill launches. It reads the dataset (and contract, if supplied or found alongside it) without modifying the source file, runs the 8 standard checks (schema, freshness, expected volume, key uniqueness, duplicates, required fields, nulls, numeric rules), and returns a Markdown table with columns `Check | Evidence | Status | Recommended Action`, followed by exactly two closing lines: an overall **PASS / WARN / FAIL** and a **PUBLISH / BLOCK** recommendation. Every status in the table is evidence-backed (row numbers, values, or counts) — no vague pass/fail assertions.

## Should NOT trigger the skill

1. "Write a SQL query that sums revenue by region for the last 30 days."
2. "Design a dashboard layout showing weekly order volume by product."
3. "Calculate the average order value from this dataset."

**Expected behavior for all three:** the skill does not launch. The request is handled directly — SQL is written, the layout is designed/described, or the metric is calculated — with no PASS/WARN/FAIL table, no PUBLISH/BLOCK recommendation, and no unsolicited data-quality commentary appended. If the user separately asks whether the result is safe to publish, that follow-up (not the original SQL/metric/design request) is what should invoke the skill.

## Expected output requirements (positive cases)

- Dataset is read-only; the skill must never modify, sort, reorder, or delete rows in the source file.
- Contract rules take precedence; where the contract is silent, the skill falls back to the defaults documented in `references/quality-checks.md` rather than inventing arbitrary thresholds.
- The output table's `Evidence` column always contains something concrete and checkable (a row locator, a value, or a count) — not a restated status.
- The two closing lines appear exactly once, in order (overall result, then recommendation), and the recommendation logic is consistent: any FAIL check forces BLOCK.
