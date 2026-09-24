# STORY-008 — Detailed Reporting of Investigation Outcomes

As a data engineer, I want detailed reports of investigation outcomes, so that I can analyze them further.

**Release:** r3 · User Interface and Reporting (weeks 4–4)
**Owner:** Data Engineer
**Blocked by:** STORY-006

## The requirement this satisfies

- **REQ-017** (Functional, should) — The system must provide detailed reports of investigation outcomes.

## How to build it

Develop reporting module and ensure integration with investigation data.

## Failure paths you must handle

- Report generation fails
- Incorrect report data
- Audit logging fails
- Performance issues
- Unauthorized access to reports

## Acceptance — your stop condition

Tick each box as it genuinely passes. This file is yours — the platform reads
the same criteria out of `.colaberry/progress.json`, which Claude Code keeps in
step (see the managed block in CLAUDE.md). Ticking something you have not
actually met only misleads you.

- [x] Given an investigation, when completed, then a detailed report is generated.
- [x] Given a failed investigation, when reported, then failure details are included.
- [x] Trust: Reports are logged for audit.

When every box above is ticked, stop and show the demo.
