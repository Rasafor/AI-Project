import tempfile
import unittest
from pathlib import Path

from pipeline_incident_investigator.sql_source import (
    SqlInfoMissingError,
    SqlSourceUnavailableError,
    load_incident_sql,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class LoadIncidentSqlTests(unittest.TestCase):
    def test_loads_query_and_current_schema_from_fixture_one(self):
        sql = load_incident_sql(REPO_ROOT / "data_engineering_incident_test.json")

        self.assertIn("customer_type", sql["query"])
        self.assertIsInstance(sql["current_schema_columns"], list)
        self.assertIn("customer_category", sql["current_schema_columns"])
        self.assertNotIn("customer_type", sql["current_schema_columns"])

    def test_loads_query_with_no_schema_history_from_fixture_two(self):
        sql = load_incident_sql(REPO_ROOT / "data_engineering_incident_test_2.json")

        self.assertTrue(sql["query"])
        self.assertIsNone(sql["current_schema_columns"])

    def test_missing_file_raises_sql_source_unavailable(self):
        with self.assertRaises(SqlSourceUnavailableError):
            load_incident_sql(REPO_ROOT / "does_not_exist.json")

    def test_non_json_file_raises_sql_source_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incident.json"
            path.write_text("not json")
            with self.assertRaises(SqlSourceUnavailableError):
                load_incident_sql(path)

    def test_missing_sql_info_raises_sql_info_missing(self):
        with self.assertRaises(SqlInfoMissingError):
            load_incident_sql(REPO_ROOT / "data_engineering_incident_test_3.json")


if __name__ == "__main__":
    unittest.main()
