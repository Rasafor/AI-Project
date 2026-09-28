---
description: Run the STORY-009 pilot, record the result in progress.json, PROGRESS.md and the story doc so all three agree, then commit with the Story trailer
argument-hint: [run-label] [why this run]
allowed-tools: Bash(python scripts/run_pilot.py:*), Bash(python -m unittest:*), Bash(python -c:*), Bash(git status:*), Bash(git diff:*), Bash(git log:*), Bash(git add:*), Read, Edit, AskUserQuestion
---

Record one pilot run end to end. The three records (`.colaberry/progress.json`,
`PROGRESS.md`, `docs/stories/STORY-009.md`) must say the same thing when this finishes.
# WHY: past runs needed follow-up commits (4276918, 7356721) because these drifted apart.

Arguments: `$ARGUMENTS`. The first word is the run label. Anything after it is why you ran it.

## 1. Get the inputs (ask, don't guess)

- If there's no label, or `pilot/results/<label>.json` already exists, ask for one with
  AskUserQuestion. Offer `run-<today YYYY-MM-DD>` and `followup-<next number>` as options.
  `run_pilot.py` refuses to overwrite a label, and that is on purpose.
- If no reason was given, ask why this run is happening. Options: "new held-out cases",
  "code change to pattern_matcher", "regression recheck on current main". The answer goes
  into all three records.
- The operator is `regina` unless the user says otherwise.

## 2. Pre-flight: stop if any check fails

1. Run `git status --short`. If anything under `pilot/cases/` or `pilot/expected.json` is
   uncommitted, STOP. Say the cases have to be committed before the run (the pre-registration
   rule this pilot has followed since bc3f573), and ask whether to commit them first as
   `STORY-009: record <n> pilot cases before the run`.
   Note any other uncommitted files and never stage them later.
2. Run the same tests CI runs (`.github/workflows/pr-standards.yml`):
   `python -m unittest discover -s pipeline_incident_investigator/tests -t .` and
   `python -m unittest tests.test_command_center_render tests.test_generate_investigation_snapshot tests.test_check_story_commits`.
   (`tests/` is not a package, so `discover -s tests` fails. Don't use it.)
   If either fails, STOP and quote the failing test names.

## 3. Run the pilot

`python scripts/run_pilot.py <label> --operator <operator>`
- Exit 0 means passed and exit 1 means failed. Both are real results, so record either one.
- Exit 2 means the pilot could not run. STOP and quote stderr. Record nothing.

Verify the audit trail independently:
`python -c "from pipeline_incident_investigator.audit_log import verify_log_integrity as v; print(len(v('pilot/results/<label>_audit_trail.jsonl')))"`
If this raises, the trust criterion fails. Say so and continue recording.

## 4. Work out what's true

Read `pilot/results/<label>.json`. Find the previous run: the newest other file in
`pilot/results/` by `git log -1 --format=%ct`. Compare case by case and list:
- the wrong cases (path, expected, verdict), marking a **confident wrong answer**
  (a verdict other than `uncertain` that doesn't match) apart from a safe miss (`uncertain`)
- every case whose `correct` changed since the previous run
- errors/total, error rate vs the limit, slowest seconds vs the budget, and the audit entry count

The criteria this run implies:
error-rate = `passed` and errors ≤ limit; time = `all_within_budget`; audit = trail verifies.
If any of them differs from the current `passed` flag in progress.json, don't change it
yet. Show old vs new and ask the user with AskUserQuestion. The owner sets these flags by
hand sometimes (4276918), so a silent flip is wrong in both directions.

## 5. Update all three records from the same numbers

Mint a Session ID `CC-<YYYYMMDD>-<4 random alphanumerics>` unless this session already
has one.

- **`.colaberry/progress.json`**, story `STORY-009` only: set the criteria `passed` flags
  as agreed, append ` <LABEL UPPERCASE> (<date>): <reason>. Pilot <label>: <e>/<n> wrong
  (<rate>) vs <limit> -- PASSED|FAILED; slowest <s> s; audit trail verifies (<k> entries).
  <wrong-case list or "no wrong cases">.` to `notes`, and set `updated_at` to the current
  UTC ISO time. Leave `verification` and every other story alone. Load and dump it
  with Python `json` (indent=2, ensure_ascii=False) so formatting is stable.
- **`docs/stories/STORY-009.md`**: update the box and the `_Met: ..._` / `_Not met: ..._`
  note on the error-rate line to cite this run's numbers and `pilot/results/<label>.json`.
  Keep the existing caveat about the cases being seen during development unless this run
  used cases the developer did not write.
- **`PROGRESS.md`**: re-read the last 20 lines first, because other sessions append here.
  Then append the standard entry (`- [x]` if the pilot passed, else `- [ ]`):
  title `STORY-009 — pilot <label> (<e>/<n> = <rate>)`, plus Date, Session, What changed
  (reason + any code or case changes since the previous run), Verification (the test
  counts from step 2, the pilot numbers and the audit count), and Notes (changed cases and
  the honest limit on what this run proves).

Then run the agreement check and fix any mismatch it prints before moving on:
```
python -c "import json,re,sys;L='<label>';r=json.load(open(f'pilot/results/{L}.json'));n=f\"{r['errors']}/{r['total']}\";s=[x for x in json.load(open('.colaberry/progress.json',encoding='utf-8'))['stories'] if x['id']=='STORY-009'][0];d=open('docs/stories/STORY-009.md',encoding='utf-8').read();p=open('PROGRESS.md',encoding='utf-8').read();bad=[k for k,t in [('progress.json notes',s['notes']),('STORY-009.md',d),('PROGRESS.md',p)] if L not in t or n not in t];tick=re.search(r'- \[(x| )\] Given a pilot test, when conducted',d).group(1)=='x';bad+=['tick mismatch'] if tick!=s['criteria'][0]['passed'] else [];print('AGREE' if not bad else 'MISMATCH: '+', '.join(bad));sys.exit(1 if bad else 0)"
```

## 6. Stage and commit (ask before commit and push)

Stage by explicit path only: `pilot/results/<label>.json`,
`pilot/results/<label>_audit_trail.jsonl`, `.colaberry/progress.json`, `PROGRESS.md`,
`docs/stories/STORY-009.md`, and any cases or code the user said belong to this run.
Show `git diff --staged --stat`.

Draft this commit message, show it, and ask with AskUserQuestion:
**Commit and push to both remotes / Commit only / Leave staged**.
```
STORY-009: record pilot <label> (<PASSED|FAILED>, <rate> errors)

<2-4 lines: reason, wrong cases, what changed since the previous run>

Session: <id>
Tests: <counts>

Story: STORY-009
```
Put `Story: STORY-009` in the final trailer block, with no blank line between it and any
Co-Authored-By line (see the 755925a finding in `scripts/check_story_commits.py`).
Push with `git push colaberry main && git push origin main`. The portal reads `colaberry`.

## 7. Report

End with three lines: the result (errors, rate, pass/fail, changed cases), the records
updated and whether the agreement check said AGREE, and the commit state (hash + pushed,
or what's still staged).
