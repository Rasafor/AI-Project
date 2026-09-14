import json
import tempfile
import unittest
from pathlib import Path

from pipeline_incident_investigator.investigator import investigate
from pipeline_incident_investigator.log_source import LogsUnavailableError

REPO_ROOT = Path(__file__).resolve().parents[2]


def _read_audit_lines(log_path: Path) -> list[dict]:
    if not log_path.exists():
        return []
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]


class InvestigateTests(unittest.TestCase):
    def test_generates_recommendation_for_schema_mismatch_incident(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            result = investigate(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=audit_log_path,
            )

            self.assertIsNotNone(result.recommendation)
            self.assertEqual(result.recommendation.category, "Schema Change")
            self.assertEqual(result.incident_id, "INC-2026-001")

            entries = _read_audit_lines(audit_log_path)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]["activity"], "log_analysis")
            self.assertEqual(entries[0]["outcome"], "success")
            self.assertEqual(entries[1]["activity"], "recommendation")
            self.assertEqual(entries[1]["outcome"], "success")
            self.assertTrue(all(e["correlation_id"] == result.correlation_id for e in entries))

    def test_generates_recommendation_for_resource_exhaustion_incident(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            result = investigate(
                REPO_ROOT / "data_engineering_incident_test_2.json",
                audit_log_path=audit_log_path,
            )

            self.assertIsNotNone(result.recommendation)
            self.assertEqual(result.recommendation.category, "Resource Exhaustion")

    def test_no_recommendation_for_incident_with_no_known_pattern(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            result = investigate(
                REPO_ROOT / "data_engineering_incident_test_3.json",
                audit_log_path=audit_log_path,
            )

            self.assertIsNone(result.recommendation)

            entries = _read_audit_lines(audit_log_path)
            self.assertEqual(entries[1]["activity"], "recommendation")
            self.assertEqual(entries[1]["outcome"], "no_recommendation")

    def test_audits_failure_and_reraises_when_logs_are_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            with self.assertRaises(LogsUnavailableError):
                investigate(
                    REPO_ROOT / "does_not_exist.json",
                    audit_log_path=audit_log_path,
                )

            entries = _read_audit_lines(audit_log_path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]["activity"], "log_analysis")
            self.assertEqual(entries[0]["outcome"], "failure")
            self.assertEqual(entries[0]["details"]["error_class"], "LogsUnavailableError")

    def test_replaying_the_same_investigation_does_not_duplicate_the_audit_trail(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            first = investigate(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=audit_log_path,
                correlation_id="fixed-correlation-id",
            )
            second = investigate(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=audit_log_path,
                correlation_id="fixed-correlation-id",
            )

            self.assertEqual(first, second)
            entries = _read_audit_lines(audit_log_path)
            self.assertEqual(len(entries), 2)


if __name__ == "__main__":
    unittest.main()
