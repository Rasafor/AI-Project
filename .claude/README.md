# Automation in this repo: one command, one hook, one CI reviewer

**▶ [Watch the walkthrough recording](../artifacts/week-08/data-pipeline-incident-pilot-automation.mp4)**
One push, recorded end to end: the command records a pilot run, the hook blocks a bad commit by itself, and the CI reviewer comments on the pushed commit.
*GitHub plays the video on the file's own page. A video committed to the repo doesn't play inside a README.*

| | What it is | What triggers it | Where it lives |
|---|---|---|---|
| **Command** | `/record-pilot-run` | You type it in Claude Code | [`commands/record-pilot-run.md`](commands/record-pilot-run.md) |
| **Hook** | Story-commit guard | Fires by itself before every Bash command Claude runs; acts only on `git commit` | [`hooks/story_commit_guard.py`](hooks/story_commit_guard.py), wired in [`settings.json`](settings.json) |
| **CI reviewer** | Push review workflow | Every `git push`, any branch, in each GitHub repo you push to | [`../.github/workflows/push-review.yml`](../.github/workflows/push-review.yml) |

---

## The command: `/record-pilot-run [label] [why]`

It records one STORY-009 pilot run end to end, so the three records can't drift apart. Before this command, that drift took follow-up fix commits to correct.

1. **Asks** for a run label and the reason for the run if you didn't give them. It refuses a label that was already used, because results are recorded once.
2. **Pre-flight:** stops if pilot cases are uncommitted, since cases are committed before the run. Also stops if any test suite fails.
3. **Runs** `scripts/run_pilot.py` and checks the audit trail's hash chain independently.
4. **Compares** the result with the previous run, case by case. If a criterion's pass/fail should flip, it **asks you** first rather than changing it silently.
5. **Updates** `.colaberry/progress.json`, `PROGRESS.md` and `docs/stories/STORY-009.md` from the same numbers, then runs an agreement check that must print `AGREE`.
6. **Stages files by explicit path.** Then it shows you the commit message and asks: commit and push to both remotes, commit only, or leave staged.

## The hook: story-commit guard

It **blocks** a commit, with the reason shown, when:

- **Any commit:**
  - A leftover file is staged: `.colaberry/.colaberry/…`, `copy*`, `old_*`, `*.bak`, `*.orig` or `*~`.
  - A file under `.colaberry/` is UTF-16, which is the `connect.txt` bug.
  - The commit changes work (any path outside `.colaberry/`, `artifacts/` and `PROGRESS.md`) without a new, complete PROGRESS.md entry in the staged lines. A complete entry has `- [x]` or `- [ ]`, a real `Date:`, `Session: CC-YYYYMMDD-xxxx`, `What changed:`, and for `[x]`, a `Verification:` that isn't a placeholder (TBD, TODO, pending, n/a, "will test…"). Re-pasting an already-committed entry doesn't count. ([`hooks/progress_entry_check.py`](hooks/progress_entry_check.py))
- **A commit naming `STORY-nnn`:**
  - `progress.json`, `PROGRESS.md` or `docs/stories/STORY-nnn.md` isn't staged.
  - `PROGRESS.md`'s new lines don't mention the story.
  - A story-doc checkbox disagrees with that criterion's `passed` flag.
  - It compares the staged versions, not your working files.
- It also refuses `git add … && git commit` on one line, and `git commit -a`. In both cases it can't see what will actually be committed.

**Read-only, narrowed:**
- It can only start `git diff`, `git show` or `git ls-files`, with no shell.
- Git runs with no configured programs (`--no-ext-diff --no-textconv`, fsmonitor off) and no network (`protocol.allow=never`, `GIT_NO_LAZY_FETCH`).
- Git gets only a minimal environment, never your tokens.
- Index locking is off. A test hashes every file in the repo, including `.git`, before and after a run.

**Fails closed:**
- A problem it can't check or an internal crash returns exit 2.
- `settings.json` ends the command with `|| exit 2`, so a missing `python`, a missing hook file or an import error also blocks. Claude Code would let any other exit code through.
**Does not check:**
- Whether a criterion is really met. It only checks that the records agree.
- The wording of notes, or whether a `Verification:` line is true. It only checks that one is there and isn't a placeholder.
- Whether the PROGRESS entry describes *this* change. Any new complete entry satisfies it.
- Bash commands that run longer than the 30-second hook timeout. Claude Code treats a timeout as non-blocking.
- Commits you make in your own terminal. It only sees commits Claude runs.

Tests: `python -m unittest tests.test_story_commit_guard tests.test_progress_entry_gate` (44 tests).

## The CI reviewer: push review

On every push, it checks **only what that push changed** and leaves **one comment on the pushed commit**:

| # | Check | Fails the run? |
|---|---|---|
| 1 | Secret scan of the pushed commits (gitleaks 8.30.1, checksum verified) | Yes |
| 2 | Style rules (`ruff`, per `ruff.toml`) on changed Python files | Yes |
| 3 | File-size limit: no changed Python file over 500 lines | Yes |
| 4 | Test suites (same list as `pr-standards.yml`) | Yes |
| 5 | Story commits carry a parseable `Story: STORY-nnn` trailer | Only for an unknown story id |
| 6 | Claude reads the diff and lists real problems, then gives a verdict | No, advice only |

- **Never a silent pass:** a check that couldn't run shows as **"did not run"**, never as passed.
- **Kept apart:** the job that runs your code has a read-only token. A second job posts the comment; it never runs repo code and never sees the API key.
- **Setup for check 6:** add the `ANTHROPIC_API_KEY` repository secret in Git Bash, and paste the key when prompted:
  `gh secret set ANTHROPIC_API_KEY -R Rasafor/Data-Engineer-Incident-Report`.
  Without it, check 6 is skipped and the comment says so.
- **Does not check:**
  - Code the push didn't change.
  - History before the push. Tokens committed before this workflow existed, like the MCP Inspector token in the week-05 PDF, aren't rescanned.
  - Anything inside binary files like PDFs, videos and images.
- **Time:** about 2–3 minutes per push, running in the background.
