import tempfile
import unittest
from pathlib import Path

from pipeline_incident_investigator.audit_log import verify_log_integrity
from pipeline_incident_investigator.data_quality_investigation import investigate_data_quality
from pipeline_incident_investigator.data_quality_source import (
    DataQualityInfoMissingError,
    DataQualitySourceUnavailableError,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


class InvestigateDataQualityTests(unittest.TestCase):
    def test_identifies_root_causes_for_incident_with_quality_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            result = investigate_data_quality(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=audit_log_path,
            )

            self.assertEqual({i.id for i in result.issues}, {"row_count_shortfall", "schema_drift"})
            self.assertEqual(result.incident_id, "INC-2026-001")

            entries = verify_log_integrity(audit_log_path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].activity, "data_quality_analysis")
            self.assertEqual(entries[0].outcome, "issues_found")
            self.assertEqual(set(entries[0].details["issue_ids"]), {"row_count_shortfall", "schema_drift"})

    def test_no_root_causes_for_incident_with_no_quality_issues(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            result = investigate_data_quality(
                REPO_ROOT / "data_engineering_incident_test_3.json",
                audit_log_path=audit_log_path,
            )

            self.assertEqual(result.issues, [])

            entries = verify_log_integrity(audit_log_path)
            self.assertEqual(entries[0].outcome, "no_issues")

    def test_audits_failure_when_data_quality_source_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            with self.assertRaises(DataQualitySourceUnavailableError):
                investigate_data_quality(
                    REPO_ROOT / "does_not_exist.json",
                    audit_log_path=audit_log_path,
                )

            entries = verify_log_integrity(audit_log_path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].outcome, "failure")
            self.assertEqual(entries[0].details["error_class"], "DataQualitySourceUnavailableError")

    def test_audits_failure_when_data_quality_checks_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            incident_path = Path(tmp) / "incident.json"
            incident_path.write_text('{"incident_id": "INC-TEST"}')
            audit_log_path = Path(tmp) / "audit.jsonl"

            with self.assertRaises(DataQualityInfoMissingError):
                investigate_data_quality(incident_path, audit_log_path=audit_log_path)

            entries = verify_log_integrity(audit_log_path)
            self.assertEqual(entries[0].details["error_class"], "DataQualityInfoMissingError")

    def test_replaying_the_same_investigation_does_not_duplicate_the_audit_trail(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            first = investigate_data_quality(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=audit_log_path,
                correlation_id="fixed-correlation-id",
            )
            second = investigate_data_quality(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=audit_log_path,
                correlation_id="fixed-correlation-id",
            )

            self.assertEqual(first, second)
            self.assertEqual(len(verify_log_integrity(audit_log_path)), 1)


if __name__ == "__main__":
    unittest.main()
