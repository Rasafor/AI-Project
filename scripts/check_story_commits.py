"""Check that story commits give the Colaberry Command Center what it needs.

The platform -- not this script -- sets each story's status (the
`verification` block in .colaberry/progress.json, which docs/DATA_CONTRACT.md
says the platform owns). It does so from pushed commits carrying a
`Story: STORY-nnn` trailer plus the `passed` flags this repo owns. When either
half is missing or wrong, the status silently fails to move. This script
catches that at commit time, instead of weeks later on the dashboard.

Read-only: it never writes progress.json, never touches git history.

Findings per commit:
  ERROR    the Story line names a story that is not in .colaberry/plan.json
  WARNING  the subject names a story but no `Story:` line exists
  WARNING  a `Story:` line exists but not in the final trailer block, so git
           (and possibly the platform) does not parse it as a trailer
  WARNING  the trailer and the subject name different stories
  WARNING  the story has no criteria ticked in progress.json
  WARNING  progress.json lists criteria not in the plan (the platform discards them)

Exit code 1 if any ERROR, else 0. Usage:
  python scripts/check_story_commits.py [<git range>]   (default: HEAD~1..HEAD)
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
GIT_TIMEOUT_SECONDS = 30

_SUBJECT_STORY = re.compile(r"^(STORY-\d{3})\b")
_STORY_LINE = re.compile(r"^Story:\s*(STORY-\d{3})\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Commit:
    sha: str
    subject: str
    body: str
    trailer_stories: tuple[str, ...]  # as parsed by git's own trailer parser


@dataclass(frozen=True)
class Finding:
    level: str  # "error" | "warning"
    sha: str
    message: str


def load_plan(repo_root: Path = REPO_ROOT) -> dict[str, list[str]]:
    """Story id -> acceptance criteria text, from .colaberry/plan.json."""
    plan = json.loads((repo_root / ".colaberry" / "plan.json").read_text(encoding="utf-8"))
    return {s["id"]: list(s.get("acceptance") or []) for s in plan["stories"]}


def load_progress(repo_root: Path = REPO_ROOT) -> dict[str, dict]:
    """Story id -> that story's entry in .colaberry/progress.json."""
    progress = json.loads((repo_root / ".colaberry" / "progress.json").read_text(encoding="utf-8"))
    return {s["id"]: s for s in progress["stories"]}


def read_commits(git_range: str, repo_root: Path = REPO_ROOT) -> list[Commit]:
    """Read commits in a range with git's own trailer parsing. Raises on git failure."""
    fmt = "%H%x1f%s%x1f%(trailers:key=Story,valueonly,separator=%x2C)%x1f%B%x1e"
    result = subprocess.run(
        ["git", "log", f"--format={fmt}", git_range],
        cwd=repo_root, capture_output=True, text=True, encoding="utf-8",
        timeout=GIT_TIMEOUT_SECONDS, check=True,
    )
    commits = []
    for record in result.stdout.split("\x1e"):
        record = record.strip("\n")
        if not record:
            continue
        sha, subject, trailers, body = record.split("\x1f", 3)
        stories = tuple(t.strip() for t in trailers.split(",") if t.strip())
        commits.append(Commit(sha=sha, subject=subject, body=body, trailer_stories=stories))
    return commits


def check_commit(commit: Commit, plan: dict[str, list[str]], progress: dict[str, dict]) -> list[Finding]:
    """Every problem that would stop the platform crediting this commit correctly."""
    short = commit.sha[:7]
    subject_match = _SUBJECT_STORY.match(commit.subject)
    subject_story = subject_match.group(1) if subject_match else None
    line_stories = _STORY_LINE.findall(commit.body)
    named = set(commit.trailer_stories) | set(line_stories)

    if subject_story is None and not named:
        return []  # not a story commit

    findings: list[Finding] = []

    def warn(message: str) -> None:
        findings.append(Finding("warning", short, message))

    for story in sorted(named):
        if story not in plan:
            findings.append(Finding("error", short, f"'Story: {story}' names a story that is not in .colaberry/plan.json"))

    if subject_story and not named:
        warn(f"subject names {subject_story} but there is no 'Story: {subject_story}' line; "
             "the Command Center may not credit this commit")
    elif line_stories and not commit.trailer_stories:
        warn(f"'Story: {line_stories[0]}' is not in the final trailer block; put it in the last "
             "paragraph (next to Co-Authored-By) so it parses as a trailer")
    if subject_story and commit.trailer_stories and subject_story not in commit.trailer_stories:
        warn(f"subject names {subject_story} but the trailer names {', '.join(commit.trailer_stories)}")

    for story in sorted(s for s in named if s in plan):
        entry = progress.get(story)
        criteria = (entry or {}).get("criteria") or []
        if not any(c.get("passed") for c in criteria):
            warn(f"{story} has no criteria ticked in .colaberry/progress.json, so its status cannot move")
        invented = [c["text"] for c in criteria if c.get("text") not in plan[story]]
        if invented:
            warn(f"{story} lists {len(invented)} criteria in progress.json that are not in the plan "
                 "(the platform discards them)")

    return findings


def report(findings: list[Finding], commits_checked: int) -> None:
    """Print findings as GitHub annotations in CI, plain lines locally, plus a summary."""
    in_ci = os.environ.get("GITHUB_ACTIONS") == "true"
    for f in findings:
        print(f"::{f.level}::{f.sha}: {f.message}" if in_ci else f"{f.level.upper()} {f.sha}: {f.message}")

    errors = sum(f.level == "error" for f in findings)
    warnings = len(findings) - errors
    summary = (f"Checked {commits_checked} commit(s): {errors} error(s), {warnings} warning(s). "
               + ("Story statuses can update as expected." if not findings
                  else "Fix the items above so the Command Center credits this work."))
    print(summary)

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as out:
            out.write(f"## Story status check\n\n{summary}\n\n")
            out.writelines(f"- **{f.level}** `{f.sha}`: {f.message}\n" for f in findings)


def main(argv: list[str]) -> int:
    git_range = argv[1] if len(argv) > 1 else "HEAD~1..HEAD"
    try:
        commits = read_commits(git_range)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        print(f"ERROR could not read commits for range {git_range!r}: {exc}", file=sys.stderr)
        return 2

    plan, progress = load_plan(), load_progress()
    findings = [f for c in commits for f in check_commit(c, plan, progress)]
    report(findings, len(commits))
    return 1 if any(f.level == "error" for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
