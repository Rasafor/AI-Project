"""PreToolUse hook: block a story commit whose records are missing or disagree.

Fires on every Bash tool call; does nothing unless the command runs `git commit`.

For every commit it blocks staged leftovers that were caught late before
(.colaberry/.colaberry/ copies, copy*/old_* backups, *.bak/*.orig/~ files) and
UTF-16 files under .colaberry/ (the connect.txt encoding bug).

When the commit command names STORY-nnn it also requires, in the staged
snapshot (what will actually be committed, not the working tree):
  - .colaberry/progress.json, PROGRESS.md and docs/stories/STORY-nnn.md are staged
  - PROGRESS.md's staged additions mention STORY-nnn
  - every criterion of STORY-nnn in progress.json has a line in the story doc's
    Acceptance section, and each `[x]`/`[ ]` matches that criterion's `passed`

For EVERY commit that stages tracked work it also requires a complete PROGRESS.md
entry in the staged additions (see progress_entry_check.py).

Read-only by construction, and narrowed to the least it needs:
  - git only, argument list (no shell), and only the read subcommands in GIT_READ_ONLY;
    anything else raises before a process starts.
  - no programs from git config: fsmonitor off, and diff runs with --no-ext-diff
    --no-textconv (a "read-only" diff otherwise runs any diff.external/textconv driver
    the repo or user config names).
  - no network: protocol.allow=never and GIT_NO_LAZY_FETCH=1, so a partial clone
    cannot fetch missing objects while the hook reads them.
  - minimal environment: git gets only the variables in KEEP_ENV, never the API or
    GitHub tokens in the session environment.
  - GIT_OPTIONAL_LOCKS=0 so reads never refresh or lock .git/index. The hook writes nothing.

Exit 0 = allow. Exit 2 = block, reason on stderr (shown to Claude). Anything
the hook cannot determine (git fails, unreadable JSON, unparseable command)
also exits 2, including an unexpected crash: Claude Code treats any exit other than 2
as a non-blocking error and lets the commit through, so main() never exits 1.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import sys

from progress_entry_check import check as check_progress_entry

GIT_TIMEOUT_SECONDS = 10
GIT_READ_ONLY = {"diff", "show", "ls-files"}
KEEP_ENV = ("PATH", "PATHEXT", "SYSTEMROOT", "WINDIR", "COMSPEC", "HOME", "USERPROFILE",
            "HOMEDRIVE", "HOMEPATH", "TEMP", "TMP", "LANG", "LC_ALL")
RECORDS = (".colaberry/progress.json", "PROGRESS.md")
JUNK = re.compile(
    r"(^|/)\.colaberry/\.colaberry/"      # nested seed copies (c69d95d)
    r"|(^|/)(copy|old_)[^/]*$"             # copyprogress.json, old_progress_0913.json
    r"|\.(bak|orig)$|~$"
)
STORY_ID = re.compile(r"\bSTORY-\d{3}\b")
COMMIT = re.compile(r"\bgit\b.*\bcommit\b", re.S)  # cheap pre-filter; shell_tokens() decides


class GuardError(Exception):
    """The hook could not establish what is being committed."""


def run_git(args: list[str]) -> subprocess.CompletedProcess:
    """The only way this hook starts a process: a read-only git subcommand, no shell,
    no configured programs, no network, a minimal environment."""
    if not args or args[0] not in GIT_READ_ONLY:
        raise GuardError(f"refusing git {args[:1]}: only {sorted(GIT_READ_ONLY)} are allowed")
    if args[0] == "diff":
        args = ["diff", "--no-ext-diff", "--no-textconv", *args[1:]]
    env = {k: os.environ[k] for k in KEEP_ENV if k in os.environ}
    env.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0")
    return subprocess.run(
        ["git", "-c", "core.fsmonitor=false", "-c", "protocol.allow=never", *args],
        capture_output=True, env=env, timeout=GIT_TIMEOUT_SECONDS, check=False,
    )


def git(*args: str) -> str:
    try:
        out = run_git(list(args))
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GuardError(f"git {' '.join(args)} failed: {type(exc).__name__}: {exc}") from exc
    if out.returncode != 0:
        raise GuardError(f"git {' '.join(args)} exited {out.returncode}: {out.stderr.decode(errors='replace').strip()}")
    return out.stdout.decode("utf-8", errors="replace")


def staged_bytes(path: str) -> bytes:
    try:
        out = run_git(["show", f":{path}"])
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GuardError(f"git show :{path} failed: {type(exc).__name__}: {exc}") from exc
    if out.returncode != 0:
        raise GuardError(f"cannot read staged {path}: {out.stderr.decode(errors='replace').strip()}")
    return out.stdout


HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(\n|$)", re.S)
SHELL_OPS = {"&&", "||", ";", "|", "&", "(", ")", ";;"}
VALUE_OPTS = {"-m", "-F", "-C", "-c", "-t", "--message", "--file", "--author", "--date",
              "--template", "--cleanup", "--fixup", "--squash", "--trailer", "--reuse-message",
              "--reedit-message", "--pathspec-from-file"}


def shell_tokens(command: str) -> list[str]:
    """Tokens of the command with heredoc bodies removed, so message text is never
    mistaken for arguments (a message saying "commit -a" is not the -a flag)."""
    stripped = HEREDOC.sub("<<HEREDOC\n", command)
    lex = shlex.shlex(stripped, posix=True, punctuation_chars=True)
    lex.whitespace_split = True
    try:
        return list(lex)
    except ValueError as exc:
        raise GuardError(f"cannot parse the commit command: {exc}") from exc


def git_invocations(tokens: list[str], sub: str) -> list[list[str]]:
    """Argument lists of every `git [global opts] <sub> ...` in the token stream."""
    found = []
    for i, tok in enumerate(tokens):
        if tok != "git":
            continue
        j = i + 1
        while j < len(tokens) and tokens[j].startswith("-"):
            j += 2 if tokens[j] in ("-C", "-c") else 1
        if j < len(tokens) and tokens[j] == sub:
            k = j + 1
            while k < len(tokens) and tokens[k] not in SHELL_OPS:
                k += 1
            found.append(tokens[j + 1:k])
    return found


def uses_all_flag(args: list[str]) -> bool:
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--all":
            return True
        if a in VALUE_OPTS:
            i += 2
            continue
        if a.startswith("-") and not a.startswith("--"):
            letters = a[1:]
            for n, ch in enumerate(letters):
                if ch == "a":
                    return True
                if ch in "mFCct":  # rest of the cluster (or next token) is this option's value
                    if n == len(letters) - 1:
                        i += 1
                    break
        i += 1
    return False


def commit_message_text(command: str, args: list[str]) -> str:
    """The command text plus any -F <file> message, which is where a story id may live."""
    text = command
    for i, tok in enumerate(args[:-1]):
        if tok in ("-F", "--file") and args[i + 1] != "-":
            with open(args[i + 1], encoding="utf-8", errors="replace") as fh:  # read-only
                text += "\n" + fh.read()
    return text


def files_to_commit(args: list[str]) -> list[str]:
    # `commit -a` would need the working tree, and plain `git diff` rewrites .git/index
    # even with GIT_OPTIONAL_LOCKS=0 (measured). Refuse it rather than write; the repo
    # rule is explicit `git add <path>` anyway.
    if uses_all_flag(args):
        raise GuardError("`git commit -a/--all` is not checked; stage explicit paths with "
                         "`git add <path>` and commit without -a")
    return [f for f in git("diff", "--cached", "--name-only").splitlines() if f]


def check_leftovers(files: list[str]) -> list[str]:
    problems = [f"leftover/backup file staged: {f}" for f in files if JUNK.search(f)]
    staged = set(git("diff", "--cached", "--name-only", "--diff-filter=d").splitlines())
    for f in files:
        if f in staged and f.startswith(".colaberry/") and f.endswith((".txt", ".json")):
            if staged_bytes(f)[:2] in (b"\xff\xfe", b"\xfe\xff"):
                problems.append(f"{f} is UTF-16; the portal reads UTF-8 (the connect.txt bug)")
    return problems


def check_story(story: str, files: list[str]) -> list[str]:
    doc_path = f"docs/stories/{story}.md"
    # Report every problem, not just the first: the agreement check below reads the
    # staged snapshot (index), which exists whether or not a record changed in this commit.
    problems: list[str] = []
    missing = [p for p in (*RECORDS, doc_path) if p not in files]
    if missing:
        problems.append(f"{story} commit is missing staged record(s): {', '.join(missing)}")
    if "PROGRESS.md" in files:
        added = [ln[1:] for ln in git("diff", "--cached", "--", "PROGRESS.md").splitlines()
                 if ln.startswith("+") and not ln.startswith("+++")]
        if not any(story in ln for ln in added):
            problems.append(f"PROGRESS.md is staged but none of its added lines mention {story}")
    tracked = set(git("ls-files", "--", ".colaberry/progress.json", doc_path).splitlines())
    if {".colaberry/progress.json", doc_path} - tracked:
        return problems  # nothing to compare yet; the missing-records line already says so

    try:
        progress = json.loads(staged_bytes(".colaberry/progress.json").decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise GuardError(f"staged .colaberry/progress.json is not valid UTF-8 JSON: {exc}") from exc
    entry = next((s for s in progress.get("stories", []) if s.get("id") == story), None)
    if entry is None:
        return problems + [f"{story} has no entry in staged .colaberry/progress.json"]

    doc = staged_bytes(doc_path).decode("utf-8", errors="replace")
    if "## Acceptance" not in doc:
        return problems + [f"{doc_path} has no '## Acceptance' section"]
    ticks = re.findall(r"^- \[([ xX])\] (.*)$", doc.split("## Acceptance", 1)[1], re.M)
    for c in entry.get("criteria", []):
        match = [t for t, text in ticks if text.startswith(c["text"])]
        if not match:
            problems.append(f"criterion not in {doc_path}: {c['text'][:70]!r}")
        elif (match[0].lower() == "x") != bool(c.get("passed")):
            problems.append(
                f"records disagree on {c['text'][:60]!r}: progress.json passed={c.get('passed')}, "
                f"{doc_path} box is [{match[0]}]")
    return problems


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        print(f"story_commit_guard: unreadable hook input: {exc}", file=sys.stderr)
        return 2
    command = (payload.get("tool_input") or {}).get("command", "")
    if not COMMIT.search(command):
        return 0

    try:
        tokens = shell_tokens(command)
        commits = git_invocations(tokens, "commit")
        if not commits:
            return 0  # "git commit" only appears inside text (a message, an echo), not as a command
        if git_invocations(tokens, "add"):
            raise GuardError("stage with `git add` in a separate command first; this guard checks "
                             "what is staged before the command runs, so it cannot see adds in the same line")
        args = [a for c in commits for a in c]
        files = files_to_commit(args)
        problems = check_leftovers(files)
        for story in sorted(set(STORY_ID.findall(commit_message_text(command, args)))):
            problems += check_story(story, files)
        added = [ln[1:] for ln in git("diff", "--cached", "--", "PROGRESS.md").splitlines()
                 if ln.startswith("+") and not ln.startswith("+++")] if "PROGRESS.md" in files else []
        head = run_git(["show", "HEAD:PROGRESS.md"])  # nonzero: no commit or no file yet
        committed = head.stdout.decode("utf-8", errors="replace") if head.returncode == 0 else ""
        problems += check_progress_entry(files, added, committed)
    except (GuardError, OSError) as exc:
        print(f"story_commit_guard BLOCKED (could not verify): {exc}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - an unexpected bug must block, never fall through to exit 1
        print(f"story_commit_guard BLOCKED (internal error, fix the hook): {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    if problems:
        print("story_commit_guard BLOCKED this commit:\n  - " + "\n  - ".join(problems), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as exc:  # noqa: BLE001 - e.g. a malformed payload; block, never exit 1
        print(f"story_commit_guard BLOCKED (internal error, fix the hook): {type(exc).__name__}: {exc}", file=sys.stderr)
        code = 2
    sys.exit(code)
