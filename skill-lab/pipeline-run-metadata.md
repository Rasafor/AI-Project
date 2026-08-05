# Pipeline Run Metadata: orders_pipeline

- **job_name:** orders_pipeline
- **run_id:** run-20260803-2210
- **schedule:** hourly (cron `10 * * * *`)
- **source:** `orders_source_db.raw_orders`
- **destination:** `warehouse.fact_orders`
- **downstream_consumers:** executive_revenue_dashboard, finance_weekly_export

## Attempt history

| Attempt | Start (UTC) | End (UTC) | Rows read | Rows failed mapping | Result |
|---|---|---|---|---|---|
| 1 | 2026-08-03T22:10:02Z | 2026-08-03T22:10:04Z | 1482 | 322 (21.7%) | FAILED — schema_validate |
| 2 (retry) | 2026-08-03T22:15:05Z | 2026-08-03T22:15:07Z | 1486 | 326 (21.9%) | FAILED — schema_validate |

- **retry_policy:** max_attempts=2, backoff=fixed_5m
- **final_status:** FAILED (retries exhausted, no further automatic retry scheduled)
- **failure_threshold:** schema_validate stage allows max 5% row failure before hard-failing

## Last known-good run

- **run_id:** run-20260803-2110
- **start/end (UTC):** 2026-08-03T21:10:02Z / 2026-08-03T21:10:03Z
- **rows_read:** 1479
- **rows_failed_mapping:** 4 (0.27%)
- **result:** SUCCESS

## Recent changes on record

- 2026-08-02: source system changelog records `raw_orders.region` column changed from `VARCHAR(50)` constrained-list to free-text `VARCHAR(255)` on the source side.
- No corresponding change was made to the `region_code_map` mapping table used by the transform stage (last modified 2026-06-14, per mapping-table metadata).

## Dependency status

- **upstream_dependency:** orders_source_db — no incidents reported on the source system's status page for the run window.
- **on_call_notified:** yes — channel `data-eng-alerts`, notification dispatched 2026-08-03T22:15:08Z.
