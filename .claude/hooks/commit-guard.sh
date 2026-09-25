#!/usr/bin/env bash
# PreToolUse hook. NOT wired into settings.json yet.
python3 -c '
import json
import sys

payload = json.load(sys.stdin)
command = payload.get("tool_input", {}).get("command", "")

if "git push --force" in command or "rm -rf /" in command:
    print(f"commit-guard: blocked - command matches a forbidden pattern: {command!r}", file=sys.stderr)
    sys.exit(2)

sys.exit(0)
'
