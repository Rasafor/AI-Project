"""Tests for .claude/hooks/story_commit_guard.py, run against throwaway git repos.

Run: python -m unittest tests.test_story_commit_guard
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "story_commit_guard.py"
CRITERIA = ["Given a log, when analyzed, then a recommendation is generated.",
            "Trust: All activities are logged for audit."]


def progress(passed: list[bool]) -> str:
    story = {"id": "STORY-001", "criteria": [{"text": t, "passed": p} for t, p in zip(CRITERIA, passed)]}
    return json.dumps({"stories": [story]}, indent=2) + "\n"


def story_doc(boxes: list[str]) -> str:
    lines = "\n".join(f"- [{b}] {t}" for b, t in zip(boxes, CRITERIA))
    return f"# STORY-001\n\n## Acceptance\n\n{lines}\n"


class GuardTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name)
        self.git("init", "-q")
        self.git("config", "user.email", "t@example.com")
        self.git("config", "user.name", "t")
        self.write(".colaberry/progress.json", progress([False, False]))
        self.write("PROGRESS.md", "# Progress\n")
        self.write("docs/stories/STORY-001.md", story_doc([" ", " "]))
        self.git("add", ".")
        self.git("commit", "-q", "-m", "seed")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, *args: str) -> None:
        subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, timeout=30)

    def write(self, rel: str, text: str | bytes) -> None:
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(text if isinstance(text, bytes) else text.encode("utf-8"))

    def run_hook(self, command: str) -> subprocess.CompletedProcess:
        payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": command}})
        return subprocess.run([sys.executable, str(HOOK)], input=payload.encode(), cwd=self.repo,
                              capture_output=True, timeout=60, env=dict(os.environ))

    def stage_story(self, passed: list[bool], boxes: list[str], progress_line: str = "- [x] STORY-001 done") -> None:
        self.write(".colaberry/progress.json", progress(passed))
        self.write("docs/stories/STORY-001.md", story_doc(boxes))
        self.write("PROGRESS.md", f"# Progress\n\n{progress_line}\n")
        self.git("add", ".colaberry/progress.json", "docs/stories/STORY-001.md", "PROGRESS.md")

    def assertBlocked(self, result, fragment: str) -> None:
        self.assertEqual(result.returncode, 2, result.stderr.decode())
        self.assertIn(fragment, result.stderr.decode())

    # happy paths
    def test_non_commit_command_is_ignored(self):
        self.assertEqual(self.run_hook("git status").returncode, 0)

    def test_story_commit_with_agreeing_records_is_allowed(self):
        self.stage_story([True, False], ["x", " "])
        r = self.run_hook('git commit -m "STORY-001: add it"')
        self.assertEqual(r.returncode, 0, r.stderr.decode())

    def test_plain_commit_without_story_is_allowed(self):
        self.write("notes.txt", "hi\n")
        self.git("add", "notes.txt")
        self.assertEqual(self.run_hook('git commit -m "notes"').returncode, 0)

    # failure paths
    def test_missing_records_block(self):
        self.write("notes.txt", "hi\n")
        self.git("add", "notes.txt")
        self.assertBlocked(self.run_hook('git commit -m "STORY-001: x"'), "missing staged record(s)")

    def test_doc_box_disagreeing_with_progress_blocks(self):
        # the 4276918 case: progress.json says passed, the story doc still says [ ]
        self.stage_story([True, True], ["x", " "])
        self.assertBlocked(self.run_hook('git commit -m "STORY-001: x"'), "records disagree")

    def test_disagreement_is_named_even_when_progress_json_is_unchanged(self):
        # the real-repo break: only the doc and PROGRESS.md staged; the mismatch must still be named
        self.write(".colaberry/progress.json", progress([True, True]))
        self.write("docs/stories/STORY-001.md", story_doc(["x", "x"]))
        self.git("add", ".")
        self.git("commit", "-q", "-m", "agree")
        self.write("docs/stories/STORY-001.md", story_doc([" ", "x"]))
        self.write("PROGRESS.md", "# Progress\n\n- [ ] STORY-001 note\n")
        self.git("add", "docs/stories/STORY-001.md", "PROGRESS.md")
        r = self.run_hook('git commit -m "STORY-001: x"')
        self.assertBlocked(r, "records disagree")
        self.assertIn("missing staged record(s): .colaberry/progress.json", r.stderr.decode())

    def test_doc_ticked_but_progress_false_blocks(self):
        self.stage_story([False, True], ["x", "x"])
        self.assertBlocked(self.run_hook('git commit -m "STORY-001: x"'), "records disagree")

    def test_working_tree_fix_after_staging_does_not_hide_staged_disagreement(self):
        self.stage_story([True, True], ["x", " "])
        self.write("docs/stories/STORY-001.md", story_doc(["x", "x"]))  # fixed but NOT staged
        self.assertBlocked(self.run_hook('git commit -m "STORY-001: x"'), "records disagree")

    def test_progress_md_entry_for_other_story_blocks(self):
        self.stage_story([True, True], ["x", "x"], progress_line="- [x] STORY-002 done")
        self.assertBlocked(self.run_hook('git commit -m "STORY-001: x"'), "none of its added lines")

    def test_criterion_missing_from_doc_blocks(self):
        self.write(".colaberry/progress.json", progress([True, True]))
        self.write("docs/stories/STORY-001.md", "# STORY-001\n\n## Acceptance\n\n- [x] something else\n")
        self.write("PROGRESS.md", "# Progress\n\n- [x] STORY-001\n")
        self.git("add", ".")
        self.assertBlocked(self.run_hook('git commit -m "STORY-001: x"'), "criterion not in")

    def test_story_id_in_message_file_is_checked(self):
        (self.repo / "msg.txt").write_text("fix\n\nStory: STORY-001\n", encoding="utf-8")
        self.stage_story([True, True], ["x", " "])
        self.assertBlocked(self.run_hook("git commit -F msg.txt"), "records disagree")

    def test_leftover_copy_file_blocks_any_commit(self):
        self.write(".colaberry/copyprogress.json", "{}\n")
        self.git("add", ".colaberry/copyprogress.json")
        self.assertBlocked(self.run_hook('git commit -m "tidy"'), "leftover/backup")

    def test_utf16_colaberry_file_blocks(self):
        self.write(".colaberry/connect.txt", "code".encode("utf-16"))
        self.git("add", ".colaberry/connect.txt")
        self.assertBlocked(self.run_hook('git commit -m "connect"'), "UTF-16")

    def test_add_and_commit_in_one_command_blocks(self):
        self.assertBlocked(self.run_hook('git add . && git commit -m "STORY-001: x"'), "separate command")

    def test_commit_all_flag_is_refused(self):
        self.write("PROGRESS.md", "# Progress\n\nchanged\n")  # tracked, modified, not staged
        self.assertBlocked(self.run_hook('git commit -am "STORY-001: x"'), "not checked")
        self.assertBlocked(self.run_hook('git commit --all -m "notes"'), "not checked")

    def test_message_text_is_not_read_as_flags(self):
        # real false positive, 2026-09-27: a heredoc message saying "refuses commit -a",
        # with an apostrophe, was blocked as if -a were passed
        self.write("notes.txt", "hi\n")
        self.git("add", "notes.txt")
        heredoc = "git commit -q -F - <<'EOF'\nGuard refuses commit -a; a story commit's records\nEOF\n"
        r = self.run_hook(heredoc)
        self.assertEqual(r.returncode, 0, r.stderr.decode())
        self.assertEqual(self.run_hook('git commit -m "explain why git add && commit -a is refused"').returncode, 0)
        self.assertEqual(self.run_hook('echo "run git commit -a later"').returncode, 0)

    def test_real_flags_still_caught_among_message_options(self):
        self.assertBlocked(self.run_hook('git commit -m "tidy" -a'), "not checked")
        self.assertBlocked(self.run_hook('git -C . commit --all -m "x"'), "not checked")
        self.assertBlocked(self.run_hook('git commit -qam "x"'), "not checked")
        self.assertBlocked(self.run_hook("git add x && git commit -F - <<'EOF'\nmsg\nEOF\n"), "separate command")

    def test_outside_a_git_repo_fails_closed(self):
        with tempfile.TemporaryDirectory() as bare:
            payload = json.dumps({"tool_input": {"command": 'git commit -m "x"'}})
            r = subprocess.run([sys.executable, str(HOOK)], input=payload.encode(), cwd=bare,
                               capture_output=True, timeout=60,
                               env=dict(os.environ, GIT_CEILING_DIRECTORIES=str(Path(bare).parent)))
        self.assertBlocked(r, "could not verify")

    def test_hook_does_not_write_the_index(self):
        # read-only: plain `git diff` (the -a path) rewrites .git/index to refresh stat info
        # unless GIT_OPTIONAL_LOCKS=0; `diff --cached` never does, so it would prove nothing.
        index = self.repo / ".git" / "index"
        before = (index.stat().st_mtime_ns, index.read_bytes())
        time.sleep(1.1)
        os.utime(self.repo / "PROGRESS.md")  # stale stat info tempts git to refresh the index
        self.run_hook('git commit -am "STORY-001: x"')
        self.assertEqual(before, (index.stat().st_mtime_ns, index.read_bytes()))

    def test_same_input_twice_gives_same_result(self):
        self.stage_story([True, True], ["x", " "])
        a, b = self.run_hook('git commit -m "STORY-001: x"'), self.run_hook('git commit -m "STORY-001: x"')
        self.assertEqual((a.returncode, a.stderr), (b.returncode, b.stderr))


if __name__ == "__main__":
    unittest.main()
