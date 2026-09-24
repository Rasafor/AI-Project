import unittest

from scripts.check_story_commits import Commit, check_commit, load_plan, load_progress, main, read_commits

PLAN = {"STORY-001": ["Given X, then Y."]}
TICKED = {"STORY-001": {"criteria": [{"text": "Given X, then Y.", "passed": True}]}}
TRAILER_BODY = "STORY-001: add thing\n\nDetails.\n\nStory: STORY-001\nCo-Authored-By: A <a@example.com>"


def _commit(subject="STORY-001: add thing", body=TRAILER_BODY, trailers=("STORY-001",)):
    return Commit(sha="abcdef1234", subject=subject, body=body, trailer_stories=trailers)


def _messages(findings):
    return [(f.level, f.message) for f in findings]


class CheckCommitTests(unittest.TestCase):
    def test_well_formed_story_commit_has_no_findings(self):
        self.assertEqual(check_commit(_commit(), PLAN, TICKED), [])

    def test_non_story_commit_is_ignored(self):
        commit = _commit(subject="Fix typo", body="Fix typo", trailers=())
        self.assertEqual(check_commit(commit, PLAN, TICKED), [])

    def test_unknown_story_is_an_error(self):
        commit = _commit(subject="STORY-999: x", body="STORY-999: x\n\nStory: STORY-999", trailers=("STORY-999",))
        findings = check_commit(commit, PLAN, TICKED)
        self.assertIn("error", [f.level for f in findings])
        self.assertIn("not in .colaberry/plan.json", findings[0].message)

    def test_subject_without_story_line_warns(self):
        commit = _commit(body="STORY-001: add thing\n\nDetails.", trailers=())
        (level, message), = _messages(check_commit(commit, PLAN, TICKED))
        self.assertEqual(level, "warning")
        self.assertIn("no 'Story: STORY-001' line", message)

    def test_story_line_outside_trailer_block_warns(self):
        body = "STORY-001: add thing\n\nStory: STORY-001\n\nCo-Authored-By: A <a@example.com>"
        (level, message), = _messages(check_commit(_commit(body=body, trailers=()), PLAN, TICKED))
        self.assertEqual(level, "warning")
        self.assertIn("not in the final trailer block", message)

    def test_mismatched_subject_and_trailer_warns(self):
        plan = {**PLAN, "STORY-002": ["Z"]}
        progress = {**TICKED, "STORY-002": {"criteria": [{"text": "Z", "passed": True}]}}
        commit = _commit(body="STORY-001: x\n\nStory: STORY-002", trailers=("STORY-002",))
        messages = [m for _, m in _messages(check_commit(commit, plan, progress))]
        self.assertTrue(any("trailer names STORY-002" in m for m in messages))

    def test_no_ticked_criteria_warns(self):
        progress = {"STORY-001": {"criteria": [{"text": "Given X, then Y.", "passed": False}]}}
        messages = [m for _, m in _messages(check_commit(_commit(), PLAN, progress))]
        self.assertTrue(any("no criteria ticked" in m for m in messages))

    def test_story_missing_from_progress_warns_instead_of_crashing(self):
        messages = [m for _, m in _messages(check_commit(_commit(), PLAN, {}))]
        self.assertTrue(any("no criteria ticked" in m for m in messages))

    def test_invented_criteria_warn(self):
        progress = {"STORY-001": {"criteria": [{"text": "Given X, then Y.", "passed": True},
                                               {"text": "My own extra criterion", "passed": True}]}}
        messages = [m for _, m in _messages(check_commit(_commit(), PLAN, progress))]
        self.assertTrue(any("not in the plan" in m for m in messages))


class RealHistoryTests(unittest.TestCase):
    """Runs against this repo's real commits and .colaberry files (needs full git history)."""

    def setUp(self):
        self.plan, self.progress = load_plan(), load_progress()

    def _check(self, sha):
        (commit,) = read_commits(f"{sha}~1..{sha}")
        return check_commit(commit, self.plan, self.progress)

    def test_story_008_commit_is_clean(self):
        self.assertEqual(self._check("73080fe"), [])

    def test_story_007_commit_lacks_story_line(self):
        messages = [f.message for f in self._check("e7959ea")]
        self.assertTrue(any("no 'Story: STORY-007' line" in m for m in messages))

    def test_story_002_line_is_outside_trailer_block(self):
        messages = [f.message for f in self._check("755925a")]
        self.assertTrue(any("not in the final trailer block" in m for m in messages))

    def test_rerun_gives_identical_findings(self):
        self.assertEqual(self._check("755925a"), self._check("755925a"))

    def test_bad_git_range_exits_2_instead_of_crashing(self):
        self.assertEqual(main(["check_story_commits.py", "no-such-ref..HEAD"]), 2)


if __name__ == "__main__":
    unittest.main()
