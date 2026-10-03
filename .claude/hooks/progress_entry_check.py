"""PROGRESS.md gate for every commit (CLAUDE.md "PROGRESS.md update rule", hard gates 1-3).

Pure functions only: no git, no files, no I/O. story_commit_guard.py reads the staged
snapshot and passes in the staged paths and the lines PROGRESS.md's staged diff adds.

A commit that stages any tracked-work path must also stage PROGRESS.md, and the lines
it adds must contain at least one complete entry:

    - [x] <task>                        ([ ] allowed for honest partial work)
      - Date: YYYY-MM-DD                (a real calendar date)
      - Session: CC-YYYYMMDD-xxxx       (4 lowercase alphanumerics)
      - What changed: <text>
      - Verification: <text>            (required for [x]; no placeholders)

An added entry only counts if its (task line, Session) pair is not already in the
last committed PROGRESS.md: re-pasting or moving an old entry is not a new record.

Paths owned by the platform sync (.colaberry/, artifacts/) and PROGRESS.md itself are
exempt. Everything else counts as work, so a new top-level folder is covered by default.
"""

from __future__ import annotations

import datetime as dt
import re

EXEMPT_PREFIXES = (".colaberry/", "artifacts/")
EXEMPT_FILES = ("PROGRESS.md",)
SESSION = re.compile(r"^CC-(\d{8})-[a-z0-9]{4}$")
PLACEHOLDER = re.compile(r"^(tbd|todo|pending|n/?a|none|-|\.\.\.|<.*>|will (be )?(test|verif)\w*.*)$", re.I)
FIELD = re.compile(r"^\s+- (Date|Session|What changed|Verification|Notes):\s*(.*?)\s*$")
HEAD = re.compile(r"^- \[([ xX])\] (\S.*)$")


def work_paths(files: list[str]) -> list[str]:
    return [f for f in files if f not in EXEMPT_FILES and not f.startswith(EXEMPT_PREFIXES)]


def _entries(added: list[str]) -> list[dict]:
    """Split added lines into entries: a `- [ ]`/`- [x]` head plus the indented fields under it."""
    entries: list[dict] = []
    cur = None
    for line in added:
        h = HEAD.match(line)
        if h:
            cur = {"done": h.group(1).lower() == "x", "title": h.group(2), "fields": {}}
            entries.append(cur)
            continue
        f = FIELD.match(line)
        if cur is not None and f:
            cur["fields"].setdefault(f.group(1), f.group(2))
        elif line.strip() and not line.startswith((" ", "\t")):
            cur = None  # any other unindented line ends the entry
    return entries


def _date_ok(value: str) -> bool:
    try:
        dt.date.fromisoformat(value)
    except ValueError:
        return False
    return bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", value))


def entry_problems(e: dict) -> list[str]:
    f, name, out = e["fields"], e["title"][:50], []
    for key in ("Date", "Session", "What changed"):
        if not f.get(key):
            out.append(f"entry {name!r} has no `{key}:` line (or it is empty)")
    if f.get("Date") and not _date_ok(f["Date"]):
        out.append(f"entry {name!r} Date {f['Date']!r} is not a real YYYY-MM-DD date")
    if f.get("Session"):
        m = SESSION.match(f["Session"])
        if not m:
            out.append(f"entry {name!r} Session {f['Session']!r} is not CC-YYYYMMDD-xxxx")
        elif not _date_ok(f"{m.group(1)[:4]}-{m.group(1)[4:6]}-{m.group(1)[6:]}"):
            out.append(f"entry {name!r} Session {f['Session']!r} has an impossible date")
    if e["done"]:
        v = f.get("Verification", "")
        if not v:
            out.append(f"entry {name!r} is marked [x] with no `Verification:` evidence")
        elif PLACEHOLDER.match(v):
            out.append(f"entry {name!r} is marked [x] but Verification is a placeholder: {v!r}")
    return out


def _key(e: dict) -> tuple[str, str]:
    return (e["title"].strip(), e["fields"].get("Session", ""))


def check(files: list[str], added: list[str], committed: str = "") -> list[str]:
    """Problems with this commit's PROGRESS.md entry; [] means the commit may proceed.
    `committed` is PROGRESS.md as of HEAD ("" when there is none yet)."""
    work = work_paths(files)
    if not work:
        return []
    shown = ", ".join(work[:4]) + (f" (+{len(work) - 4} more)" if len(work) > 4 else "")
    if "PROGRESS.md" not in files:
        return [f"commit changes {shown} but PROGRESS.md is not staged (CLAUDE.md hard gate 3)"]
    old = {_key(e) for e in _entries(committed.splitlines())}
    found = _entries(added)
    entries = [e for e in found if _key(e) not in old]
    if not entries:
        if found:
            return [f"PROGRESS.md only repeats entries already committed ({found[0]['title'][:50]!r}); "
                    f"add a new entry for {shown}"]
        return [f"PROGRESS.md is staged but adds no `- [x]` entry for {shown}"]
    per_entry = [entry_problems(e) for e in entries]
    if any(not p for p in per_entry):
        return []  # at least one complete entry covers the commit
    return [p for ps in per_entry for p in ps]
