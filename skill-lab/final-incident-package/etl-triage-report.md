# ETL Failure Triage Report

**Sources reviewed:** `skill-lab/orders-pipeline-failure.log`, `skill-lab/pipeline-run-metadata.md`
**Context:** requested after `data-quality-gate` scored `skill-lab/orders.csv` as FAIL/BLOCK ahead of the scheduled executive dashboard publish — this triage is to establish why the underlying data is bad.

## 1. Incident Summary
Job `orders_pipeline` (run `run-20260803-2210`) failed twice in a row on 2026-08-03 — attempt 1 at 22:10:02Z and its retry at 22:15:05Z — both failing in the `transform` stage's `schema_validate` step because the `region` column is producing values the `region_code_map` mapping table can't resolve. Retries are now exhausted and the job is marked FAILED with no further automatic retry scheduled.

## 2. Evidence
- Attempt 1: extract succeeded (`rows_read=1482`, `duration_ms=812`); `schema_validate` logged `WARN` that `region` — expected `ENUM(NA,EMEA,APAC,LATAM)` — was observed as `VARCHAR(255)` with out-of-domain values `'North America'`, `'Europe'`, `''`.
- Attempt 1 mapping errors: no `region_code_map` entry for `'North America'` (214 rows unresolved), none for `'Europe'` (96 rows unresolved), 12 rows with null/blank `region` and no default mapping — stage failed at 322/1482 rows (21.7%) against a 5% threshold.
- Attempt 2 (retry, 5 minutes later per `backoff=fixed_5m`): extract succeeded (`rows_read=1486`), identical failure signature — `'North America'` 216 rows unresolved, `'Europe'` 97 rows, 13 null/blank — 326/1486 (21.9%), same threshold breach, same failure reason (`region_mapping_threshold_exceeded`).
- Orchestrator log: "Retry attempts exhausted (2/2)," job marked FAILED, on-call notified via `data-eng-alerts` at 22:15:08Z.
- Metadata: last known-good run (`run-20260803-2110`, 21:10:02–21:10:03Z) had only 4/1479 rows (0.27%) fail mapping — well under threshold.
- Metadata "Recent changes on record": source changelog shows `raw_orders.region` changed from `VARCHAR(50)` constrained-list to free-text `VARCHAR(255)` on **2026-08-02**; `region_code_map` was last modified **2026-06-14** — i.e. not updated since, and not updated after the source change.
- Metadata: upstream dependency `orders_source_db` shows no reported incidents for the run window; both attempts' extract steps completed in under a second with row counts consistent with the historical baseline (1479 → 1482 → 1486).

## 3. Ranked Causes

1. **Source schema drift on `region` (most likely).** The source column was widened to free-text on 2026-08-02, roughly 30 hours before the first failure — consistent with the last known-good run (21:10Z, still under threshold) degrading into a hard failure once enough free-text values accumulated. Evidence: the `WARN` log line naming the exact type/domain mismatch, plus the metadata's recorded 2026-08-02 DDL change.
2. **`region_code_map` mapping table not updated for the new source values.** The table's last-modified date (2026-06-14) predates the source change by ~7 weeks, so it was never going to have entries for `'North America'`/`'Europe'`, and has no default for blank/null. Evidence: the three distinct `ERROR` mapping-failure lines in both attempts, each naming an unresolved value and its row count.
3. **Failure is deterministic, not transient (confirmed, not just suspected).** The retry reproduced the same failure signature — same unresolved values, same threshold breach, marginally higher counts consistent with normal row growth, not a different error. This rules out timeout, upstream unavailability, and credential/auth causes: extract succeeded quickly both times, no incidents reported upstream, and no auth-related log lines appear at all.

No evidence supports partial load/truncation (row counts track the historical baseline) or a downstream constraint violation (the job never reached the load stage — it failed earlier, in `schema_validate`).

## 4. Next Tests
1. **For cause 1 (schema drift):** run a read-only `DESCRIBE`/`information_schema` query against `orders_source_db.raw_orders` to confirm the live column type, plus `SELECT DISTINCT region FROM raw_orders` to get the current full set of values — confirm whether `'North America'` and `'Europe'` are the only new values or if more exist.
2. **For cause 2 (stale mapping table):** diff the distinct values from test 1 against the current keys in `region_code_map` (read-only) to get the complete list of missing entries, including whether a null/blank default exists anywhere in the table.
3. **For cause 3 (blast radius / non-transient confirmation):** check, read-only, whether other pipelines or reports consuming `orders_source_db.raw_orders.region` (beyond `orders_pipeline`) show the same rejection pattern — since the schema change is on the shared source table, other consumers may be silently degrading rather than hard-failing.

## 5. Escalation Recommendation
**Escalate now**, to the data-engineering on-call/source-system owner (on-call was already paged via `data-eng-alerts` at 22:15:08Z). Justification: downstream consumers are `executive_revenue_dashboard` and `finance_weekly_export`, retries are exhausted with none further scheduled, and the causal chain is well evidenced rather than speculative (source DDL change dated, mapping table's staleness dated, retry outcome confirms it's not transient). Recommend looping in whoever made the 2026-08-02 `region` column change, since the fix is a coordinated decision — either constrain the source column again or update `region_code_map` with the new values plus a null-handling default — not something to resolve unilaterally from the pipeline side.
