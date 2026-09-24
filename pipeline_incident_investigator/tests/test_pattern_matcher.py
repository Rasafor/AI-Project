import json
import unittest
from pathlib import Path

from pipeline_incident_investigator.log_source import load_incident_logs
from pipeline_incident_investigator.pattern_matcher import FOLLOW_UP_WORDINGS, match_patterns
from pipeline_incident_investigator.tests.fixtures import CLEAN_LOGS

REPO_ROOT = Path(__file__).resolve().parents[2]


class MatchPatternsTests(unittest.TestCase):
    def test_matches_schema_mismatch_pattern_in_fixture_one(self):
        logs = load_incident_logs(REPO_ROOT / "data_engineering_incident_test.json")
        matches = match_patterns(logs)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, "schema_mismatch")
        self.assertTrue(any("Cannot resolve column" in line for line in matches[0].evidence))

    def test_matches_resource_exhaustion_pattern_in_fixture_two(self):
        logs = load_incident_logs(REPO_ROOT / "data_engineering_incident_test_2.json")
        matches = match_patterns(logs)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, "resource_exhaustion")
        self.assertTrue(any("ExecutorLostFailure" in line for line in matches[0].evidence))

    def test_no_match_for_logs_with_no_known_pattern(self):
        self.assertEqual(match_patterns(CLEAN_LOGS), [])

    # Rules added after the STORY-009 baseline pilot failed.
    def _categories(self, line):
        return [m.category for m in match_patterns([line])]

    def test_yarn_memory_limit_is_resource_exhaustion(self):
        line = "WARN Container killed by YARN for exceeding memory limits. 10.4 GB of 10 GB physical memory used"
        self.assertEqual(self._categories(line), ["Resource Exhaustion"])

    def test_postgres_missing_column_is_schema_change(self):
        line = 'ERROR psycopg2.errors.UndefinedColumn: column "customer_type" does not exist'
        self.assertEqual(self._categories(line), ["Schema Change"])

    def test_oom_inside_a_config_key_is_not_a_memory_failure(self):
        for line in ("INFO Effective config: memory.oom.kill_disable=false",
                     "INFO Effective config: spark.executor.oom.retry=true"):
            with self.subTest(line=line):
                self.assertEqual(self._categories(line), [])

    def test_bare_oom_still_matches(self):
        self.assertEqual(self._categories("ERROR executor 4 lost: OOM"), ["Resource Exhaustion"])


class FollowUpSpecTests(unittest.TestCase):
    """STORY-009 follow-up 1: the code must learn exactly the committed list, no more and no less."""

    SPEC = json.loads((REPO_ROOT / "pilot" / "pattern_fix_spec.json").read_text(encoding="utf-8"))

    def test_code_wordings_are_exactly_the_committed_spec(self):
        spec = {}
        for addition in self.SPEC["additions"]:
            spec.setdefault(addition["category"], []).append(addition["wording"])
        self.assertEqual({k: list(v) for k, v in FOLLOW_UP_WORDINGS.items()}, spec)

    def test_every_spec_wording_is_recognized_under_its_category(self):
        for addition in self.SPEC["additions"]:
            line = f"ERROR something failed: {addition['wording']} (details)"
            with self.subTest(wording=addition["wording"]):
                self.assertEqual([m.category for m in match_patterns([line])], [addition["category"]])


if __name__ == "__main__":
    unittest.main()
