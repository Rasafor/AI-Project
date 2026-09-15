import tempfile
import unittest
from pathlib import Path

from pipeline_incident_investigator.audit_log import verify_log_integrity
from pipeline_incident_investigator.investigator import investigate
from pipeline_incident_investigator.notification_service import (
    ALLOWED_VIEWER_ROLES,
    FAILED,
    SENT,
    NotificationAuditError,
    NotificationChannelError,
    NotificationDeliveryError,
    NotificationNotFoundError,
    UnauthorizedNotificationAccessError,
    get_notification,
    notify_if_uncertain,
)

REPO_ROOT = Path(__file__).resolve().parents[2]


def _flaky_send(fail_times: int):
    """A send_fn stub that raises NotificationChannelError the first `fail_times`
    calls, then succeeds. Tracks how many times it was actually called."""
    state = {"calls": 0}

    def send(payload, *, timeout):
        state["calls"] += 1
        if state["calls"] <= fail_times:
            raise NotificationChannelError("simulated channel outage")

    send.state = state
    return send


def _always_fails(payload, *, timeout):
    raise NotificationChannelError("simulated channel permanently unavailable")


class NotifyIfUncertainRealFixtureTests(unittest.TestCase):
    def test_uncertain_root_cause_sends_a_notification(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = investigate(
                REPO_ROOT / "data_engineering_incident_test_3.json",
                audit_log_path=Path(tmp) / "investigation_audit.jsonl",
            )
            self.assertIsNone(investigation.recommendation)  # sanity: this fixture is the uncertain case

            notification_audit_path = Path(tmp) / "notification_audit.jsonl"
            record = notify_if_uncertain(investigation, audit_log_path=notification_audit_path)

            self.assertIsNotNone(record)
            self.assertEqual(record.status, SENT)
            self.assertEqual(record.investigation_correlation_id, investigation.correlation_id)

            entries = [e for e in verify_log_integrity(notification_audit_path) if e.activity == "notification_sent"]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].outcome, SENT)

    def test_certain_root_cause_schema_change_sends_no_notification(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = investigate(
                REPO_ROOT / "data_engineering_incident_test.json",
                audit_log_path=Path(tmp) / "investigation_audit.jsonl",
            )
            self.assertIsNotNone(investigation.recommendation)

            notification_audit_path = Path(tmp) / "notification_audit.jsonl"
            record = notify_if_uncertain(investigation, audit_log_path=notification_audit_path)

            self.assertIsNone(record)
            self.assertFalse(notification_audit_path.exists())

    def test_certain_root_cause_resource_exhaustion_sends_no_notification(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = investigate(
                REPO_ROOT / "data_engineering_incident_test_2.json",
                audit_log_path=Path(tmp) / "investigation_audit.jsonl",
            )
            self.assertIsNotNone(investigation.recommendation)

            notification_audit_path = Path(tmp) / "notification_audit.jsonl"
            record = notify_if_uncertain(investigation, audit_log_path=notification_audit_path)

            self.assertIsNone(record)
            self.assertFalse(notification_audit_path.exists())


class NotifyIfUncertainRetryTests(unittest.TestCase):
    def _uncertain_investigation(self, tmp):
        return investigate(
            REPO_ROOT / "data_engineering_incident_test_3.json",
            audit_log_path=Path(tmp) / "investigation_audit.jsonl",
        )

    def test_retries_until_send_succeeds(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = self._uncertain_investigation(tmp)
            send_fn = _flaky_send(fail_times=2)
            notification_audit_path = Path(tmp) / "notification_audit.jsonl"

            record = notify_if_uncertain(
                investigation, send_fn=send_fn, max_attempts=3, audit_log_path=notification_audit_path
            )

            self.assertEqual(record.status, SENT)
            self.assertEqual(record.attempts, 3)
            self.assertEqual(send_fn.state["calls"], 3)

    def test_raises_delivery_error_after_exhausting_retries(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = self._uncertain_investigation(tmp)
            notification_audit_path = Path(tmp) / "notification_audit.jsonl"

            with self.assertRaises(NotificationDeliveryError) as ctx:
                notify_if_uncertain(
                    investigation,
                    send_fn=_always_fails,
                    max_attempts=3,
                    audit_log_path=notification_audit_path,
                )

            self.assertEqual(ctx.exception.record.status, FAILED)
            self.assertEqual(ctx.exception.record.attempts, 3)

            entries = [
                e for e in verify_log_integrity(notification_audit_path) if e.activity == "notification_sent"
            ]
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0].outcome, FAILED)

    def test_does_not_resend_after_a_successful_delivery(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = self._uncertain_investigation(tmp)
            notification_audit_path = Path(tmp) / "notification_audit.jsonl"
            send_fn = _flaky_send(fail_times=0)  # always succeeds, but counts calls

            first = notify_if_uncertain(investigation, send_fn=send_fn, audit_log_path=notification_audit_path)
            second = notify_if_uncertain(investigation, send_fn=send_fn, audit_log_path=notification_audit_path)

            self.assertEqual(first, second)
            self.assertEqual(send_fn.state["calls"], 1)  # the second call never invoked send_fn again
            entries = [
                e for e in verify_log_integrity(notification_audit_path) if e.activity == "notification_sent"
            ]
            self.assertEqual(len(entries), 1)

    def test_retrying_after_a_failure_can_still_succeed_and_both_attempts_are_on_record(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = self._uncertain_investigation(tmp)
            notification_audit_path = Path(tmp) / "notification_audit.jsonl"

            with self.assertRaises(NotificationDeliveryError):
                notify_if_uncertain(
                    investigation,
                    send_fn=_always_fails,
                    max_attempts=1,
                    audit_log_path=notification_audit_path,
                )

            recovered = notify_if_uncertain(
                investigation,
                send_fn=_flaky_send(fail_times=0),
                audit_log_path=notification_audit_path,
            )

            self.assertEqual(recovered.status, SENT)

            entries = [
                e for e in verify_log_integrity(notification_audit_path) if e.activity == "notification_sent"
            ]
            self.assertEqual(len(entries), 2)
            self.assertEqual([e.outcome for e in entries], [FAILED, SENT])

    def test_raises_notification_audit_error_when_the_audit_write_fails(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = self._uncertain_investigation(tmp)
            blocking_file = Path(tmp) / "not_a_directory"
            blocking_file.write_text("blocking")
            notification_audit_path = blocking_file / "notification_audit.jsonl"

            with self.assertRaises(NotificationAuditError):
                notify_if_uncertain(investigation, audit_log_path=notification_audit_path)


class GetNotificationTests(unittest.TestCase):
    def test_returns_the_recorded_state_for_an_authorized_viewer(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = investigate(
                REPO_ROOT / "data_engineering_incident_test_3.json",
                audit_log_path=Path(tmp) / "investigation_audit.jsonl",
            )
            notification_audit_path = Path(tmp) / "notification_audit.jsonl"
            sent = notify_if_uncertain(investigation, audit_log_path=notification_audit_path)

            fetched = get_notification(
                investigation.correlation_id,
                viewer="dana",
                viewer_role="data_engineer",
                audit_log_path=notification_audit_path,
            )

            self.assertEqual(fetched, sent)

    def test_raises_not_found_for_an_unknown_investigation(self):
        with tempfile.TemporaryDirectory() as tmp:
            notification_audit_path = Path(tmp) / "notification_audit.jsonl"

            with self.assertRaises(NotificationNotFoundError):
                get_notification(
                    "no-such-investigation",
                    viewer="dana",
                    viewer_role="data_engineer",
                    audit_log_path=notification_audit_path,
                )

    def test_unauthorized_viewer_is_denied_and_audited_without_disturbing_the_notification(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = investigate(
                REPO_ROOT / "data_engineering_incident_test_3.json",
                audit_log_path=Path(tmp) / "investigation_audit.jsonl",
            )
            notification_audit_path = Path(tmp) / "notification_audit.jsonl"
            notify_if_uncertain(investigation, audit_log_path=notification_audit_path)
            self.assertNotIn("intern", ALLOWED_VIEWER_ROLES)

            with self.assertRaises(UnauthorizedNotificationAccessError):
                get_notification(
                    investigation.correlation_id,
                    viewer="mallory",
                    viewer_role="intern",
                    audit_log_path=notification_audit_path,
                )

            denials = [
                e
                for e in verify_log_integrity(notification_audit_path)
                if e.activity == "notification_access_denied"
            ]
            self.assertEqual(len(denials), 1)
            self.assertEqual(denials[0].outcome, "unauthorized")
            self.assertEqual(denials[0].details["attempted_by"], "mallory")

            # A legitimate viewer can still fetch it afterwards, unaffected.
            still_there = get_notification(
                investigation.correlation_id,
                viewer="dana",
                viewer_role="data_engineer",
                audit_log_path=notification_audit_path,
            )
            self.assertEqual(still_there.status, SENT)


class TrustAuditTrailTests(unittest.TestCase):
    def test_every_notification_attempt_is_logged_with_a_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            investigation = investigate(
                REPO_ROOT / "data_engineering_incident_test_3.json",
                audit_log_path=Path(tmp) / "investigation_audit.jsonl",
            )
            notification_audit_path = Path(tmp) / "notification_audit.jsonl"

            notify_if_uncertain(investigation, audit_log_path=notification_audit_path)

            entries = [
                e for e in verify_log_integrity(notification_audit_path) if e.activity == "notification_sent"
            ]
            self.assertEqual(len(entries), 1)
            self.assertTrue(entries[0].timestamp)


if __name__ == "__main__":
    unittest.main()
