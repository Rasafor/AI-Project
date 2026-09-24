import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from pipeline_incident_investigator import audit_log
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


class SinglePassOptimizationTests(unittest.TestCase):
    """STORY-009 replaced two full reads per write with one. These pin that it changed nothing."""

    GOLDEN = Path(__file__).resolve().parent / "golden_audit_trail.jsonl"

    def _write_golden_sequence(self, log_path):
        # The exact sequence that produced golden_audit_trail.jsonl with the pre-optimization code:
        # 20 writes over 10 distinct (correlation_id, activity) pairs, so 10 are dedup replays.
        frozen = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
        with mock.patch.object(audit_log, "datetime", wraps=datetime) as dt:
            dt.now.return_value = frozen
            for i in range(20):
                record_activity(log_path, correlation_id=f"c{i % 5}", incident_id=f"INC-{i}",
                                activity=f"a{i % 2}", outcome="ok", details={"i": i})

    def test_output_is_byte_identical_to_the_pre_optimization_code(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            self._write_golden_sequence(log_path)
            self.assertEqual(log_path.read_bytes(), self.GOLDEN.read_bytes())

    def test_dedup_hit_returns_the_first_entry_and_writes_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            first = record_activity(log_path, correlation_id="c", incident_id="i", activity="a", outcome="ok")
            record_activity(log_path, correlation_id="d", incident_id="i", activity="a", outcome="ok")
            before = log_path.read_bytes()

            replay = record_activity(log_path, correlation_id="c", incident_id="i", activity="a", outcome="changed")

            self.assertEqual(replay, first)
            self.assertEqual(log_path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
