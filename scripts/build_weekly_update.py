"""Build the weekly stakeholder update (title + body) for .github/workflows/weekly-update.yml.

The workflow runs Claude Code headless (`claude -p "/update-summary last 7 days"
--output-format json`) and hands the JSON result to this script. This script
does the deterministic part:

  - reads Claude's result and fails loudly if Claude reported an error;
  - tidies it with the same formatter as the status-report hook
    (.claude/hooks/format_status_report.py) and refuses to send it if any of
    the seven standard sections is missing;
  - for a week with no commits, skips Claude entirely and writes a short
    "quiet week" note, so stakeholders still hear something;
  - builds a title keyed on the ISO week (e.g. "2026-W39"), which the workflow
    uses as the idempotency key: one issue per week, never two.

Failure modes handled: Claude error or malformed JSON, missing sections, empty
result -- each exits 1 with a message, so nothing half-formed is ever sent and
GitHub emails the repo owner that the run failed. Not handled here: GitHub
API failures (the workflow's `gh` steps own those).

Usage:
  python scripts/build_weekly_update.py --commits N --recipients "@a, @b" \
      [--claude-json result.json] [--date YYYY-MM-DD] --out-title t.txt --out-body b.md
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import date, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "format_status_report", REPO_ROOT / ".claude" / "hooks" / "format_status_report.py"
)
formatter = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(formatter)

FOOTER = (
    "_Sent automatically every Friday by the weekly-update routine, from the project's "
    "own records (commits, PROGRESS.md, story files). Reply here with questions._"
)


class UpdateError(Exception):
    """The update is not fit to send; the message says why."""


def week_title(today: date) -> str:
    monday = today - timedelta(days=today.weekday())
    year, week, _ = today.isocalendar()
    return f"Weekly project update: week of {monday:%b} {monday.day}, {monday.year} ({year}-W{week:02d})"


def summary_from_claude(raw_json: str) -> str:
    try:
        result = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        raise UpdateError(f"Claude's output was not valid JSON ({exc})") from exc
    if not isinstance(result, dict) or result.get("is_error") or result.get("subtype", "success") != "success":
        detail = result.get("subtype") if isinstance(result, dict) else type(result).__name__
        raise UpdateError(f"Claude reported an error instead of a summary ({detail})")
    text = (result.get("result") or "").strip()
    if not text:
        raise UpdateError("Claude returned an empty summary")
    return text


def build_body(summary: str | None, recipients: str, today: date, commits: int) -> str:
    monday = today - timedelta(days=today.weekday())
    header = f"**To:** {recipients}  \n**Covers:** the 7 days to {today:%a %b} {today.day}, {today.year} · {commits} change(s)"
    if commits == 0:
        content = (
            "## The update in one sentence\n\nNo changes were recorded this week "
            f"(week of {monday:%b} {monday.day}).\n\n"
            "## What's next\n\nSee the plan in docs/STORIES.md; next week's update will report progress."
        )
    else:
        if summary is None:
            raise UpdateError("a week with commits needs Claude's summary")
        content = formatter.format_report(summary).strip()
        first_section = content.find("## ")
        if first_section > 0:  # drop chatter like "Here's the summary:" before the report itself
            content = content[first_section:]
        missing = formatter.missing_sections(content + "\n")
        if missing:
            raise UpdateError(f"summary is missing sections: {', '.join(missing)}")
    return f"{header}\n\n{content}\n\n---\n\n{FOOTER}\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--commits", type=int, required=True)
    parser.add_argument("--recipients", required=True)
    parser.add_argument("--claude-json", type=Path)
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--out-title", type=Path, required=True)
    parser.add_argument("--out-body", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        summary = None
        if args.commits > 0:
            if args.claude_json is None:
                raise UpdateError("--claude-json is required when there are commits")
            summary = summary_from_claude(args.claude_json.read_text(encoding="utf-8"))
        body = build_body(summary, args.recipients.strip(), args.date, args.commits)
    except (UpdateError, OSError) as exc:
        print(f"build_weekly_update: not sending ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1

    args.out_title.write_text(week_title(args.date) + "\n", encoding="utf-8")
    args.out_body.write_text(body, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
