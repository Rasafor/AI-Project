"""Tests for the PROGRESS.md gate (.claude/hooks/progress_entry_check.py) as wired into
story_commit_guard.py, plus the hook's narrowing and fail-closed guarantees.

Run: python -m unittest tests.test_progress_entry_gate
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.test_story_commit_guard import HOOK, RepoFixture, entry

HOOKS_DIR = HOOK.parent
SETTINGS = HOOKS_DIR.parent / "settings.json"
sys.path.insert(0, str(HOOKS_DIR))
import progress_entry_check as gate  # noqa: E402
import story_commit_guard as guard  # noqa: E402

GOOD = entry("reliability-lab: desk survives duplicate confirms").splitlines()


def lines(text: str) -> list[str]:
    return text.splitlines()


class EntryRules(unittest.TestCase):
    """The pure rule, one wrong result at a time."""

    def test_no_work_needs_no_entry(self):
        self.assertEqual(gate.check([".colaberry/manifest.json", "artifacts/INDEX.md"], []), [])

    def test_complete_entry_passes(self):
        self.assertEqual(gate.check(["reliability-lab/desk.js", "PROGRESS.md"], GOOD), [])

    def test_work_without_progress_md_blocks(self):  # the bfaac1e case
        p = gate.check(["reliability-lab/desk.js", "reliability-lab/README.md"], [])
        self.assertIn("PROGRESS.md is not staged", p[0])

    def test_progress_md_staged_without_an_entry_blocks(self):
        p = gate.check(["x.py", "PROGRESS.md"], ["  - Notes: tweaked wording of an old entry"])
        self.assertIn("adds no `- [x]` entry", p[0])

    def test_done_without_verification_blocks(self):
        bad = [ln for ln in GOOD if "Verification" not in ln]
        self.assertIn("no `Verification:` evidence", " ".join(gate.check(["x.py", "PROGRESS.md"], bad)))

    def test_placeholder_verification_blocks(self):
        for v in ("TBD", "todo", "pending", "n/a", "will test tomorrow", "<test name>"):
            bad = [ln if "Verification" not in ln else f"  - Verification: {v}" for ln in GOOD]
            self.assertIn("placeholder", " ".join(gate.check(["x.py", "PROGRESS.md"], bad)), v)

    def test_missing_or_malformed_session_blocks(self):
        for s in ("", "CC-2026103-ab12", "cc-20261003-ab12", "CC-20261003-AB12", "CC-20261003-abc"):
            bad = [ln if "Session" not in ln else f"  - Session: {s}" for ln in GOOD]
            self.assertTrue(gate.check(["x.py", "PROGRESS.md"], bad), s)

    def test_impossible_dates_block(self):
        bad = [ln if "Date" not in ln else "  - Date: 2026-02-30" for ln in GOOD]
        self.assertIn("not a real", " ".join(gate.check(["x.py", "PROGRESS.md"], bad)))
        bad = [ln if "Session" not in ln else "  - Session: CC-20261399-ab12" for ln in GOOD]
        self.assertIn("impossible date", " ".join(gate.check(["x.py", "PROGRESS.md"], bad)))

    def test_partial_entry_without_verification_is_honest_and_allowed(self):
        partial = ["- [ ] pilot follow-up 4 (fails by one case)"] + [ln for ln in GOOD[1:] if "Verification" not in ln]
        self.assertEqual(gate.check(["x.py", "PROGRESS.md"], partial), [])

    def test_fields_must_belong_to_the_entry(self):
        # fields that sit under an unrelated unindented line do not complete the entry
        bad = ["- [x] new thing", "## Some heading"] + GOOD[1:]
        self.assertTrue(gate.check(["x.py", "PROGRESS.md"], bad))

    def test_repasted_old_entry_blocks(self):
        # found by breaking it on purpose: copying a committed entry satisfied the format check
        committed = "# Progress\n\n" + "\n".join(GOOD) + "\n"
        p = gate.check(["x.py", "PROGRESS.md"], GOOD, committed)
        self.assertIn("only repeats entries already committed", p[0])
        renamed = ["- [x] a genuinely new change"] + GOOD[1:]
        self.assertEqual(gate.check(["x.py", "PROGRESS.md"], renamed, committed), [])

    def test_new_top_level_folder_counts_as_work(self):
        self.assertTrue(gate.check(["brand-new-lab/run.js"], []))


class HookIntegration(RepoFixture):
    """The rule through the real hook against throwaway repos (inherits the repo fixture)."""

    def test_replay_bfaac1e_is_blocked(self):
        self.write("reliability-lab/desk.js", "// changed\n")
        self.git("add", "reliability-lab/desk.js")
        self.assertBlocked(self.run_hook('git commit -m "reliability-lab: desk"'), "PROGRESS.md is not staged")

    def test_entry_in_working_tree_but_not_staged_is_blocked(self):
        self.write("reliability-lab/desk.js", "// changed\n")
        self.write("PROGRESS.md", f"# Progress\n\n{entry()}")  # written, never staged
        self.git("add", "reliability-lab/desk.js")
        self.assertBlocked(self.run_hook('git commit -m "x"'), "PROGRESS.md is not staged")

    def test_repasted_committed_entry_is_blocked_through_the_hook(self):
        self.write("PROGRESS.md", f"# Progress\n\n{entry('old work')}")
        self.git("add", "PROGRESS.md")
        self.git("commit", "-q", "-m", "old")
        self.write("lab/a.js", "1\n")
        self.write("PROGRESS.md", f"# Progress\n\n{entry('old work')}\n{entry('old work')}")
        self.git("add", "lab/a.js", "PROGRESS.md")
        self.assertBlocked(self.run_hook('git commit -m "x"'), "only repeats entries already committed")

    def test_platform_sync_files_alone_pass(self):
        self.write(".colaberry/manifest.json", "{}\n")
        self.git("add", ".colaberry/manifest.json")
        self.assertEqual(self.run_hook('git commit -m "sync"').returncode, 0)

    def test_hook_changes_nothing_on_disk(self):
        """Hash every file in the repo, .git included, around a blocked and an allowed run."""
        def snapshot() -> dict[str, str]:
            return {str(p.relative_to(self.repo)): hashlib.sha256(p.read_bytes()).hexdigest()
                    for p in sorted(self.repo.rglob("*")) if p.is_file()}
        self.write("lab/a.js", "1\n")
        self.git("add", "lab/a.js")
        before = snapshot()
        self.assertBlocked(self.run_hook('git commit -m "x"'), "PROGRESS.md")
        self.write("PROGRESS.md", f"# Progress\n\n{entry()}")
        self.git("add", "PROGRESS.md")
        before = snapshot()
        self.assertEqual(self.run_hook('git commit -m "x"').returncode, 0)
        self.assertEqual(before, snapshot())

    def test_configured_external_diff_program_is_never_run(self):
        """A "read-only" git diff runs diff.external from repo config. The hook must not."""
        marker = self.repo / "PWNED"
        script = self.repo / "ext.py"
        script.write_text(f"open({str(marker)!r}, 'w').write('ran')\n", encoding="utf-8")
        self.git("config", "diff.external", f'"{sys.executable}" "{script}"')
        self.write("lab/a.js", "1\n")
        self.write("PROGRESS.md", f"# Progress\n\n{entry()}")
        self.git("add", "lab/a.js", "PROGRESS.md")
        # sanity: plain git diff in this repo really would run it
        subprocess.run(["git", "diff", "--cached", "--", "PROGRESS.md"], cwd=self.repo, capture_output=True, timeout=30)
        self.assertTrue(marker.exists(), "fixture broken: external diff did not run for plain git")
        marker.unlink()
        self.assertEqual(self.run_hook('git commit -m "x"').returncode, 0)
        self.assertFalse(marker.exists(), "the hook executed a program from git config")


class Narrowing(unittest.TestCase):
    def test_only_read_subcommands_can_start(self):
        for sub in ("commit", "add", "config", "push", "fetch", "update-index", "checkout", "gc"):
            with mock.patch.object(guard.subprocess, "run") as run:
                with self.assertRaises(guard.GuardError):
                    guard.run_git([sub])
                run.assert_not_called()

    def test_git_gets_no_secrets_and_no_network(self):
        secrets = {"GITHUB_TOKEN": "ghp_x", "ANTHROPIC_API_KEY": "sk-x", "AWS_SECRET_ACCESS_KEY": "y"}
        with mock.patch.dict(os.environ, secrets), mock.patch.object(guard.subprocess, "run") as run:
            guard.run_git(["diff", "--cached"])
        argv, env = run.call_args.args[0], run.call_args.kwargs["env"]
        self.assertFalse(set(secrets) & set(env))
        self.assertIn("protocol.allow=never", argv)
        self.assertEqual(env["GIT_NO_LAZY_FETCH"], "1")
        self.assertIn("--no-ext-diff", argv)
        self.assertIn("--no-textconv", argv)
        self.assertFalse(run.call_args.kwargs.get("shell"))


class FailsClosed(unittest.TestCase):
    """Claude Code lets a commit through on any hook exit except 2. Prove every failure is 2."""

    def run_wired(self, project: Path, payload: str) -> subprocess.CompletedProcess:
        command = json.loads(SETTINGS.read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        bash = shutil.which("bash")
        if not bash:
            self.skipTest("bash not on PATH")
        return subprocess.run([bash, "-c", command], input=payload.encode(), capture_output=True, timeout=60,
                              env=dict(os.environ, CLAUDE_PROJECT_DIR=str(project).replace("\\", "/")))

    def test_settings_command_is_fail_closed(self):
        command = json.loads(SETTINGS.read_text())["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        self.assertTrue(command.rstrip().endswith("|| exit 2"), command)

    def test_import_crash_blocks_through_the_real_wiring(self):
        with tempfile.TemporaryDirectory() as tmp:
            hooks = Path(tmp) / ".claude" / "hooks"
            hooks.mkdir(parents=True)
            shutil.copy(HOOK, hooks / HOOK.name)
            (hooks / "progress_entry_check.py").write_text("raise ImportError('simulated broken module')\n")
            r = self.run_wired(Path(tmp), json.dumps({"tool_input": {"command": "git status"}}))
            self.assertEqual(r.returncode, 2, r.stderr.decode())
            bare = subprocess.run([sys.executable, str(hooks / HOOK.name)], input=b"{}", capture_output=True, timeout=60)
            self.assertEqual(bare.returncode, 1, "without `|| exit 2` this crash would have let commits through")

    def test_missing_hook_file_blocks_through_the_real_wiring(self):
        with tempfile.TemporaryDirectory() as tmp:
            r = self.run_wired(Path(tmp), "{}")
            self.assertEqual(r.returncode, 2)

    def test_unexpected_payload_shape_blocks(self):
        r = subprocess.run([sys.executable, str(HOOK)], input=b"[]", capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 2, r.stderr.decode())
        self.assertIn("internal error", r.stderr.decode())


if __name__ == "__main__":
    unittest.main()
