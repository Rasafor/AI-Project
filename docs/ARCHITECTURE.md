# Project Architecture

**Status:** Foundation approved 2026-07-30 (Session `CC-20260730-1mk2`).
**Scope:** This is a personal coursework workspace for a class taught by
Colaberry — not the Colaberry production system that root `CLAUDE.md`'s
backend/frontend sections describe. See "Scope decision" below.

---

## Scope decision

Root `CLAUDE.md` is written for a full Node/Express/React "Colaberry"
product (backend, frontend, Sequelize, Mandrill, Basecamp, a production VPS,
a named DRI). None of that exists in this repo, and nothing in this
repo's actual stack (static HTML/CSS/JS) or the coursework framing
("Week 3 component") calls for it.

**Decision:** apply CLAUDE.md's process-discipline rules, which are
stack-agnostic —

- PROGRESS.md hard gate (Logging & Reporting Rules section)
- Session ID protocol (Session start protocol)
- Testing minimums — happy-path coverage for new logic (Testing & Validation Rules)
- Definition of Done

— and skip the product-specific rules that assume infrastructure this repo
doesn't have (backend/frontend stack, Mandrill/Basecamp, telemetry
BuildManifest, VPS deploys, DRI escalation email).

Approved by user, 2026-07-30.

---

## Folder tree

```
AI-Project/
├── CLAUDE.md
├── PROGRESS.md
├── README.md
├── directives/
│   └── week-03.md
├── src/
│   ├── memory-match.html   (pre-existing, left in place — see note)
│   └── week-03/
├── tests/
│   └── week-03/
├── docs/
│   ├── ARCHITECTURE.md     (this file)
│   └── week-03/
└── .claude/
    └── agents/
```

---

## Per-folder reference

### `directives/`
- **Purpose:** One SOP-style brief per weekly assignment — goal, inputs,
  outputs, edge cases, verification — written before the corresponding
  `src/week-XX/` work starts.
- **Belongs:** `week-XX.md` files.
- **Never:** Code, test results, or after-the-fact write-ups.
- **CLAUDE.md rule:** "Layer 1: Directives" — human-readable SOPs; "Directive
  validation" section.
- **Status:** NOW (created).
- **Verification:** File exists before the matching `src/week-XX/` work
  starts; has a stated verification method.

### `src/week-XX/`
- **Purpose:** The actual deliverable code for a given week.
- **Belongs:** HTML/CSS/JS for that week's component.
- **Never:** Assignment briefs, test files, write-ups.
- **CLAUDE.md rule:** Existing convention (`src/memory-match.html` predates
  this structure) + Modular Composition Rule (small, single-responsibility
  files).
- **Status:** NOW for `week-03/` (created, empty). `week-01/`/`week-02/`
  intentionally NOT created — see note below.
- **Verification:** Runs correctly in a browser; matches its directive's
  verification checklist.

### `tests/week-XX/`
- **Purpose:** Happy-path verification per component.
- **Belongs:** A checklist or test file per week.
- **Never:** Component source code.
- **CLAUDE.md rule:** Testing & Validation Rules — "minimum acceptable now:
  new logic ships with at least one test covering the happy path."
- **Status:** NOW for `week-03/` (created, empty).
- **Verification:** Exists before that week is marked `[x]` in PROGRESS.md.

### `docs/week-XX/`
- **Purpose:** Write-ups, notes, or screenshots that ship with a component
  but aren't code or test artifacts.
- **Belongs:** `notes.md`, screenshots, reflections.
- **Never:** Assignment briefs (`directives/`) or code (`src/`).
- **CLAUDE.md rule:** Folder Responsibilities — "/docs — in-repo
  documentation that ships with the codebase."
- **Status:** NOW for `week-03/` (created, empty).

### `.claude/agents/`
- **Status:** EXISTING, DO-NOT-TOUCH — Claude Code harness config, not a
  coursework deliverable location. Not modified by this change.

### `scripts/` — deferred, not created
CLAUDE.md's Logging section calls for a per-session HTML changelog via
`node scripts/generateSessionChangelog.js`. That assumes a Node toolchain,
which this repo doesn't have (no `package.json`, pure static HTML). Building
that automation now would add tooling weight disproportionate to a
static-HTML weekly assignment, and the user's approval explicitly excluded
installing dependencies. The plain `PROGRESS.md` entry — which CLAUDE.md
already accepts as the fallback "until the writer exists" — satisfies the
audit requirement instead. Revisit only if a later week's component
actually needs Node.

---

## Explicitly excluded

| Folder | Why |
|---|---|
| `backend/`, `frontend/` | No Node/Express/React/Sequelize exists or is needed for coursework HTML/JS components |
| `nginx/`, `preview-db-init/` | No deployment or database infrastructure in this repo |
| `execution/`, `intelligence/`, `system/` | Colaberry-product-specific subsystems (legacy Python, portal state maps) — not part of a student coursework repo |

---

## Open item (not resolved by this change)

`src/memory-match.html` predates the `week-XX/` convention and was **left in
place** — the foundation change preserves all existing work and does not
move or rename it. Whether it belongs in `week-01/`, `week-02/`, or stays
standalone is an open decision for the user; nothing in this change assumes
an answer.

---

## Traceability

| Folder | Justification source | Evidence |
|---|---|---|
| `directives/` | CLAUDE.md rule | "Layer 1: Directives"; "Directive validation" |
| `src/week-03/` | Existing convention + CLAUDE.md rule | `src/memory-match.html` precedent; Modular Composition Rule |
| `tests/week-03/` | CLAUDE.md rule | Testing & Validation Rules, "minimum now" clause |
| `docs/week-03/` | CLAUDE.md rule + existing convention | Folder Responsibilities table; `docs/` already existed |
| PROGRESS.md gate applies | CLAUDE.md rule | Logging & Reporting Rules, hard gate, "enforced now" |
| `scripts/` deferred | CLAUDE.md rule, but scoped out | Per-session HTML changelog rule vs. "no dependencies" constraint in this approval |
