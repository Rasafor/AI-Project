import unittest
from pathlib import Path

from pipeline_incident_investigator.log_source import load_incident_logs
from pipeline_incident_investigator.pattern_matcher import MatchedPattern, match_patterns
from pipeline_incident_investigator.recommendation import (
    RecommendationGenerationError,
    generate_recommendation,
)
from pipeline_incident_investigator.tests.fixtures import CLEAN_LOGS

REPO_ROOT = Path(__file__).resolve().parents[2]


class GenerateRecommendationTests(unittest.TestCase):
    def test_recommends_action_for_schema_mismatch_incident(self):
        logs = load_incident_logs(REPO_ROOT / "data_engineering_incident_test.json")
        recommendation = generate_recommendation(match_patterns(logs))

        self.assertIsNotNone(recommendation)
        self.assertEqual(recommendation.category, "Schema Change")
        self.assertTrue(recommendation.recommended_action)
        self.assertTrue(recommendation.evidence)

    def test_recommends_action_for_resource_exhaustion_incident(self):
        logs = load_incident_logs(REPO_ROOT / "data_engineering_incident_test_2.json")
        recommendation = generate_recommendation(match_patterns(logs))

        self.assertIsNotNone(recommendation)
        self.assertEqual(recommendation.category, "Resource Exhaustion")
        self.assertTrue(recommendation.recommended_action)
        self.assertTrue(recommendation.evidence)

    def test_no_recommendation_when_no_pattern_matched(self):
        recommendation = generate_recommendation(match_patterns(CLEAN_LOGS))
        self.assertIsNone(recommendation)

    def test_raises_when_matched_pattern_has_no_configured_action(self):
        unconfigured_match = MatchedPattern(
            id="unknown_pattern",
            category="Unknown",
            description="A pattern with no recommended action wired up.",
            evidence=["some log line"],
        )
        with self.assertRaises(RecommendationGenerationError):
            generate_recommendation([unconfigured_match])


if __name__ == "__main__":
    unittest.main()
