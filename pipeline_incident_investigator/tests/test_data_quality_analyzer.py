import unittest
from pathlib import Path

from pipeline_incident_investigator.data_quality_analyzer import analyze_data_quality
from pipeline_incident_investigator.data_quality_source import load_incident_data_quality

REPO_ROOT = Path(__file__).resolve().parents[2]


class AnalyzeDataQualityTests(unittest.TestCase):
    def test_flags_row_count_shortfall_between_adjacent_layers(self):
        issues = analyze_data_quality({"bronze_row_count": 100000, "silver_row_count": 100})
        self.assertIn("row_count_shortfall", [i.id for i in issues])

    def test_does_not_flag_row_counts_that_hold_steady(self):
        issues = analyze_data_quality({"bronze_row_count": 100000, "silver_row_count": 99500})
        self.assertNotIn("row_count_shortfall", [i.id for i in issues])

    def test_flags_high_null_rate(self):
        issues = analyze_data_quality({"bronze_row_count": 10000, "null_supplier_id_count": 500})
        self.assertIn("null_rate_high", [i.id for i in issues])

    def test_does_not_flag_low_null_rate(self):
        issues = analyze_data_quality({"bronze_row_count": 10000, "null_supplier_id_count": 5})
        self.assertNotIn("null_rate_high", [i.id for i in issues])

    def test_flags_high_duplicate_rate(self):
        issues = analyze_data_quality({"bronze_row_count": 10000, "duplicate_order_id_count": 50})
        self.assertIn("duplicate_rate_high", [i.id for i in issues])

    def test_does_not_flag_low_duplicate_rate(self):
        issues = analyze_data_quality({"bronze_row_count": 10000, "duplicate_order_id_count": 2})
        self.assertNotIn("duplicate_rate_high", [i.id for i in issues])

    def test_flags_unexpected_and_missing_columns(self):
        issues = analyze_data_quality(
            {"unexpected_columns": ["customer_category"], "missing_expected_columns": ["customer_type"]}
        )
        self.assertIn("schema_drift", [i.id for i in issues])

    def test_does_not_flag_when_columns_match(self):
        issues = analyze_data_quality({"unexpected_columns": [], "missing_expected_columns": []})
        self.assertNotIn("schema_drift", [i.id for i in issues])

    def test_flags_freshness_violation(self):
        issues = analyze_data_quality({"freshness_hours_actual": 51, "freshness_hours_expected": 24})
        self.assertIn("freshness_violation", [i.id for i in issues])

    def test_does_not_flag_when_data_is_fresh(self):
        issues = analyze_data_quality({"freshness_hours_actual": 20, "freshness_hours_expected": 24})
        self.assertNotIn("freshness_violation", [i.id for i in issues])

    def test_empty_metrics_reports_no_issues(self):
        self.assertEqual(analyze_data_quality({}), [])

    def test_real_fixture_one_flags_the_row_collapse_and_the_schema_drift(self):
        metrics = load_incident_data_quality(REPO_ROOT / "data_engineering_incident_test.json")["metrics"]
        issues = analyze_data_quality(metrics)

        self.assertEqual({i.id for i in issues}, {"row_count_shortfall", "schema_drift"})

    def test_real_fixture_two_flags_shortfall_nulls_and_staleness(self):
        metrics = load_incident_data_quality(REPO_ROOT / "data_engineering_incident_test_2.json")["metrics"]
        issues = analyze_data_quality(metrics)

        self.assertEqual(
            {i.id for i in issues}, {"row_count_shortfall", "null_rate_high", "freshness_violation"}
        )

    def test_real_fixture_three_has_no_quality_issues(self):
        metrics = load_incident_data_quality(REPO_ROOT / "data_engineering_incident_test_3.json")["metrics"]
        issues = analyze_data_quality(metrics)

        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
