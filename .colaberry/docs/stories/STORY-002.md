# STORY-002 — Audit Logging for Investigations

As a compliance officer, I want all investigation activities logged, so that I can audit them later.

**Release:** r0 · Initial Skeleton (weeks 1–1)
**Owner:** Compliance Officer
**Blocked by:** nothing — you can start this now

## The requirement this satisfies

- **REQ-011** (Observability, must) — The system must log all investigation activities for audit purposes.

## How to build it

Set up audit logging framework and ensure all investigation steps are logged.

## Failure paths you must handle

- Logging service unavailable
- Logs are tampered
- Incomplete logs
- Timestamp errors
- Unauthorized access to logs

## Acceptance — your stop condition

Tick each box as it genuinely passes. This file is yours — the platform reads
the same criteria out of `.colaberry/progress.json`, which Claude Code keeps in
step (see the managed block in CLAUDE.md). Ticking something you have not
actually met only misleads you.

- [ ] Given an investigation, when it is conducted, then all activities are logged.
- [ ] Given a failed investigation, when it is logged, then failure details are included.
- [ ] Trust: Logs are immutable and timestamped.

When every box above is ticked, stop and show the demo.
