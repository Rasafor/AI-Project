# STORY-004 — Data-Quality Analysis for Root Cause Identification

As a data engineer, I want the system to analyze data-quality issues, so that root causes can be identified.

**Release:** r1 · Enhanced Analysis (weeks 2–2)
**Owner:** Data Engineer
**Blocked by:** STORY-001

## The requirement this satisfies

- **REQ-004** (Functional, must) — The system must analyze data-quality issues to identify potential root causes.

## How to build it

Implement data-quality analysis module and connect to data-quality metrics source.

## Failure paths you must handle

- Data-quality source unavailable
- Analysis errors
- Incorrect root cause identification
- Audit logging fails
- Performance issues

## Acceptance — your stop condition

Tick each box as it genuinely passes. This file is yours — the platform reads
the same criteria out of `.colaberry/progress.json`, which Claude Code keeps in
step (see the managed block in CLAUDE.md). Ticking something you have not
actually met only misleads you.

- [ ] Given data-quality metrics, when analyzed, then root causes are identified.
- [ ] Given data with no quality issues, when analyzed, then no root causes are reported.
- [ ] Trust: Data-quality analysis results are logged for audit.

When every box above is ticked, stop and show the demo.
