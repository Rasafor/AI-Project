# Data Quality Report

**Dataset:** `skill-lab/orders.csv` (12 data rows + header)
**Contract:** `skill-lab/quality-contract.md`
**Checked at (assumed):** 2026-08-03T09:30:00Z — the most recent `load_timestamp` values in the dataset cluster around 2026-08-03T09:15–09:27Z, used here as the reference "now" for freshness scoring.

| Check | Evidence | Status | Recommended Action |
|---|---|---|---|
| Schema | All contract-referenced columns present and consistently named across every row: `order_id`, `order_date`, `customer_name`, `region`, `product`, `quantity`, `unit_price`, `revenue`, `load_timestamp` (9 columns). | PASS | None. |
| Freshness | 11 of 12 rows have `load_timestamp` between 2026-08-03T09:15:00Z and 2026-08-03T09:27:00Z (within 24h). Row `ORD-1010` (CSV line 12) has `load_timestamp` = 2026-07-30T10:00:00Z — roughly 95 hours old, exceeding the 24h threshold. | FAIL | Re-extract/re-load `ORD-1010` from source before publishing; investigate why this row's load lagged the rest of the batch. |
| Expected volume | 12 data rows present; contract minimum is 10. | PASS | None. |
| Key uniqueness (`order_id`) | `order_id` value `ORD-1004` appears twice: CSV line 5 (`order_date` 2026-08-02, `load_timestamp` 09:18:00Z) and CSV line 11 (`order_date` 2026-08-03, `load_timestamp` 09:25:00Z). | FAIL | Determine which `ORD-1004` row is authoritative, or assign the duplicate a corrected unique `order_id`, before publishing. |
| Duplicates (full-row) | No two rows are identical across all 9 fields — the two `ORD-1004` rows differ in `order_date` and `load_timestamp`, so this is a key collision, not a full-row duplicate. | PASS | None. |
| Required fields (`region`) | CSV line 6 (`order_id` `ORD-1005`) has a blank `region` value. | FAIL | Backfill the correct region for `ORD-1005` from source before publishing. |
| Nulls (other fields) | No blank/null values found in `order_id`, `order_date`, `customer_name`, `product`, `quantity`, `unit_price`, `revenue`, or `load_timestamp` on any row other than the `region` gap already reported above. | PASS | None. |
| Numeric rules (`revenue` > 0) | CSV line 9 (`order_id` `ORD-1008`) has `revenue` = -100.00. | FAIL | Investigate `ORD-1008` — negative revenue violates the contract (likely a refund/credit or entry error); correct or exclude the row before publishing. |

**Overall result: FAIL** (4 of 8 checks failed: freshness, key uniqueness, required fields, numeric rules)

**Recommendation: BLOCK**
