# STORY-006 — Notification System for Uncertain Cases

As a data engineer, I want the system to notify me of uncertain cases, so that I can review them.

**Release:** r2 · Recommendation and Notification (weeks 3–3)
**Owner:** Data Engineer
**Blocked by:** STORY-005

## The requirement this satisfies

- **REQ-006** (Functional, must) — The system must flag uncertain root causes and notify the user.

## How to build it

Implement notification system and integrate with existing ops tools.

## Failure paths you must handle

- Notification service unavailable
- Incorrect notifications
- Audit logging fails
- Notification delays
- Unauthorized access to notifications

## Acceptance — your stop condition

Tick each box as it genuinely passes. This file is yours — the platform reads
the same criteria out of `.colaberry/progress.json`, which Claude Code keeps in
step (see the managed block in CLAUDE.md). Ticking something you have not
actually met only misleads you.

- [ ] Given an uncertain root cause, when identified, then a notification is sent.
- [ ] Given a certain root cause, when identified, then no notification is sent.
- [ ] Trust: Notifications are logged for audit.

When every box above is ticked, stop and show the demo.
