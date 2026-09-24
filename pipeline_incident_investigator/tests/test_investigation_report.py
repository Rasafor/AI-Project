import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

from pipeline_incident_investigator.agent_coordinator import coordinate_agents
from pipeline_incident_investigator.approval_workflow import (
    ALLOWED_APPROVER_ROLES,
    decide_approval,
    submit_investigation_recommendation,
)
from pipeline_incident_investigator.audit_log import verify_log_integrity
from pipeline_incident_investigator.investigation_report import (
    ReportAuditError,
    ReportDataIntegrityError,
    ReportNotFoundError,
    UnauthorizedReportAccessError,
    generate_report,
)
from pipeline_incident_investigator.investigator import LogsUnavailableError, investigate
from pipeline_incident_investigator.notification_service import (
    NotificationChannelError,
    NotificationDeliveryError,
    notify_if_uncertain,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
VIEWER = {"viewer": "dana", "viewer_role": "data_engineer"}


def _report_entries(audit_log_path):
    return [e for e in verify_log_integrity(audit_log_path) if e.activity == "report_generated"]


def _always_fails(payload, *, timeout):
    raise NotificationChannelError("simulated channel permanently unavailable")


class CompletedInvestigationReportTests(unittest.TestCase):
    def test_completed_investigation_generates_detailed_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            run = coordinate_agents(REPO_ROOT / "data_engineering_incident_test.json", audit_log_path=audit_log_path)

            report = generate_report(run.correlation_id, audit_log_path=audit_log_path, **VIEWER)

            self.assertEqual(report.status, "success")
            self.assertEqual(report.incident_id, run.incident_id)
            self.assertEqual(report.failures, [])
            activities = [a["activity"] for a in report.activities]
            for expected in ("coordination_initiated", "log_analysis", "sql_analysis",
                             "data_quality_analysis", "agent_coordination"):
                self.assertIn(expected, activities)
            self.assertEqual(len(report.report_hash), 64)
            json.dumps(report.to_dict())  # the report is exportable as JSON for further analysis


class FailedInvestigationReportTests(unittest.TestCase):
    def test_failed_coordinated_investigation_includes_failure_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            run = coordinate_agents(Path(tmp) / "missing_incident.json", audit_log_path=audit_log_path)
            self.assertEqual(run.status, "failure")  # sanity: every agent failed

            report = generate_report(run.correlation_id, audit_log_path=audit_log_path, **VIEWER)

            self.assertEqual(report.status, "failure")
            failed_agents = {f.activity: f for f in report.failures}
            for agent in ("log_analysis", "sql_analysis", "data_quality_analysis"):
                self.assertIn(agent, failed_agents)
                self.assertTrue(failed_agents[agent].error_class)
                self.assertTrue(failed_agents[agent].error)
                self.assertTrue(failed_agents[agent].timestamp)
            self.assertEqual(failed_agents["log_analysis"].error_class, "LogsUnavailableError")

    def test_failed_standalone_investigation_includes_failure_details(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            with self.assertRaises(LogsUnavailableError):
                investigate(Path(tmp) / "missing_incident.json", audit_log_path=audit_log_path,
                            correlation_id="inv-standalone-fail")

            report = generate_report("inv-standalone-fail", audit_log_path=audit_log_path, **VIEWER)

            self.assertEqual(report.status, "failure")
            self.assertEqual(len(report.failures), 1)
            self.assertEqual(report.failures[0].activity, "log_analysis")
            self.assertEqual(report.failures[0].error_class, "LogsUnavailableError")


class ReportAuditTrustTests(unittest.TestCase):
    def test_every_report_is_logged_for_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            run = coordinate_agents(REPO_ROOT / "data_engineering_incident_test.json", audit_log_path=audit_log_path)

            report = generate_report(run.correlation_id, audit_log_path=audit_log_path, **VIEWER)

            logged = _report_entries(audit_log_path)
            self.assertEqual(len(logged), 1)
            self.assertTrue(logged[0].timestamp)
            self.assertEqual(logged[0].details["investigation_correlation_id"], run.correlation_id)
            self.assertEqual(logged[0].details["report_hash"], report.report_hash)
            self.assertEqual(logged[0].details["generated_by"], "dana")

    def test_unchanged_report_logged_once_changed_report_logged_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            investigation = investigate(REPO_ROOT / "data_engineering_incident_test.json",
                                        audit_log_path=audit_log_path)
            submitted = submit_investigation_recommendation(investigation, audit_log_path=audit_log_path)
            self.assertEqual(submitted.status, "pending_approval")  # sanity: fixture 1 is a major change

            first = generate_report(investigation.correlation_id, audit_log_path=audit_log_path, **VIEWER)
            replay = generate_report(investigation.correlation_id, audit_log_path=audit_log_path, **VIEWER)
            self.assertEqual(first.report_hash, replay.report_hash)
            self.assertEqual(len(_report_entries(audit_log_path)), 1)
            self.assertEqual(len(first.recommendations), 1)
            self.assertEqual(first.approvals, [])

            decide_approval(submitted.decision_id, "approved", approver="lee",
                            approver_role=sorted(ALLOWED_APPROVER_ROLES)[0], audit_log_path=audit_log_path)
            after = generate_report(investigation.correlation_id, audit_log_path=audit_log_path, **VIEWER)

            self.assertNotEqual(after.report_hash, first.report_hash)
            self.assertEqual(len(after.approvals), 1)
            self.assertEqual(after.approvals[0]["outcome"], "approved")
            self.assertEqual(len(_report_entries(audit_log_path)), 2)

    def test_failed_notification_is_reported_without_changing_investigation_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            investigation = investigate(REPO_ROOT / "data_engineering_incident_test_3.json",
                                        audit_log_path=audit_log_path)
            with self.assertRaises(NotificationDeliveryError):
                notify_if_uncertain(investigation, send_fn=_always_fails, audit_log_path=audit_log_path)

            report = generate_report(investigation.correlation_id, audit_log_path=audit_log_path, **VIEWER)

            self.assertEqual(report.status, "success")
            self.assertEqual(len(report.notifications), 1)
            self.assertEqual([f.activity for f in report.failures], ["notification_sent"])


class ReportFailurePathTests(unittest.TestCase):
    def test_unauthorized_viewer_is_denied_and_audited(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            run = coordinate_agents(REPO_ROOT / "data_engineering_incident_test.json", audit_log_path=audit_log_path)

            with self.assertRaises(UnauthorizedReportAccessError):
                generate_report(run.correlation_id, viewer="mallory", viewer_role="intern",
                                audit_log_path=audit_log_path)

            trail = verify_log_integrity(audit_log_path)
            denied = [e for e in trail if e.activity == "report_access_denied"]
            self.assertEqual(len(denied), 1)
            self.assertEqual(denied[0].details["attempted_role"], "intern")
            self.assertEqual(_report_entries(audit_log_path), [])

            # a denial does not leak into, or block, a legitimate report
            report = generate_report(run.correlation_id, audit_log_path=audit_log_path, **VIEWER)
            self.assertNotIn("report_access_denied", [a["activity"] for a in report.activities])

    def test_tampered_audit_trail_refuses_to_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            run = coordinate_agents(REPO_ROOT / "data_engineering_incident_test.json", audit_log_path=audit_log_path)
            lines = audit_log_path.read_text(encoding="utf-8").splitlines()
            lines[1] = lines[1].replace('"outcome": "success"', '"outcome": "failure"')
            audit_log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            with self.assertRaises(ReportDataIntegrityError):
                generate_report(run.correlation_id, audit_log_path=audit_log_path, **VIEWER)

    def test_audit_write_failure_raises_instead_of_returning_unaudited_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            run = coordinate_agents(REPO_ROOT / "data_engineering_incident_test.json", audit_log_path=audit_log_path)
            os.chmod(audit_log_path, stat.S_IREAD)  # readable, so the report builds; not writable, so auditing fails
            try:
                with self.assertRaises(ReportAuditError):
                    generate_report(run.correlation_id, audit_log_path=audit_log_path, **VIEWER)
            finally:
                os.chmod(audit_log_path, stat.S_IREAD | stat.S_IWRITE)

    def test_unknown_investigation_raises_not_found(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            coordinate_agents(REPO_ROOT / "data_engineering_incident_test.json", audit_log_path=audit_log_path)

            with self.assertRaises(ReportNotFoundError):
                generate_report("no-such-investigation", audit_log_path=audit_log_path, **VIEWER)


if __name__ == "__main__":
    unittest.main()
