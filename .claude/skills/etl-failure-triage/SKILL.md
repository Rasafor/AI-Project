---
name: etl-failure-triage
description: Use when the user asks why an ETL or ELT pipeline, scheduled load, SQL job, data refresh, or ingestion process failed or produced suspicious output. Reviews logs and run metadata, ranks likely causes, cites evidence, and recommends the next safe diagnostic steps.
---

# ETL Failure Triage

## Required input
- A log excerpt, run output, or a description of the failure/suspicious behavior. Ask for one if none is supplied — do not triage from a bare "it failed."
- Run metadata, if available (job name, run ID, schedule, start/end times, retry count, upstream/downstream dependencies, recent schema changes). Read it when supplied; if it's missing, say so rather than guessing at it.

## Procedure
1. Read the log/output and any run metadata in full before forming any conclusion.
2. Separate **facts** (directly observed in the log/metadata — timestamps, error strings, row counts, exit codes) from **hypotheses** (inferred explanations for those facts). Never present a hypothesis as a fact.
3. Match the failure signature against known patterns (schema drift, type/mapping errors, timeout, retry exhaustion, upstream unavailability, partial load, credential/auth failure, etc.) using `references/common-failures.md`, which maps each signature to the evidence needed to credibly claim it.
4. Build a ranked list of likely causes. Every cause must cite specific evidence (a log line, a metadata field, a timestamp) — a cause with no cited evidence does not belong in the ranked list; if you suspect it anyway, note it separately as "insufficient evidence."
5. For each ranked cause, give one concrete next diagnostic step — the smallest safe, read-only action that would confirm or rule it out.

## Constraints
- Never modify, patch, or refactor pipeline code.
- Never rerun, retrigger, or resubmit the job.
- Never state a root cause without citing the evidence for it in the same breath.
- Stay within triage: diagnosis and next steps, not remediation.

## Output format
Return exactly these five sections, in order:
1. **Incident Summary** — one or two sentences: what job, when, what happened.
2. **Evidence** — observed facts only (log lines, metadata fields, counts, timestamps), no interpretation.
3. **Ranked Causes** — most to least likely; each cause states its supporting evidence inline.
4. **Next Tests** — one safe, read-only diagnostic step per ranked cause (query, log grep, metadata check — never a code change or rerun).
5. **Escalation Recommendation** — whether and to whom this should escalate, based on blast radius and whether the cause is confirmed or still hypothetical.
