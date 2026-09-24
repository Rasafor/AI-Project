---
description: Summarize a recent project update in plain language for executives
argument-hint: [STORY-nnn | commit | "last N days"]  (default: the latest commit)
allowed-tools: Bash(git log:*), Bash(git show:*), Read, Grep
---

Produce a one-page, plain-language summary of a recent project update for a
non-technical executive audience. This command is READ-ONLY: do not edit, stage,
commit, or push anything.
# WHY: a summary is a report on work, never a change to it.

1. Decide which update to summarize from `$ARGUMENTS`:
   - A story id (e.g. `STORY-008`): `git log --oneline --grep="Story: $ARGUMENTS"`
   - A commit hash: use that commit.
   - `last N days`: `git log --oneline --since="N days ago"`
   - Empty: the most recent commit, `git log --oneline -1`.
   If nothing matches, STOP and say so plainly. Do not summarize something else instead.
   # WHY: summarizing the wrong update confidently is worse than no summary.

2. Gather the facts, and only from these sources:
   - `git show --stat <commit>` for each commit: what changed and how big it was.
   - The matching entry in `PROGRESS.md`: what changed, how it was verified, and notes.
   - If a story is involved: `docs/stories/<STORY-id>.md` (the goal and acceptance
     criteria) and that story's entry in `.colaberry/progress.json` (which criteria passed).
   # WHY: every claim in the summary must trace back to a record, not to memory.

3. Write the summary using exactly these headings. Keep it under 300 words, use no
   jargon, and briefly explain any unavoidable technical term:
   - **The update in one sentence**: what now exists that didn't before.
   - **Why it matters**: the business benefit, tied to the project goal where it fits
     (e.g. cutting investigation time from 4 hours to 1).
   - **Proof it works**: the evidence in plain terms (e.g. "10 automated checks, all passing").
   - **Risks and open items**: anything not done, assumed, or deferred. Say "None
     recorded" only if the records really list none.
   - **What's next**: the next planned item from `docs/STORIES.md` or `PROGRESS.md`.
   - **Confidence**: the confidence stated in the records, if there is one.
   # WHY: a fixed shape lets executives compare updates week to week at a glance.

4. End with a short "Sources" line listing the commit ids and files you read, so
   anyone can check the summary against the originals.
