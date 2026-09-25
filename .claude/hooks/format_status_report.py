"""PostToolUse hook: tidy a saved project status report into one standard layout.

Fires after Claude's Write or Edit tool. It acts only on status reports:
Markdown files under docs/status/, or any .md file whose name contains
"status-report". Every other file is left untouched.

What it does to a status report:
  1. Turns section labels written as bold text ("**Why it matters**: ...")
     into real "## Why it matters" headings, so every report has the same
     skimmable outline as the /update-summary command.
  2. Uses one bullet style ("- ") everywhere, sets lists apart from the
     sentence above them, and capitalizes text that follows a section label.
  3. Puts one blank line around headings, collapses runs of blank lines,
     strips trailing spaces, and ends the file with exactly one newline.
  4. Leaves code blocks (``` fences) exactly as written.
  5. Checks that all required sections are present. If any are missing it
     exits with code 2, which Claude Code shows to Claude as feedback so it
     adds them. The file is already saved at that point; nothing is blocked.

Idempotent: formatting an already-formatted report changes nothing, and the
file is rewritten only when the formatted text differs.

Failure modes handled: unreadable hook input (exit 1, message on stderr,
shown to the user as a non-blocking error); report file missing or not
UTF-8 (same). Nothing is retried: the hook runs once per save, and a
failure never undoes or blocks the save itself.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# Same headings, same order, as .claude/commands/update-summary.md.
REQUIRED_SECTIONS = [
    "The update in one sentence",
    "Why it matters",
    "Proof it works",
    "Risks and open items",
    "What's next",
    "Confidence",
    "Sources",
]
_CANONICAL = {name.lower(): name for name in REQUIRED_SECTIONS}

_FENCE = re.compile(r"^\s*(```|~~~)")
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
# "**Label**: text", "**Label:** text", "- **Label** - text", "*Label*: text"
_BOLD_LABEL = re.compile(r"^\s*(?:[-*+]\s+)?\*{1,2}(.+?):?\*{1,2}\s*[:–—-]?\s*(.*)$")
_BULLET = re.compile(r"^(\s*)[*+]\s+")
_LIST_ITEM = re.compile(r"^\s*(?:-|\d+[.)])\s+")


def is_status_report(file_path: str) -> bool:
    path = file_path.replace("\\", "/").lower()
    if not path.endswith(".md"):
        return False
    return "/docs/status/" in path or path.startswith("docs/status/") or "status-report" in Path(path).name


def _lookup(label: str) -> str | None:
    key = label.strip().strip("*").rstrip(":").strip().replace("’", "'").lower()
    return _CANONICAL.get(key)


def _as_section(line: str) -> tuple[str, str] | None:
    """Return (canonical section name, trailing text) if the line labels a known section."""
    heading = _HEADING.match(line)
    if heading:
        name = _lookup(heading.group(1))
        return (name, "") if name else None
    label = _BOLD_LABEL.match(line)
    if label:
        name = _lookup(label.group(1))
        return (name, label.group(2).strip()) if name else None
    return None


def format_report(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _FENCE.match(raw):
            in_fence = not in_fence
            lines.append(raw.rstrip())
            continue
        if in_fence:
            lines.append(raw)
            continue
        line = raw.rstrip()
        section = _as_section(line)
        if section:
            name, rest = section
            lines += ["", f"## {name}", ""]
            if rest:
                lines.append(rest[0].upper() + rest[1:])
            continue
        line = _BULLET.sub(r"\1- ", line)
        starts_list = _LIST_ITEM.match(line) and lines and lines[-1] and not _LIST_ITEM.match(lines[-1])
        if starts_list and not lines[-1][0].isspace():
            lines.append("")  # a list reads as a list only when set apart from the sentence above it
        if _HEADING.match(line):
            lines += ["", line, ""]
        else:
            lines.append(line)

    # Collapse blank-line runs (outside code blocks) and trim both ends.
    out: list[str] = []
    in_fence = False
    for line in lines:
        if _FENCE.match(line):
            in_fence = not in_fence
        if not in_fence and line == "" and (not out or out[-1] == ""):
            continue
        out.append(line)
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


def missing_sections(formatted: str) -> list[str]:
    present = {m.group(1).strip() for m in re.finditer(r"^## (.+)$", formatted, re.MULTILINE)}
    return [name for name in REQUIRED_SECTIONS if name not in present]


def main(stdin_text: str) -> int:
    try:
        payload = json.loads(stdin_text)
    except json.JSONDecodeError as exc:
        print(f"format_status_report: hook input was not valid JSON ({exc})", file=sys.stderr)
        return 1
    file_path = (payload.get("tool_input") or {}).get("file_path") or ""
    if not is_status_report(file_path):
        return 0

    path = Path(file_path)
    try:
        original = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        print(f"format_status_report: could not read {file_path} ({type(exc).__name__}: {exc})", file=sys.stderr)
        return 1

    formatted = format_report(original)
    if formatted != original:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(formatted, encoding="utf-8", newline="\n")
        os.replace(tmp, path)  # atomic: a reader never sees a half-written report

    missing = missing_sections(formatted)
    if missing:
        print(
            f"Status report {path.name} is missing these sections: {', '.join(missing)}. "
            "Add them (use 'None recorded' if the records truly have nothing).",
            file=sys.stderr,
        )
        return 2

    if formatted != original:
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": f"format_status_report reformatted {path.name}; re-read it before editing again.",
        }}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.stdin.read()))
