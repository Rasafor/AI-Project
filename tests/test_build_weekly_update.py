"""Tests for scripts/build_weekly_update.py (the weekly stakeholder update routine).

Loaded by path since /scripts has no __init__.py.
"""

import importlib.util
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("build_weekly_update", REPO_ROOT / "scripts" / "build_weekly_update.py")
weekly = importlib.util.module_from_spec(spec)
spec.loader.exec_module(weekly)

FRIDAY = date(2026, 9, 25)
GOOD_SUMMARY = "\n".join(
    f"**{name}**: something true about {name.lower()}." for name in weekly.formatter.REQUIRED_SECTIONS
)


def claude_json(result, **extra):
    return json.dumps({"type": "result", "subtype": "success", "is_error": False, "result": result, **extra})


class TitleTests(unittest.TestCase):
    def test_title_names_the_monday_and_iso_week(self):
        self.assertEqual(weekly.week_title(FRIDAY), "Weekly project update: week of Sep 21, 2026 (2026-W39)")

    def test_same_week_always_gives_the_same_title(self):
        # The title is the idempotency key: a rerun any day that week must match.
        self.assertEqual(weekly.week_title(date(2026, 9, 21)), weekly.week_title(date(2026, 9, 27)))
        self.assertNotEqual(weekly.week_title(date(2026, 9, 27)), weekly.week_title(date(2026, 9, 28)))

    def test_year_boundary_uses_iso_week_year(self):
        self.assertIn("(2026-W53)", weekly.week_title(date(2027, 1, 1)))


class BodyTests(unittest.TestCase):
    def test_busy_week_is_formatted_with_all_sections(self):
        body = weekly.build_body(GOOD_SUMMARY, "@Rasafor", FRIDAY, commits=4)
        self.assertTrue(body.startswith("**To:** @Rasafor  \n**Covers:** the 7 days to Fri Sep 25, 2026 · 4 change(s)"))
        for name in weekly.formatter.REQUIRED_SECTIONS:
            self.assertIn(f"## {name}\n", body)
        self.assertTrue(body.rstrip().endswith("Reply here with questions._"))

    def test_chatter_before_the_first_section_is_dropped(self):
        body = weekly.build_body("Here's the summary you asked for:\n\n" + GOOD_SUMMARY, "@Rasafor", FRIDAY, 4)
        self.assertNotIn("Here's the summary", body)
        self.assertIn("change(s)\n\n## The update in one sentence\n", body)

    def test_quiet_week_needs_no_claude_summary(self):
        body = weekly.build_body(None, "@Rasafor", FRIDAY, commits=0)
        self.assertIn("No changes were recorded this week (week of Sep 21).", body)

    def test_summary_missing_sections_is_refused(self):
        with self.assertRaisesRegex(weekly.UpdateError, "missing sections: .*Risks and open items"):
            weekly.build_body("**Why it matters**: speed.", "@Rasafor", FRIDAY, commits=2)


class ClaudeOutputTests(unittest.TestCase):
    def test_reads_the_result_text(self):
        self.assertEqual(weekly.summary_from_claude(claude_json("  hello  ")), "hello")

    def test_rejects_errors_empty_results_and_bad_json(self):
        cases = [
            claude_json("partial", is_error=True),
            claude_json("x", subtype="error_max_turns"),
            claude_json("   "),
            "not json",
            "[]",
        ]
        for raw in cases:
            with self.subTest(raw=raw), self.assertRaises(weekly.UpdateError):
                weekly.summary_from_claude(raw)


class MainTests(unittest.TestCase):
    def run_main(self, tmp, commits, result_json=None):
        args = ["--commits", str(commits), "--recipients", " @Rasafor ", "--date", "2026-09-25",
                "--out-title", str(tmp / "title.txt"), "--out-body", str(tmp / "body.md")]
        if result_json is not None:
            (tmp / "claude.json").write_text(result_json, encoding="utf-8")
            args += ["--claude-json", str(tmp / "claude.json")]
        err = io.StringIO()
        with redirect_stderr(err):
            code = weekly.main(args)
        return code, err.getvalue()

    def test_happy_path_writes_title_and_body(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.assertEqual(self.run_main(tmp, 3, claude_json(GOOD_SUMMARY)), (0, ""))
            self.assertIn("(2026-W39)", (tmp / "title.txt").read_text(encoding="utf-8"))
            self.assertIn("**To:** @Rasafor  \n", (tmp / "body.md").read_text(encoding="utf-8"))

    def test_running_twice_gives_identical_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self.run_main(tmp, 3, claude_json(GOOD_SUMMARY))
            first = (tmp / "body.md").read_text(encoding="utf-8")
            self.run_main(tmp, 3, claude_json(GOOD_SUMMARY))
            self.assertEqual((tmp / "body.md").read_text(encoding="utf-8"), first)

    def test_failure_writes_nothing_and_explains(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            code, err = self.run_main(tmp, 3, claude_json("**Why it matters**: speed."))
            self.assertEqual(code, 1)
            self.assertIn("not sending (UpdateError): summary is missing sections", err)
            self.assertFalse((tmp / "body.md").exists())

    def test_busy_week_without_claude_output_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, err = self.run_main(Path(tmp), 3)
            self.assertEqual(code, 1)
            self.assertIn("--claude-json is required", err)


if __name__ == "__main__":
    unittest.main()
