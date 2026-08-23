# GitHub Connection Troubleshooting

Match the exact error text first; don't skip to a fix without matching a signature below.

## "remote: Repository not found" / "fatal: repository ... not found"
**Most common cause:** the username or repo name in the remote URL doesn't match what actually exists on GitHub. This is a typo/mismatch, not a broken connection or a permissions problem.
**Fix:** ask the user for their exact GitHub username (shown top-right when logged in) and the exact repo name from the URL after creating it. Run `git ls-remote <candidate-url>` to confirm before changing anything. Then `git remote set-url origin <correct-url>`.
**Do not** jump to re-creating the repo or re-authenticating — verify the URL first, it's the more common cause.

## "fatal: 'origin' does not appear to be a git repository"
**Cause:** no remote is configured at all yet.
**Fix:** `git remote add origin <url>` (not `set-url`, since none exists to update).

## "! [rejected] ... failed to push some refs" / "Updates were rejected because the remote contains work that you do not have locally"
**Cause:** the GitHub repo already has a commit locally that doesn't exist (commonly: it was created *with* a README/.gitignore checked, which conflicts with the local project's own history).
**Fix:** do not force-push to resolve this. Explain to the user that the two histories need to be reconciled (`git pull --rebase origin <branch>` or a merge), and confirm with them before running it, since it changes commit history.

## "Authentication failed" / repeated credential prompts
**Cause:** a stale or wrong cached credential in the system's credential manager.
**Fix:** direct the user to their OS credential manager (Windows: Credential Manager app, search "git") to remove the stored `github.com` entry, then retry the push so it re-prompts for fresh login.

## "Permission denied (publickey)"
**Cause:** the remote URL is using the SSH form (`git@github.com:...`) but no SSH key is set up for this machine.
**Fix:** for non-technical users, switch the remote to the HTTPS form (`https://github.com/<user>/<repo>.git`) instead of walking them through SSH key generation — it's simpler and uses the same browser-login credential flow as everything else in this skill.

## Push succeeds but nothing appears on GitHub.com
**Cause:** usually pushed to the wrong branch name (e.g. local `main` vs. an expected `master`, or a typo'd branch in the push command).
**Fix:** `git branch` to confirm the local branch name, and check it against the branch shown on the GitHub repo page before pushing again.
