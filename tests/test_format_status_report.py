"""Tests for .claude/hooks/format_status_report.py (the status-report formatting hook).

Loaded by path since .claude/hooks has no __init__.py.
"""

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / ".claude" / "hooks" / "format_status_report.py"

spec = importlib.util.spec_from_file_location("format_status_report", HOOK_PATH)
hook = importlib.util.module_from_spec(spec)
spec.loader.exec_module(hook)

MESSY_REPORT = (
    "# STORY-009 status report   \r\n"
    "\r\n\r\n\r\n"
    "**The update in one sentence**: The pilot now passes.\r\n"
    "**Why it matters:** It is the gate before autonomous operation.\r\n"
    "- **Proof it works** - 0 of 34 cases wrong.\r\n"
    "* 149 package tests pass\r\n"
    "+ 18 script tests pass\r\n"
    "### Risks and open items\r\n"
    "All 34 cases were seen during development.\r\n"
    "**What’s next**: STORY-010.\r\n"
    "**Confidence**: 90%.\r\n"
    "```\r\n"
    "* keep   this   as is\r\n"
    "\r\n\r\n\r\n"
    "```\r\n"
    "*Sources*: commit 7356721, PROGRESS.md\r\n\r\n\r\n"
)


def run_hook(file_path: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = hook.main(json.dumps({"tool_name": "Write", "tool_input": {"file_path": file_path}}))
    return code, out.getvalue(), err.getvalue()


class FormatReportTests(unittest.TestCase):
    def setUp(self):
        self.formatted = hook.format_report(MESSY_REPORT)

    def test_bold_labels_become_standard_headings(self):
        for name in hook.REQUIRED_SECTIONS:
            self.assertIn(f"\n## {name}\n", self.formatted)
        self.assertIn("## Why it matters\n\nIt is the gate before autonomous operation.", self.formatted)
        self.assertIn("## What's next\n\nSTORY-010.", self.formatted)

    def test_bullets_spacing_and_line_endings_are_normalized(self):
        self.assertIn("- 149 package tests pass\n- 18 script tests pass", self.formatted)
        self.assertNotIn("\r", self.formatted)
        self.assertNotIn("   \n", self.formatted)
        self.assertTrue(self.formatted.startswith("# STORY-009 status report\n\n## The update"))
        self.assertTrue(self.formatted.endswith("PROGRESS.md\n"))

    def test_label_text_is_capitalized_and_lists_are_set_apart(self):
        self.assertIn("## Proof it works\n\n0 of 34 cases wrong.\n\n- 149 package tests pass", self.formatted)
        tidy = hook.format_report("**Confidence**: high.\n- one\n  continued\n- two\n")
        self.assertEqual(tidy, "## Confidence\n\nHigh.\n\n- one\n  continued\n- two\n")

    def test_code_blocks_are_left_exactly_as_written(self):
        self.assertIn("```\n* keep   this   as is\n\n\n\n```", self.formatted)

    def test_formatting_twice_changes_nothing(self):
        self.assertEqual(hook.format_report(self.formatted), self.formatted)

    def test_empty_report_lists_every_section_as_missing(self):
        self.assertEqual(hook.missing_sections(hook.format_report("")), hook.REQUIRED_SECTIONS)


class HookEntryPointTests(unittest.TestCase):
    def test_complete_report_is_rewritten_and_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "docs" / "status" / "2026-09-24-STORY-009.md"
            report.parent.mkdir(parents=True)
            report.write_bytes(MESSY_REPORT.encode("utf-8"))

            code, out, err = run_hook(str(report))

            self.assertEqual((code, err), (0, ""))
            self.assertIn("reformatted", json.loads(out)["hookSpecificOutput"]["additionalContext"])
            self.assertEqual(report.read_text(encoding="utf-8"), hook.format_report(MESSY_REPORT))
            # Second run: already tidy, so no rewrite and no message.
            self.assertEqual(run_hook(str(report)), (0, "", ""))

    def test_missing_sections_are_reported_to_claude_with_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = Path(tmp) / "weekly-status-report.md"
            report.write_text("**Why it matters**: saves time.\n", encoding="utf-8")

            code, _, err = run_hook(str(report))

            self.assertEqual(code, 2)
            self.assertIn("The update in one sentence", err)
            self.assertNotIn("Why it matters", err)

    def test_other_files_are_never_touched(self):
        with tempfile.TemporaryDirectory() as tmp:
            other = Path(tmp) / "notes.md"
            other.write_text("* messy   \n\n\n\n", encoding="utf-8")

            self.assertEqual(run_hook(str(other)), (0, "", ""))
            self.assertEqual(other.read_text(encoding="utf-8"), "* messy   \n\n\n\n")

    def test_bad_hook_input_fails_loudly_not_silently(self):
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(hook.main("not json"), 1)
        self.assertIn("not valid JSON", err.getvalue())

    def test_unreadable_report_fails_loudly(self):
        code, _, err = run_hook(str(Path(tempfile.gettempdir()) / "docs" / "status" / "does-not-exist.md"))
        self.assertEqual(code, 1)
        self.assertIn("could not read", err)


if __name__ == "__main__":
    unittest.main()
