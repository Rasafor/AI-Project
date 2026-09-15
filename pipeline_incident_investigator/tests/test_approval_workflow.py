import tempfile
import unittest
from pathlib import Path

from pipeline_incident_investigator.approval_workflow import (
    ALLOWED_APPROVER_ROLES,
    APPROVED,
    AUTO_APPROVED,
    PENDING,
    REJECTED,
    ApprovalAuditError,
    ApprovalConflictError,
    ApprovalNotFoundError,
    ApprovalNotPendingError,
    RecommendationCategorizationError,
    UnauthorizedApprovalError,
    decide_approval,
    get_approval,
    severity_for_category,
    submit_investigation_recommendation,
    submit_recommendation_for_approval,
)
from pipeline_incident_investigator.audit_log import verify_log_integrity
from pipeline_incident_investigator.investigator import investigate

REPO_ROOT = Path(__file__).resolve().parents[2]


def _submit_major(audit_log_path, **overrides):
    kwargs = dict(
        incident_id="INC-TEST",
        source="log_analysis",
        category="Schema Change",
        severity="high",
        description="A column no longer exists in the source schema.",
        recommended_action="Update the transformation to use the current column.",
        audit_log_path=audit_log_path,
    )
    kwargs.update(overrides)
    return submit_recommendation_for_approval(**kwargs)


def _submit_minor(audit_log_path, **overrides):
    kwargs = dict(
        incident_id="INC-TEST",
        source="log_analysis",
        category="Resource Exhaustion",
        severity="medium",
        description="An executor ran out of memory.",
        recommended_action="Increase executor memory and rerun the failed stage.",
        audit_log_path=audit_log_path,
    )
    kwargs.update(overrides)
    return submit_recommendation_for_approval(**kwargs)


class SeverityForCategoryTests(unittest.TestCase):
    def test_maps_known_categories(self):
        self.assertEqual(severity_for_category("Schema Change"), "high")
        self.assertEqual(severity_for_category("Resource Exhaustion"), "medium")

    def test_raises_for_unknown_category(self):
        with self.assertRaises(RecommendationCategorizationError):
            severity_for_category("Some Made Up Category")


class SubmitRecommendationForApprovalTests(unittest.TestCase):
    def test_major_recommendation_requires_human_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            record = _submit_major(audit_log_path)

            self.assertTrue(record.is_major)
            self.assertEqual(record.status, PENDING)
            self.assertIsNone(record.decided_by)

            entries = verify_log_integrity(audit_log_path)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].activity, "recommendation_submitted")
            self.assertEqual(entries[0].outcome, PENDING)
            self.assertEqual(entries[0].correlation_id, record.decision_id)

    def test_minor_recommendation_is_auto_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            record = _submit_minor(audit_log_path)

            self.assertFalse(record.is_major)
            self.assertEqual(record.status, AUTO_APPROVED)
            self.assertEqual(record.decided_by, "system")

            entries = verify_log_integrity(audit_log_path)
            self.assertEqual(entries[0].outcome, AUTO_APPROVED)

    def test_two_recommendations_from_the_same_investigation_are_both_logged(self):
        # Both submissions share the same investigation_correlation_id (as they
        # would from one coordinate_agents() run) but must not collide in the
        # audit trail -- each gets its own decision_id.
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            first = _submit_major(audit_log_path, investigation_correlation_id="shared-correlation")
            second = _submit_minor(audit_log_path, investigation_correlation_id="shared-correlation")

            self.assertNotEqual(first.decision_id, second.decision_id)
            entries = verify_log_integrity(audit_log_path)
            self.assertEqual(len(entries), 2)

    def test_replaying_the_same_submission_does_not_duplicate_the_audit_trail(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            first = _submit_major(audit_log_path, decision_id="fixed-decision-id")
            second = _submit_major(audit_log_path, decision_id="fixed-decision-id")

            self.assertEqual(first, second)
            self.assertEqual(len(verify_log_integrity(audit_log_path)), 1)

    def test_raises_approval_audit_error_when_the_audit_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocking_file = Path(tmp) / "not_a_directory"
            blocking_file.write_text("blocking")
            audit_log_path = blocking_file / "audit.jsonl"

            with self.assertRaises(ApprovalAuditError):
                _submit_major(audit_log_path)


class DecideApprovalTests(unittest.TestCase):
    def test_approves_a_pending_major_recommendation(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            submitted = _submit_major(audit_log_path)

            decided = decide_approval(
                submitted.decision_id,
                APPROVED,
                approver="alice",
                approver_role="ops_lead",
                audit_log_path=audit_log_path,
            )

            self.assertEqual(decided.status, APPROVED)
            self.assertEqual(decided.decided_by, "alice")
            self.assertEqual(get_approval(submitted.decision_id, audit_log_path=audit_log_path), decided)

    def test_rejects_a_pending_major_recommendation(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            submitted = _submit_major(audit_log_path)

            decided = decide_approval(
                submitted.decision_id,
                REJECTED,
                approver="alice",
                approver_role="ops_lead",
                audit_log_path=audit_log_path,
            )

            self.assertEqual(decided.status, REJECTED)

    def test_cannot_decide_an_auto_approved_recommendation(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            submitted = _submit_minor(audit_log_path)

            with self.assertRaises(ApprovalNotPendingError):
                decide_approval(
                    submitted.decision_id,
                    APPROVED,
                    approver="alice",
                    approver_role="ops_lead",
                    audit_log_path=audit_log_path,
                )

    def test_raises_not_found_for_an_unknown_decision_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"

            with self.assertRaises(ApprovalNotFoundError):
                decide_approval(
                    "no-such-decision",
                    APPROVED,
                    approver="alice",
                    approver_role="ops_lead",
                    audit_log_path=audit_log_path,
                )

    def test_unauthorized_approver_is_denied_and_audited_without_disturbing_the_pending_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            submitted = _submit_major(audit_log_path)
            self.assertNotIn("intern", ALLOWED_APPROVER_ROLES)

            with self.assertRaises(UnauthorizedApprovalError):
                decide_approval(
                    submitted.decision_id,
                    APPROVED,
                    approver="mallory",
                    approver_role="intern",
                    audit_log_path=audit_log_path,
                )

            # The denial is on record...
            entries = verify_log_integrity(audit_log_path)
            denials = [e for e in entries if e.activity == "approval_decision_denied"]
            self.assertEqual(len(denials), 1)
            self.assertEqual(denials[0].outcome, "unauthorized")
            self.assertEqual(denials[0].details["attempted_by"], "mallory")

            # ...but the recommendation itself is still pending, untouched by the
            # denied attempt (the denial used its own correlation id, not the
            # decision's, so it cannot occupy that audit slot).
            still_pending = get_approval(submitted.decision_id, audit_log_path=audit_log_path)
            self.assertEqual(still_pending.status, PENDING)

            # A legitimate approver can still decide it afterwards.
            decided = decide_approval(
                submitted.decision_id,
                APPROVED,
                approver="alice",
                approver_role="ops_lead",
                audit_log_path=audit_log_path,
            )
            self.assertEqual(decided.status, APPROVED)

    def test_replaying_the_same_decision_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            submitted = _submit_major(audit_log_path)

            first = decide_approval(
                submitted.decision_id,
                APPROVED,
                approver="alice",
                approver_role="ops_lead",
                audit_log_path=audit_log_path,
            )
            second = decide_approval(
                submitted.decision_id,
                APPROVED,
                approver="bob",
                approver_role="incident_commander",
                audit_log_path=audit_log_path,
            )

            self.assertEqual(first, second)
            self.assertEqual(second.decided_by, "alice")  # the first decision stands
            decision_entries = [
                e for e in verify_log_integrity(audit_log_path) if e.activity == "approval_decision"
            ]
            self.assertEqual(len(decision_entries), 1)

    def test_conflicting_redecision_raises_and_leaves_the_original_decision_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            submitted = _submit_major(audit_log_path)

            decide_approval(
                submitted.decision_id,
                APPROVED,
                approver="alice",
                approver_role="ops_lead",
                audit_log_path=audit_log_path,
            )

            with self.assertRaises(ApprovalConflictError):
                decide_approval(
                    submitted.decision_id,
                    REJECTED,
                    approver="bob",
                    approver_role="incident_commander",
                    audit_log_path=audit_log_path,
                )

            unchanged = get_approval(submitted.decision_id, audit_log_path=audit_log_path)
            self.assertEqual(unchanged.status, APPROVED)
            self.assertEqual(unchanged.decided_by, "alice")


class TrustAuditTrailTests(unittest.TestCase):
    def test_every_recommendation_and_approval_is_logged_with_a_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_log_path = Path(tmp) / "audit.jsonl"
            submitted = _submit_major(audit_log_path)
            decide_approval(
                submitted.decision_id,
                APPROVED,
                approver="alice",
                approver_role="ops_lead",
                audit_log_path=audit_log_path,
            )

            entries = verify_log_integrity(audit_log_path)
            activities = {e.activity for e in entries}
            self.assertEqual(activities, {"recommendation_submitted", "approval_decision"})
            for entry in entries:
                self.assertTrue(entry.timestamp)
                self.assertEqual(entry.correlation_id, submitted.decision_id)


class SubmitInvestigationRecommendationTests(unittest.TestCase):
    """Wires real investigate() output (STORY-001) into the approval workflow --
    no hand-built recommendation objects, same as every other story's tests."""

    def test_major_recommendation_from_real_schema_change_fixture_requires_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = investigate(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=Path(tmp) / "investigation_audit.jsonl",
            )

            record = submit_investigation_recommendation(
                investigation, audit_log_path=Path(tmp) / "approval_audit.jsonl"
            )

            self.assertIsNotNone(record)
            self.assertEqual(record.category, "Schema Change")
            self.assertEqual(record.severity, "high")
            self.assertTrue(record.is_major)
            self.assertEqual(record.status, PENDING)

    def test_minor_recommendation_from_real_resource_exhaustion_fixture_is_auto_approved(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = investigate(
                REPO_ROOT / "data_engineering_incident_test_2.json",
                audit_log_path=Path(tmp) / "investigation_audit.jsonl",
            )

            record = submit_investigation_recommendation(
                investigation, audit_log_path=Path(tmp) / "approval_audit.jsonl"
            )

            self.assertIsNotNone(record)
            self.assertEqual(record.category, "Resource Exhaustion")
            self.assertEqual(record.severity, "medium")
            self.assertFalse(record.is_major)
            self.assertEqual(record.status, AUTO_APPROVED)

    def test_no_recommendation_means_nothing_is_submitted_for_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            approval_audit_path = Path(tmp) / "approval_audit.jsonl"
            investigation = investigate(
                REPO_ROOT / "data_engineering_incident_test_3.json",
                audit_log_path=Path(tmp) / "investigation_audit.jsonl",
            )

            record = submit_investigation_recommendation(investigation, audit_log_path=approval_audit_path)

            self.assertIsNone(record)
            self.assertFalse(approval_audit_path.exists())


if __name__ == "__main__":
    unittest.main()
