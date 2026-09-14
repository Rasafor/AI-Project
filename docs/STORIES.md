# Agentic AI System for Data Pipeline Incident Investigation — Stories

10 stories across 5 releases, walking-skeleton first:
the earliest release proves the thinnest end-to-end path including the trust
spine, and later releases stack features on top of something already working.

## Before the releases — start here

- **[STORY-000](stories/STORY-000.md)** — Build your Command Center

The first thing you build, on day one, before any part of the system itself. It is
the page you keep open for the rest of the programme and demo from. It belongs to no
release and fulfils none of your requirements, because it is the window onto your
system rather than a part of it.

## r0 · Initial Skeleton — weeks 1–1

**Goal:** Establish the basic end-to-end investigation path with trust spine.
**Done when you can show:** Show a basic investigation from log analysis to recommendation with audit logging.

- **[STORY-001](stories/STORY-001.md)** — Basic Log Analysis and Recommendation
- **[STORY-002](stories/STORY-002.md)** — Audit Logging for Investigations

## r1 · Enhanced Analysis — weeks 2–2

**Goal:** Add SQL and data-quality analysis capabilities.
**Done when you can show:** Demonstrate SQL and data-quality analysis contributing to root cause identification.

- **[STORY-003](stories/STORY-003.md)** — SQL Analysis for Root Cause Identification _(waits on STORY-001)_
- **[STORY-004](stories/STORY-004.md)** — Data-Quality Analysis for Root Cause Identification _(waits on STORY-001)_
- **[STORY-010](stories/STORY-010.md)** — Coordinate Specialized Agents for Dependency Analysis _(waits on STORY-004)_

## r2 · Recommendation and Notification — weeks 3–3

**Goal:** Implement recommendation engine and notification system.
**Done when you can show:** Show recommendations being generated and flagged notifications for uncertain cases.

- **[STORY-005](stories/STORY-005.md)** — Recommendation Engine with Human Approval _(waits on STORY-003, STORY-004)_
- **[STORY-006](stories/STORY-006.md)** — Notification System for Uncertain Cases _(waits on STORY-005)_

## r3 · User Interface and Reporting — weeks 4–4

**Goal:** Develop user interface and reporting features.
**Done when you can show:** Present simplified summaries and detailed reports to ops teams.

- **[STORY-007](stories/STORY-007.md)** — User Interface for Ops Teams _(waits on STORY-006)_
- **[STORY-008](stories/STORY-008.md)** — Detailed Reporting of Investigation Outcomes _(waits on STORY-006)_

## r4 · Pilot Testing and Optimization — weeks 5–6

**Goal:** Conduct pilot testing and optimize performance.
**Done when you can show:** Showcase a successful pilot with reduced investigation time and low error rates.

- **[STORY-009](stories/STORY-009.md)** — Pilot Testing and Performance Optimization _(waits on STORY-008)_
