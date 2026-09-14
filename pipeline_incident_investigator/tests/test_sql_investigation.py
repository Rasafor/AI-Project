import tempfile
import unittest
from pathlib import Path

from pipeline_incident_investigator.audit_log import verify_log_integrity
from pipeline_incident_investigator.sql_investigation import investigate_sql
from pipeline_incident_investigator.sql_source import SqlInfoMissingError, SqlSourceUnavailableError

REPO_ROOT = Path(__file__).resolve().parents[2]


class InvestigateSqlTests(unittest.TestCase):
    def test_identifies_issues_for_incident_with_bad_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            result = investigate_sql(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=audit_log_path,
            )

            self.assertEqual([i.id for i in result.issues], ["undefined_column"])
            self.assertEqual(result.incident_id, "INC-2026-001")

            entries = verify_log_integrity(audit_log_path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].activity, "sql_analysis")
            self.assertEqual(entries[0].outcome, "issues_found")
            self.assertEqual(entries[0].details["issue_ids"], ["undefined_column"])

    def test_no_issues_for_incident_with_clean_sql(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            result = investigate_sql(
                REPO_ROOT / "data_engineering_incident_test_2.json",
                audit_log_path=audit_log_path,
            )

            self.assertEqual(result.issues, [])

            entries = verify_log_integrity(audit_log_path)
            self.assertEqual(entries[0].outcome, "no_issues")

    def test_audits_failure_when_sql_source_unavailable(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            with self.assertRaises(SqlSourceUnavailableError):
                investigate_sql(
                    REPO_ROOT / "does_not_exist.json",
                    audit_log_path=audit_log_path,
                )

            entries = verify_log_integrity(audit_log_path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].outcome, "failure")
            self.assertEqual(entries[0].details["error_class"], "SqlSourceUnavailableError")

    def test_audits_failure_when_sql_info_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            with self.assertRaises(SqlInfoMissingError):
                investigate_sql(
                    REPO_ROOT / "data_engineering_incident_test_3.json",
                    audit_log_path=audit_log_path,
                )

            entries = verify_log_integrity(audit_log_path)
            self.assertEqual(entries[0].details["error_class"], "SqlInfoMissingError")

    def test_replaying_the_same_investigation_does_not_duplicate_the_audit_trail(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            first = investigate_sql(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=audit_log_path,
                correlation_id="fixed-correlation-id",
            )
            second = investigate_sql(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=audit_log_path,
                correlation_id="fixed-correlation-id",
            )

            self.assertEqual(first, second)
            self.assertEqual(len(verify_log_integrity(audit_log_path)), 1)


if __name__ == "__main__":
    unittest.main()
