# Progress Log

## Foundation

- [x] Establish coursework folder architecture per CLAUDE.md governance
  - Date: 2026-07-30
  - Session: CC-20260730-1mk2
  - What changed: Created `directives/` (with `week-03.md` template), `src/week-03/`, `tests/week-03/`, `docs/week-03/`, each with a short README; added `docs/ARCHITECTURE.md` documenting the approved structure, scope decision, and traceability. No existing files (`README.md`, `src/memory-match.html`, `.claude/agents/`) were moved or modified.
  - Verification: user confirmed ("APPROVE FOUNDATION")
  - Notes: Scope decision — this repo is treated as a personal coursework workspace, not the Colaberry production system CLAUDE.md's backend/frontend sections describe (user-confirmed). `scripts/` intentionally deferred: CLAUDE.md's HTML changelog rule assumes a Node toolchain this repo doesn't have, and this change's approval explicitly excluded installing dependencies — see `docs/ARCHITECTURE.md` for full reasoning. Placement of pre-existing `src/memory-match.html` into a `week-XX/` folder is an open question, left untouched pending user decision.
