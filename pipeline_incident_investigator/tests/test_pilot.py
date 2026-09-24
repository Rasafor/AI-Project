import itertools
import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from pipeline_incident_investigator.audit_log import record_activity, verify_log_integrity
from pipeline_incident_investigator.pilot import (
    ERROR,
    UNCERTAIN,
    PilotAuditError,
    PilotConfigError,
    UnauthorizedPilotAccessError,
    run_pilot,
)

OPERATOR = {"operator": "dana", "operator_role": "data_engineer"}
FIXTURE_1 = "data_engineering_incident_test.json"  # real: Schema Change
FIXTURE_3 = "data_engineering_incident_test_3.json"  # real: no known pattern


def _write_expected(tmp, cases, threshold=0.05, budget=3600):
    path = Path(tmp) / "expected.json"
    path.write_text(json.dumps({"error_rate_threshold": threshold, "time_budget_seconds": budget,
                                "cases": cases}), encoding="utf-8")
    return path


def _entries(audit_log_path, activity):
    return [e for e in verify_log_integrity(audit_log_path) if e.activity == activity]


CORRECT_CASES = [{"path": FIXTURE_1, "expected": "Schema Change"}, {"path": FIXTURE_3, "expected": UNCERTAIN}]


class PilotOutcomeTests(unittest.TestCase):
    def test_all_correct_and_fast_pilot_passes(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = run_pilot(_write_expected(tmp, CORRECT_CASES), audit_log_path=Path(tmp) / "a.jsonl", **OPERATOR)

            self.assertTrue(result.passed)
            self.assertEqual((result.total, result.errors, result.error_rate), (2, 0, 0.0))
            self.assertTrue(result.all_within_budget)
            self.assertLess(result.max_seconds, 3600)
            self.assertEqual([c.verdict for c in result.cases], ["Schema Change", UNCERTAIN])

    def test_wrong_verdict_counts_as_error_and_fails_pilot(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = [{"path": FIXTURE_1, "expected": "Resource Exhaustion"}, CORRECT_CASES[1]]
            result = run_pilot(_write_expected(tmp, cases), audit_log_path=Path(tmp) / "a.jsonl", **OPERATOR)

            self.assertEqual(result.errors, 1)
            self.assertEqual(result.error_rate, 0.5)
            self.assertFalse(result.cases[0].correct)
            self.assertFalse(result.passed)

    def test_over_time_budget_fails_pilot_even_with_no_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake_clock = itertools.count(0, 5000).__next__  # every case appears to take 5000 s
            result = run_pilot(_write_expected(tmp, CORRECT_CASES), audit_log_path=Path(tmp) / "a.jsonl",
                               clock=fake_clock, **OPERATOR)

            self.assertEqual(result.errors, 0)
            self.assertFalse(result.all_within_budget)
            self.assertFalse(result.passed)
            self.assertEqual(result.max_seconds, 5000)

    def test_missing_case_file_is_an_error_for_that_case_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            cases = [{"path": "no/such/incident.json", "expected": UNCERTAIN}, CORRECT_CASES[0]]
            result = run_pilot(_write_expected(tmp, cases), audit_log_path=Path(tmp) / "a.jsonl", **OPERATOR)

            self.assertEqual(result.cases[0].verdict, ERROR)
            self.assertEqual(result.cases[0].error_class, "LogsUnavailableError")
            self.assertTrue(result.cases[1].correct)  # the pilot kept going
            self.assertEqual(result.errors, 1)

    def test_unexpected_crash_is_recorded_and_pilot_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch("pipeline_incident_investigator.pilot.coordinate_agents",
                            side_effect=[RuntimeError("boom"), mock.DEFAULT],
                            wraps=__import__("pipeline_incident_investigator.agent_coordinator",
                                             fromlist=["coordinate_agents"]).coordinate_agents):
                result = run_pilot(_write_expected(tmp, CORRECT_CASES), audit_log_path=Path(tmp) / "a.jsonl",
                                   **OPERATOR)

            self.assertEqual((result.cases[0].verdict, result.cases[0].error_class), (ERROR, "RuntimeError"))
            self.assertTrue(result.cases[1].correct)


class PilotTrustTests(unittest.TestCase):
    def test_every_case_and_the_summary_are_logged_for_audit(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "a.jsonl"
            result = run_pilot(_write_expected(tmp, CORRECT_CASES), audit_log_path=audit_log_path, **OPERATOR)

            case_entries = _entries(audit_log_path, "pilot_case")
            self.assertEqual(len(case_entries), 2)
            self.assertTrue(all(e.timestamp and e.details["run_id"] == result.run_id for e in case_entries))
            (summary,) = _entries(audit_log_path, "pilot_completed")
            self.assertEqual(summary.outcome, "passed")
            self.assertEqual(summary.details["error_rate"], 0.0)
            self.assertEqual(summary.details["operator"], "dana")

    def test_replaying_a_run_writes_no_duplicate_audit_entries(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "a.jsonl"
            expected = _write_expected(tmp, CORRECT_CASES)
            run_pilot(expected, audit_log_path=audit_log_path, run_id="run-1", **OPERATOR)
            lines_after_first = len(audit_log_path.read_text(encoding="utf-8").splitlines())

            run_pilot(expected, audit_log_path=audit_log_path, run_id="run-1", **OPERATOR)

            self.assertEqual(len(audit_log_path.read_text(encoding="utf-8").splitlines()), lines_after_first)

    def test_audit_write_failure_raises_instead_of_returning_results(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "a.jsonl"
            record_activity(audit_log_path, correlation_id="seed", incident_id="x", activity="seed", outcome="ok")
            os.chmod(audit_log_path, stat.S_IREAD)
            try:
                with self.assertRaises(PilotAuditError):
                    run_pilot(_write_expected(tmp, CORRECT_CASES), audit_log_path=audit_log_path, **OPERATOR)
            finally:
                os.chmod(audit_log_path, stat.S_IREAD | stat.S_IWRITE)


class PilotAccessAndConfigTests(unittest.TestCase):
    def test_unauthorized_role_is_denied_audited_and_runs_nothing(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "a.jsonl"
            with self.assertRaises(UnauthorizedPilotAccessError):
                run_pilot(_write_expected(tmp, CORRECT_CASES), audit_log_path=audit_log_path,
                          operator="pat", operator_role="project_manager")

            (denied,) = _entries(audit_log_path, "pilot_access_denied")
            self.assertEqual(denied.details["attempted_role"], "project_manager")
            self.assertEqual(_entries(audit_log_path, "pilot_case"), [])

    def test_malformed_or_missing_definition_raises_config_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "a.jsonl"
            bad = Path(tmp) / "bad.json"
            for content in ("not json", json.dumps({"cases": []}),
                            json.dumps({"error_rate_threshold": 0.05, "time_budget_seconds": 1, "cases": []}),
                            json.dumps({"error_rate_threshold": 0.05, "time_budget_seconds": 1,
                                        "cases": [{"path": FIXTURE_1}]})):
                bad.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(PilotConfigError):
                    run_pilot(bad, audit_log_path=audit_log_path, **OPERATOR)
            with self.assertRaises(PilotConfigError):
                run_pilot(Path(tmp) / "missing.json", audit_log_path=audit_log_path, **OPERATOR)


if __name__ == "__main__":
    unittest.main()
