# Common ETL/ELT Failure Signatures

Signature-to-cause reference for the `etl-failure-triage` skill. For each pattern: how it shows up in logs/metadata, what evidence is needed before naming it as a cause (not just suspecting it), and the typical safe next diagnostic step.

## Schema drift / schema mismatch
**Signature:** a column's observed type, cardinality, or domain no longer matches what the transform/load stage expects (e.g. an enum column receiving free-text values, a column missing, a new column appearing).
**Evidence needed:** an explicit type/domain-mismatch log line naming the column and the unexpected value(s), or a metadata field recording a recent source schema change.
**Typical next step:** compare the source table's current schema (read-only `DESCRIBE`/`information_schema` query) against the pipeline's expected schema/mapping definition; check the source system's changelog for recent DDL changes.

## Failed conversion / mapping step
**Signature:** a transform stage reports rows rejected or unresolved during a type cast or value-mapping lookup (e.g. "no mapping entry for value X").
**Evidence needed:** the specific unmapped/unconvertible value(s), the count or percentage of affected rows, and the failure threshold that was crossed.
**Typical next step:** read-only diff between the distinct source values in the affected column and the mapping table's known keys, to enumerate exactly which values are unmapped.

## Retry exhaustion
**Signature:** the job attempted a retry (per its retry policy) and failed again with the same or a near-identical error, then stopped retrying.
**Evidence needed:** two or more attempt log blocks with matching failure signatures and timestamps consistent with the configured backoff.
**Typical next step:** confirm the retry did not change any input (same row counts, same rejected values) — if so, the cause is systemic (data/schema), not transient, and retrying again without a fix is not a viable next step.

## Timeout
**Signature:** a stage log ends abruptly without a completion or error line, or an explicit timeout/deadline-exceeded message appears.
**Evidence needed:** an explicit timeout error, or a stage start with no corresponding stage-complete line before the job/orchestrator marks it failed.
**Typical next step:** check the stage's configured timeout value against its historical duration trend (read-only) to see if this run was anomalously slow or the threshold too tight.

## Upstream unavailability
**Signature:** a connection error, DNS failure, auth rejection, or non-2xx/non-success response when the extract stage reaches out to the source system.
**Evidence needed:** an explicit connection/auth error log line naming the source system, ideally with a status code or error class.
**Typical next step:** check the source system's own status/health endpoint or incident channel (read-only) rather than assuming the pipeline is at fault.

## Partial load / truncation
**Signature:** the row count landed in the destination is materially lower than the row count extracted from the source, with no corresponding rejection/error count that explains the gap.
**Evidence needed:** explicit extract vs. load row counts from the log/metadata that don't reconcile.
**Typical next step:** read-only count comparison between source, staging, and destination tables to localize where rows were dropped.

## Credential / auth failure
**Signature:** a 401/403-class error, "access denied," or "invalid token/credential" message at connection time.
**Evidence needed:** the explicit auth-error log line and, if available, metadata on when the credential/secret was last rotated.
**Typical next step:** check the credential's expiry/rotation metadata (read-only) rather than assuming the code path is broken.

## Downstream constraint violation
**Signature:** the load stage fails on a unique-key, foreign-key, or not-null constraint at the destination.
**Evidence needed:** the specific constraint name and the offending value(s) from the error message.
**Typical next step:** read-only query against the destination table for existing rows that would collide with the incoming batch.
