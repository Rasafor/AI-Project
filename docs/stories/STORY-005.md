# STORY-005 — Recommendation Engine with Human Approval

As an ops team member, I want recommendations to be approved by humans, so that major changes are verified.

**Release:** r2 · Recommendation and Notification (weeks 3–3)
**Owner:** Ops Team Member
**Blocked by:** STORY-003, STORY-004

## The requirement this satisfies

- **REQ-005** (Functional, must) — The system must recommend corrective actions for human approval.
- **REQ-010** (Safety, must) — The system must ensure recommendations for major changes are reviewed before approval.

## How to build it

Develop recommendation engine and approval workflow.

## Failure paths you must handle

- Approval workflow fails
- Incorrect recommendation categorization
- Audit logging fails
- Approval delays
- Unauthorized approvals

## Acceptance — your stop condition

Tick each box as it genuinely passes. This file is yours — the platform reads
the same criteria out of `.colaberry/progress.json`, which Claude Code keeps in
step (see the managed block in CLAUDE.md). Ticking something you have not
actually met only misleads you.

- [ ] Given a recommendation, when it is major, then it requires human approval.
- [ ] Given a minor recommendation, when generated, then it is auto-approved.
- [ ] Trust: All recommendations and approvals are logged.

When every box above is ticked, stop and show the demo.
