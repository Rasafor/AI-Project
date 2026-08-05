# Quality Checks Reference

Detailed definitions for the 8 standard checks run by the `data-quality-gate` skill. Read this file before scoring any check. For each check: what it verifies, what evidence to capture, and the PASS/WARN/FAIL criteria (including the default to use when the contract doesn't define one).

## Schema
**Verifies:** the dataset's columns match what's expected — present, correctly named, no unexpected structural drift.
**Evidence to capture:** the actual column list vs. the expected list (from the contract, or inferred from the dataset's own header if the contract is silent).
**Criteria:**
- PASS — all contract-referenced (or clearly-required) columns are present and correctly named.
- WARN — extra/unexpected columns present, or the contract doesn't specify a schema at all.
- FAIL — a contract-required column is missing or renamed.

## Freshness
**Verifies:** the data is recent enough to be trustworthy at publish time.
**Evidence to capture:** the most recent (and, if relevant, least recent) value of the load/timestamp field, and its age relative to the check time.
**Criteria:**
- PASS — max age is within the contract's threshold.
- WARN — no freshness threshold in the contract; report the observed age and flag it as unverified.
- FAIL — any row's relevant timestamp exceeds the contract's max-age threshold.
Default threshold when the contract is silent: flag anything older than 24 hours as WARN, not FAIL, since no explicit rule was violated.

## Expected volume
**Verifies:** the row count is in a plausible range — not a partial load, not a runaway duplication.
**Evidence to capture:** actual row count vs. the contract's minimum (and maximum, if defined).
**Criteria:**
- PASS — row count is within the contract's bounds.
- WARN — no volume expectation in the contract; report the count for context.
- FAIL — row count is below the contract's minimum (or above its maximum, if one is defined).

## Key uniqueness
**Verifies:** the designated business/primary key has no duplicate values.
**Evidence to capture:** every duplicated key value, with the specific rows (line numbers or another stable locator) it appears on.
**Criteria:**
- PASS — the key column is unique across all rows.
- WARN — no key is specified in the contract; identify the most likely candidate key and check it anyway, noting the assumption.
- FAIL — any duplicate value exists on the designated key.

## Duplicates
**Verifies:** no two rows are identical across all fields (a broader check than key uniqueness — a duplicate key is not automatically a full-row duplicate, and vice versa).
**Evidence to capture:** any row pairs/groups that match on every field, with their locators.
**Criteria:**
- PASS — no full-row duplicates found.
- FAIL — at least one full-row duplicate exists.
(No WARN state for this check — it's binary and doesn't depend on the contract.)

## Required fields
**Verifies:** every field the contract marks as required is non-blank on every row.
**Evidence to capture:** each required field with a blank/null value, and the row(s) it occurs on.
**Criteria:**
- PASS — no blanks in any contract-required field.
- WARN — the contract doesn't mark any field as required; spot-check fields that look structurally essential (keys, dates, core categorical fields) and report blanks found, if any, without failing the dataset on them.
- FAIL — any contract-required field is blank on any row.

## Nulls
**Verifies:** the general null/blank rate across the dataset, beyond what's already covered by Required Fields — a broader data-completeness signal.
**Evidence to capture:** count (or rate) of blanks per column, for columns not already flagged under Required Fields.
**Criteria:**
- PASS — no unexpected blanks outside what's already reported under Required Fields.
- WARN — blanks found in non-required fields; report the rate, don't block on it alone.
- FAIL — never fails independently; a null in a required field is scored under Required Fields, not here, to avoid double-penalizing the same defect.

## Numeric rules
**Verifies:** contract-defined numeric constraints on specific fields (e.g. "revenue must be greater than 0," "quantity must be a positive integer").
**Evidence to capture:** every value that violates a defined rule, with its row locator and the value itself.
**Criteria:**
- PASS — all contract-defined numeric rules hold on every row.
- WARN — the contract defines no numeric rules; skip this check and say so, rather than inventing thresholds.
- FAIL — any row violates a contract-defined numeric rule.
