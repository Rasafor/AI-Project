import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline_incident_investigator import agent_coordinator
from pipeline_incident_investigator.agent_coordinator import (
    CoordinationAuditError,
    CoordinationInitiationError,
    coordinate_agents,
)
from pipeline_incident_investigator.audit_log import AuditLoggingError, verify_log_integrity

REPO_ROOT = Path(__file__).resolve().parents[2]


class CoordinateAgentsTests(unittest.TestCase):
    def test_analysis_completes_successfully_when_all_agents_succeed(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            result = coordinate_agents(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=audit_log_path,
            )

            self.assertEqual(result.status, "success")
            self.assertEqual(result.incident_id, "INC-2026-001")
            self.assertEqual(
                {o.agent for o in result.agent_outcomes},
                {"log_analysis", "sql_analysis", "data_quality_analysis"},
            )
            self.assertTrue(all(o.status == "succeeded" for o in result.agent_outcomes))

            entries = verify_log_integrity(audit_log_path)
            self.assertTrue(all(e.correlation_id == result.correlation_id for e in entries))
            summary = [e for e in entries if e.activity == "agent_coordination"][0]
            self.assertEqual(summary.outcome, "success")

    def test_partial_failure_when_one_agent_fails_but_others_still_run(self):
        # Fixture 3's SQL info is genuinely missing (SqlInfoMissingError), while
        # its logs and data-quality metrics are both present and clean -- a
        # real, not synthetic, one-agent-fails case.
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            result = coordinate_agents(
                REPO_ROOT / "data_engineering_incident_test_3.json",
                audit_log_path=audit_log_path,
            )

            self.assertEqual(result.status, "partial_failure")
            outcomes = {o.agent: o for o in result.agent_outcomes}
            self.assertEqual(outcomes["log_analysis"].status, "succeeded")
            self.assertEqual(outcomes["data_quality_analysis"].status, "succeeded")
            self.assertEqual(outcomes["sql_analysis"].status, "failed")
            self.assertEqual(outcomes["sql_analysis"].error_class, "SqlInfoMissingError")

            summary = [e for e in verify_log_integrity(audit_log_path) if e.activity == "agent_coordination"][0]
            self.assertEqual(summary.outcome, "partial_failure")
            self.assertEqual(summary.details["agent_outcomes"]["sql_analysis"], "failed:SqlInfoMissingError")

    def test_failure_when_no_agents_succeed(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            result = coordinate_agents(
                REPO_ROOT / "does_not_exist.json",
                audit_log_path=audit_log_path,
            )

            self.assertEqual(result.status, "failure")
            self.assertTrue(all(o.status == "failed" for o in result.agent_outcomes))

            summary = [e for e in verify_log_integrity(audit_log_path) if e.activity == "agent_coordination"][0]
            self.assertEqual(summary.outcome, "failure")

    def test_audit_trail_logs_the_coordination_task_with_a_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            result = coordinate_agents(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=audit_log_path,
            )

            entries = verify_log_integrity(audit_log_path)
            coordination_entries = [
                e for e in entries if e.activity in ("coordination_initiated", "agent_coordination")
            ]
            self.assertEqual(len(coordination_entries), 2)
            for entry in coordination_entries:
                self.assertEqual(entry.correlation_id, result.correlation_id)
                self.assertTrue(entry.timestamp)

    def test_retrying_after_a_failure_recovers_without_data_loss(self):
        # Same fixture, same correlation_id, called twice -- simulates a caller
        # retrying after seeing a partial_failure result.
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            first = coordinate_agents(
                REPO_ROOT / "data_engineering_incident_test_3.json",
                audit_log_path=audit_log_path,
                correlation_id="fixed-correlation-id",
            )
            entries_after_first = verify_log_integrity(audit_log_path)

            second = coordinate_agents(
                REPO_ROOT / "data_engineering_incident_test_3.json",
                audit_log_path=audit_log_path,
                correlation_id="fixed-correlation-id",
            )
            entries_after_second = verify_log_integrity(audit_log_path)

            self.assertEqual(first, second)
            self.assertEqual(len(entries_after_first), len(entries_after_second))
            # The two agents that succeeded the first time are not re-audited as
            # new entries, and the one that failed is still reported -- retrying
            # neither duplicates nor loses anything already on record.
            self.assertEqual(second.status, "partial_failure")

    def test_raises_coordination_initiation_error_when_the_first_audit_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            # A file where a directory is expected makes the audit log's
            # parent.mkdir() raise OSError -> AuditLoggingError, before any
            # agent has been dispatched.
            blocking_file = Path(tmp) / "not_a_directory"
            blocking_file.write_text("blocking")
            audit_log_path = blocking_file / "audit.jsonl"

            with self.assertRaises(CoordinationInitiationError):
                coordinate_agents(
                    REPO_ROOT / "data_engineering_incident_test.json",
                    audit_log_path=audit_log_path,
                )

    def test_raises_coordination_audit_error_with_partial_result_when_summary_write_fails(self):
        real_record_activity = agent_coordinator.record_activity

        def flaky_record_activity(log_path, *, activity, **kwargs):
            if activity == "agent_coordination":
                raise AuditLoggingError("simulated audit trail failure")
            return real_record_activity(log_path, activity=activity, **kwargs)

        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            with patch.object(agent_coordinator, "record_activity", side_effect=flaky_record_activity):
                with self.assertRaises(CoordinationAuditError) as ctx:
                    coordinate_agents(
                        REPO_ROOT / "data_engineering_incident_test.json",
                        audit_log_path=audit_log_path,
                    )

            partial_result = ctx.exception.partial_result
            self.assertEqual(partial_result.status, "success")
            self.assertTrue(all(o.status == "succeeded" for o in partial_result.agent_outcomes))

    def test_does_not_mask_an_unexpected_error_from_an_agent_as_a_typed_failure(self):
        def boom(*args, **kwargs):
            raise RuntimeError("an unexpected bug, not a known failure mode")

        broken_specs = [
            ("log_analysis", boom, (agent_coordinator.LogsUnavailableError,)),
        ]

        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            with patch.object(agent_coordinator, "_AGENT_SPECS", broken_specs):
                with self.assertRaises(RuntimeError):
                    coordinate_agents(
                        REPO_ROOT / "data_engineering_incident_test.json",
                        audit_log_path=audit_log_path,
                    )


if __name__ == "__main__":
    unittest.main()
