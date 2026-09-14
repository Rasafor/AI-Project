import json
import tempfile
import unittest
from pathlib import Path

from pipeline_incident_investigator.data_quality_source import (
    DataQualityInfoMissingError,
    DataQualitySourceUnavailableError,
    load_incident_data_quality,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class LoadIncidentDataQualityTests(unittest.TestCase):
    def test_loads_metrics_from_fixture_one(self):
        result = load_incident_data_quality(REPO_ROOT / "data_engineering_incident_test.json")

        self.assertEqual(result["incident_id"], "INC-2026-001")
        self.assertEqual(result["metrics"]["silver_row_count"], 0)
        self.assertEqual(result["metrics"]["unexpected_columns"], ["customer_category"])

    def test_loads_metrics_from_fixture_two(self):
        result = load_incident_data_quality(REPO_ROOT / "data_engineering_incident_test_2.json")

        self.assertEqual(result["metrics"]["gold_row_count_actual"], 334892)
        self.assertEqual(result["metrics"]["freshness_hours_actual"], 51)

    def test_loads_sparse_metrics_from_fixture_three(self):
        # Fixture 3's connection-timeout incident never reached data extraction, so its
        # data_quality_checks is sparse (no nulls/duplicates/freshness fields at all) --
        # but it is still a non-empty dict, so the loader succeeds. Whether that sparse
        # data amounts to "no issues" is the analyzer's call, not the loader's.
        result = load_incident_data_quality(REPO_ROOT / "data_engineering_incident_test_3.json")

        self.assertIsNone(result["metrics"]["source_row_count"])
        self.assertEqual(result["metrics"]["bronze_row_count"], 0)

    def test_missing_file_raises_source_unavailable(self):
        with self.assertRaises(DataQualitySourceUnavailableError):
            load_incident_data_quality(REPO_ROOT / "does_not_exist.json")

    def test_non_json_file_raises_source_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incident.json"
            path.write_text("not json")
            with self.assertRaises(DataQualitySourceUnavailableError):
                load_incident_data_quality(path)

    def test_missing_data_quality_checks_key_raises_info_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incident.json"
            path.write_text(json.dumps({"incident_id": "INC-TEST"}))
            with self.assertRaises(DataQualityInfoMissingError):
                load_incident_data_quality(path)

    def test_empty_data_quality_checks_raises_info_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incident.json"
            path.write_text(json.dumps({"incident_id": "INC-TEST", "data_quality_checks": {}}))
            with self.assertRaises(DataQualityInfoMissingError):
                load_incident_data_quality(path)


if __name__ == "__main__":
    unittest.main()
