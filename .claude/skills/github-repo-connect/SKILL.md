---
name: github-repo-connect
description: Use when a user wants to connect an existing local project to GitHub for the first time, or when git push/git ls-remote fails with "repository not found," "no upstream branch," or another first-connection error. Confirms account/repo status, corrects the remote URL, fixes local git identity, scans pending changes for secrets, and completes the first push — explaining each step in plain language for non-technical users. Do NOT use for routine day-to-day saves on an already-connected repo (use safe-commit-and-push for that), and do NOT use for merge conflicts, rebasing, or force-push recovery — those need a human judgment call, not this checklist.
allowed-tools: Bash, Read, Grep, AskUserQuestion
---

# GitHub Repo Connect

## When to use
Trigger this skill when the user asks to:
- Connect a local project to GitHub for the first time.
- Fix a `git push` that fails with "repository not found," "does not appear to exist," or "no upstream branch."
- Get their first commit onto GitHub after a repo was just created.

## When NOT to use
Do not trigger for:
- Routine commits on a repo that's already connected and has pushed successfully before — use `safe-commit-and-push`.
- Merge conflicts, rebasing, or recovering from a bad force-push — these need a human decision at each step, not a checklist.

## Required input
- Confirmation of whether the user already has a GitHub account.
- The exact GitHub username and repository name they intend to use (never assume the remote URL already configured is correct — verify it).

## Procedure
1. Check the current state: `git remote -v`, `git status`, `git ls-remote origin` (expect this to fail if nothing is connected yet — that's diagnostic, not an error to panic over).
2. If no GitHub account exists yet, stop and hand the browser-based signup steps to the user in plain language. **Never attempt to create the account or the GitHub repository directly** — both require the user's own email verification, password, and (for repo visibility) an informed choice only they can make.
3. Before recommending public vs. private visibility, scan tracked files for anything that shouldn't go public (internal URLs/IPs, personal emails, credentials) and surface it via `AskUserQuestion` — this is the user's call, not an automatic default.
4. Once the user reports the repo exists, verify it's actually reachable with `git ls-remote <url>` before trusting any username/repo name they gave you.
5. If `git ls-remote` fails, **read `references/troubleshooting.md` before guessing** — most first-connection failures map to a small, known set of causes (e.g. username typo) rather than a genuinely broken setup.
6. Fix local git identity (`git config user.name` / `user.email`) if it's still a placeholder.
7. Scan every new/modified file for secret-like patterns (keys, passwords, tokens) before staging anything.
8. Stage by explicit path (never `git add -A`), commit with a plain-language message, then `git push -u origin <branch>` to set upstream tracking.
9. Verify the push landed (`git log origin/<branch>`, `git status`) and report the live URL back to the user.

## Output format
Narrate each step as it happens in plain language — translate git terms using `references/plain-language-glossary.md` where helpful. Close with a short summary: what's now connected, what was pushed, and the URL to view it.

## Constraints
- Never create a GitHub account or repository on the user's behalf.
- Never guess the fix for a connection error without checking `references/troubleshooting.md` first.
- Never use `git add -A` or `git add .`.
- Never push before completing the secret scan in step 7.
- Flag sensitive-looking content before a public repo goes live, even if the user hasn't asked about visibility.
