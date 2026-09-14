import json
import tempfile
import unittest
from pathlib import Path

from pipeline_incident_investigator.audit_log import (
    AuditLogTamperedError,
    record_activity,
    verify_log_integrity,
)
from pipeline_incident_investigator.investigator import investigate
from pipeline_incident_investigator.log_source import LogsUnavailableError

REPO_ROOT = Path(__file__).resolve().parents[2]


def _rewrite_lines(log_path: Path, lines: list[str]) -> None:
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class FullInvestigationAuditTrailTests(unittest.TestCase):
    def test_every_activity_of_an_investigation_is_logged_and_verifiable(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            investigate(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=audit_log_path,
            )

            entries = verify_log_integrity(audit_log_path)
            self.assertEqual([e.activity for e in entries], ["log_analysis", "recommendation"])
            self.assertTrue(all(e.timestamp for e in entries))

    def test_failed_investigation_audit_entry_includes_failure_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            with self.assertRaises(LogsUnavailableError):
                investigate(
                    REPO_ROOT / "does_not_exist.json",
                    audit_log_path=audit_log_path,
                )

            entries = verify_log_integrity(audit_log_path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].outcome, "failure")
            self.assertEqual(entries[0].details["error_class"], "LogsUnavailableError")
            self.assertTrue(entries[0].details["error"])


class TamperDetectionTests(unittest.TestCase):
    def _build_three_entry_log(self, log_path: Path) -> None:
        for i in range(3):
            record_activity(
                log_path,
                correlation_id="corr-1",
                incident_id="INC-TEST",
                activity=f"step-{i}",
                outcome="success",
            )

    def test_untampered_log_verifies_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            self._build_three_entry_log(log_path)

            entries = verify_log_integrity(log_path)
            self.assertEqual(len(entries), 3)

    def test_editing_an_entry_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            self._build_three_entry_log(log_path)

            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            record = json.loads(lines[1])
            record["outcome"] = "tampered"
            lines[1] = json.dumps(record)
            _rewrite_lines(log_path, lines)

            with self.assertRaises(AuditLogTamperedError):
                verify_log_integrity(log_path)

    def test_deleting_an_entry_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            self._build_three_entry_log(log_path)

            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            del lines[1]
            _rewrite_lines(log_path, lines)

            with self.assertRaises(AuditLogTamperedError):
                verify_log_integrity(log_path)

    def test_reordering_entries_is_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "audit.jsonl"
            self._build_three_entry_log(log_path)

            lines = log_path.read_text(encoding="utf-8").strip().splitlines()
            lines[0], lines[1] = lines[1], lines[0]
            _rewrite_lines(log_path, lines)

            with self.assertRaises(AuditLogTamperedError):
                verify_log_integrity(log_path)


if __name__ == "__main__":
    unittest.main()
