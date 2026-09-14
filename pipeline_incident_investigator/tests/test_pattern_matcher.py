import unittest
from pathlib import Path

from pipeline_incident_investigator.log_source import load_incident_logs
from pipeline_incident_investigator.pattern_matcher import match_patterns
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


if __name__ == "__main__":
    unittest.main()
