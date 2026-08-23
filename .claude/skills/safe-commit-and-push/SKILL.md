---
name: safe-commit-and-push
description: Use when the user asks to save, commit, back up, or push their code changes to GitHub — e.g. "save my work," "back this up," "push my changes," "put this on GitHub." Reviews what changed, scans new/modified files for secrets before staging, stages files explicitly, writes a plain-language commit message, and pushes. Do NOT use for first-time repository setup (creating a new GitHub repo, wiring up a remote for the first time) or for advanced/destructive operations like resolving merge conflicts, rebasing, or force-pushing — those need explicit human judgment calls, not this checklist.
---

# Safe Commit and Push

## When to use
Trigger this skill when the user asks to:
- Save or commit their current work.
- Push changes to GitHub / "put this online" / "back this up."
- Check what's changed and get it published in one step.

## When NOT to use
Do not trigger for:
- Setting up a brand-new repository or connecting a remote for the first time (that's a one-time setup task, not a routine save).
- Merge conflicts, rebasing, or force-push scenarios — these can discard work and need a human decision at each step, not an automated checklist.
- Anything involving production credentials or secrets management beyond the scan in step 2.

## Procedure
1. Run `git status` to see exactly what's modified and what's untracked. Never assume — always look first.
2. Scan every new or modified file for secret-like patterns (API keys, passwords, tokens, private keys) before anything is staged. If anything looks sensitive, stop and flag it to the user instead of staging it.
3. Stage files by explicit path (never `git add -A` or `git add .`), so nothing unexpected rides along.
4. Write a plain-language commit message describing what changed and, where known, why.
5. Commit, then `git push`.
6. Verify the push landed (`git log` / `git status` against the remote) before telling the user it's done.

## Output format
Narrate each step in plain language as it happens — no unexplained git jargon. Close with one short paragraph: what was saved, and where to view it (repo URL or file path).

## Constraints
- Never force-push or discard uncommitted work without explicit confirmation.
- Never stage a file after a secret-like pattern has been flagged in it, until the user confirms it's safe or the secret is removed.
- Prefer asking a clarifying question over guessing when `git status` shows unfamiliar files that don't obviously belong to the requested change.
