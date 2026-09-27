# STORY-003 — SQL Analysis for Root Cause Identification

As a data engineer, I want the system to analyze SQL queries, so that potential issues can be identified.

**Release:** r1 · Enhanced Analysis (weeks 2–2)
**Owner:** Data Engineer
**Blocked by:** STORY-001

## The requirement this satisfies

- **REQ-003** (Functional, must) — The system must analyze SQL queries to identify potential issues.

## How to build it

Develop SQL analysis module and integrate with SQL data source.

## Failure paths you must handle

- SQL data source unavailable
- SQL analysis errors
- Incorrect issue identification
- Audit logging fails
- Performance degradation

## Acceptance — your stop condition

Tick each box as it genuinely passes. This file is yours — the platform reads
the same criteria out of `.colaberry/progress.json`, which Claude Code keeps in
step (see the managed block in CLAUDE.md). Ticking something you have not
actually met only misleads you.

- [ ] Given a SQL query, when analyzed, then potential issues are identified.
- [ ] Given a SQL query with no issues, when analyzed, then no issues are reported.
- [ ] Trust: SQL analysis results are logged for audit.

When every box above is ticked, stop and show the demo.
