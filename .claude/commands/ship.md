---
description: Test, stage, and draft a PR for the current change
argument-hint: [pr-title]
allowed-tools: Bash(python -m unittest discover:*), Bash(git status:*), Bash(git add:*), Bash(git diff:*)
---

1. Run the test command: `python -m unittest discover -s pipeline_incident_investigator/tests -t .`
   If anything fails (non-zero exit, any `FAIL`/`ERROR` in the output), STOP here and report
   the failing test names and their output verbatim. Do not proceed to step 2 or 3.
   # WHY: verification is step one, and step one is allowed to say no.

2. On green (exit 0, no failures): run `git status` to see what actually changed, then stage
   those files by explicit path with `git add <path> ...` — never `git add -A` or `git add .`.
   This repo has no formatter configured (no black/ruff/pyproject.toml, none installed) —
   there is no format step to run here; do not invent one.

3. Run `git diff --staged` and read it in full. Draft a PR description titled `$ARGUMENTS`,
   with:
   - **Summary** — what changed and why, grounded in the actual staged diff, not guessed.
   - **Test Evidence** — the exact command from step 1 and a quoted line of its real passing
     output (e.g. the `OK` line and test count from `unittest`).
   - **Risk** — one line on blast radius / what could break, or "None identified" if genuinely
     none.

   Output this description as your final message. Do not run `git commit`, do not run
   `git push`, do not open a PR — this command prepares a change, it does not ship one.
   # WHY: $ARGUMENTS is whatever you type after /ship — the title travels into the body.
