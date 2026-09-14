import json
import tempfile
import unittest
from pathlib import Path

from pipeline_incident_investigator.log_source import (
    LogsIncompleteError,
    LogsUnavailableError,
    load_incident_logs,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "data_engineering_incident_test.json"


class LoadIncidentLogsTests(unittest.TestCase):
    def test_loads_execution_logs_from_fixture(self):
        logs = load_incident_logs(FIXTURE)
        self.assertIsInstance(logs, list)
        self.assertGreater(len(logs), 0)
        self.assertIn("Pipeline daily_customer_orders started", logs[0])

    def test_missing_file_raises_logs_unavailable(self):
        with self.assertRaises(LogsUnavailableError):
            load_incident_logs(REPO_ROOT / "does_not_exist.json")

    def test_non_json_file_raises_logs_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incident.json"
            path.write_text("not json")
            with self.assertRaises(LogsUnavailableError):
                load_incident_logs(path)

    def test_empty_execution_logs_raises_logs_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incident.json"
            path.write_text(json.dumps({"incident_id": "INC-TEST", "execution_logs": []}))
            with self.assertRaises(LogsIncompleteError):
                load_incident_logs(path)

    def test_missing_execution_logs_key_raises_logs_incomplete(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incident.json"
            path.write_text(json.dumps({"incident_id": "INC-TEST"}))
            with self.assertRaises(LogsIncompleteError):
                load_incident_logs(path)


if __name__ == "__main__":
    unittest.main()
