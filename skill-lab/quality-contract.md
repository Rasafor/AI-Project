# Quality Contract: orders.csv

Applies to `skill-lab/orders.csv`. Any row or dataset condition that violates a rule below is a **FAIL** for that check.

## Rules

- **Uniqueness**: `order_id` must be unique. No two rows may share the same `order_id`.
- **Required field**: `region` is required. No row may have a blank or null `region`.
- **Numeric rule**: `revenue` must be greater than 0.
- **Freshness**: `load_timestamp` must be less than 24 hours old at the time of the check.
- **Expected volume**: the dataset must contain at least 10 rows.
