# STORY-007 — User Interface for Ops Teams

As an ops team member, I want a user-friendly interface, so that I can efficiently manage and monitor system operations.

**Release:** r3 · User Interface and Reporting (weeks 4–4)
**Owner:** UI/UX Team
**Blocked by:** STORY-006

## The requirement this satisfies

- **REQ-007** (Functional, must) — The system must provide simplified summaries for ops teams.
- **REQ-013** (Non-functional, should) — Every screen the ops team uses must complete its primary action in three clicks or fewer.

## How to build it

Implement the UI using the existing design framework, ensuring all primary actions are accessible within three clicks. Optimize backend queries to maintain response times under 2 seconds.

## Failure paths you must handle

- Interface takes more than three clicks for primary actions
- Response times exceed 2 seconds
- Audit trail fails to log actions

## Acceptance — your stop condition

Tick each box as it genuinely passes. This file is yours — the platform reads
the same criteria out of `.colaberry/progress.json`, which Claude Code keeps in
step (see the managed block in CLAUDE.md). Ticking something you have not
actually met only misleads you.

- [ ] Given an ops team member, when accessing the dashboard, then the primary action completes in three clicks or fewer.
- [ ] Given an ops team member, when using the interface, then response times are under 2 seconds for any action.
- [ ] Trust: Given any user action, when logged, then the audit trail records the action with a timestamp.

When every box above is ticked, stop and show the demo.
