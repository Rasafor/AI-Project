import json
import tempfile
import unittest
from pathlib import Path

from pipeline_incident_investigator.audit_log import AuditLoggingError, record_activity


class RecordActivityTests(unittest.TestCase):
    def test_records_activity_to_log_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"

            entry = record_activity(
                log_path,
                correlation_id="corr-1",
                incident_id="INC-2026-001",
                activity="log_analysis",
                outcome="success",
                details={"pattern_id": "schema_mismatch"},
            )

            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)

            recorded = json.loads(lines[0])
            self.assertEqual(recorded["correlation_id"], "corr-1")
            self.assertEqual(recorded["incident_id"], "INC-2026-001")
            self.assertEqual(recorded["activity"], "log_analysis")
            self.assertEqual(recorded["outcome"], "success")
            self.assertEqual(recorded["details"], {"pattern_id": "schema_mismatch"})
            self.assertTrue(recorded["timestamp"])
            self.assertEqual(entry.correlation_id, "corr-1")

    def test_replaying_same_correlation_id_and_activity_does_not_duplicate(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"

            first = record_activity(
                log_path,
                correlation_id="corr-1",
                incident_id="INC-2026-001",
                activity="log_analysis",
                outcome="success",
            )
            second = record_activity(
                log_path,
                correlation_id="corr-1",
                incident_id="INC-2026-001",
                activity="log_analysis",
                outcome="success",
            )

            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 1)
            self.assertEqual(first, second)

    def test_different_activity_same_correlation_id_appends_separately(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"

            record_activity(
                log_path,
                correlation_id="corr-1",
                incident_id="INC-2026-001",
                activity="log_analysis",
                outcome="success",
            )
            record_activity(
                log_path,
                correlation_id="corr-1",
                incident_id="INC-2026-001",
                activity="recommendation_generated",
                outcome="success",
            )

            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            self.assertEqual(len(lines), 2)

    def test_write_failure_raises_audit_logging_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocking_file = Path(tmp) / "not_a_directory"
            blocking_file.write_text("occupying this path")
            log_path = blocking_file / "audit.jsonl"

            with self.assertRaises(AuditLoggingError):
                record_activity(
                    log_path,
                    correlation_id="corr-1",
                    incident_id="INC-2026-001",
                    activity="log_analysis",
                    outcome="success",
                )


if __name__ == "__main__":
    unittest.main()
