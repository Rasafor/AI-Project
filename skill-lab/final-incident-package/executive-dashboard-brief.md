# Executive Revenue Dashboard — Publish Blocked (Incident Brief)

**Status: BLOCK.** Do not publish the scheduled `orders.csv` refresh to the executive revenue dashboard.

## What happened
- `data-quality-gate` ran against `skill-lab/orders.csv` (the dashboard's data source) ahead of the scheduled publish. Result: **FAIL** — 4 of 8 checks failed.
- Because the data failed, `etl-failure-triage` was run against the `orders_pipeline` ETL job (`run-20260803-2210`) to establish why. The job failed twice — an initial run and one retry — with retries now exhausted and none further scheduled.

## Data-quality findings
- **Stale row:** one row's `load_timestamp` is 2026-07-30 — roughly 95 hours old, past the 24-hour freshness limit.
- **Duplicate order ID:** `ORD-1004` appears twice in the dataset.
- **Missing required field:** `ORD-1005` has a blank `region`.
- **Invalid numeric value:** `ORD-1008` has `revenue = -100.00`, violating the "revenue must be greater than 0" rule.

## Root cause (from pipeline triage)
- The source table's `region` column was changed on 2026-08-02 from a constrained list to free-text, producing values (`'North America'`, `'Europe'`, blank) that the pipeline's `region_code_map` mapping table cannot resolve.
- `region_code_map` was last updated 2026-06-14 — before the source change — and was never updated to match it.
- The retry reproduced the identical failure, confirming this is a deterministic data/config issue rather than a transient one.
- Pipeline on-call was already notified via `data-eng-alerts` at 22:15:08Z.

## What is not yet known
- **Owner:** no individual or team has been confirmed as owning the fix in the reviewed log/metadata.
- **Resolution time:** no ETA is available in the reviewed sources.
- **Financial impact:** not quantified in the reviewed sources — not stated here.

## Recommended next business action
Escalate to the data-engineering on-call/source-system owner (already paged) to confirm ownership and an ETA before the dashboard's next scheduled publish window. Do not publish the orders dataset until the `region` mapping is fixed and the four flagged rows are corrected or excluded.

## Decision
**BLOCK.**
