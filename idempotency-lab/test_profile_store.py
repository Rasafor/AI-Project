import sqlite3
import tempfile
import threading
import unittest
from pathlib import Path

from profile_store import (
    IdempotencyKeyConflictError,
    ProfileNotFoundError,
    ProfileValidationError,
    connect,
    create_profile,
    get_profile,
    state_fingerprint,
    update_profile,
)

FIXED_NOW = "2026-10-02T12:00:00+00:00"


def _events(conn):
    return [tuple(row) for row in conn.execute("SELECT event_key, event_type FROM outbox ORDER BY id")]


class IdempotencyTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect()
        create_profile(self.conn, "u-1", "Ada", "ada@old.example")

    def update(self, changes, key="k-1", **kwargs):
        return update_profile(self.conn, "u-1", changes, idempotency_key=key, now=lambda: FIXED_NOW, **kwargs)

    def test_happy_path_applies_the_change_once(self):
        result = self.update({"email": "ada@new.example", "add_tags": ["vip"]})
        self.assertFalse(result.replayed)
        self.assertEqual(result.changed_fields, ["email", "tags"])
        profile = get_profile(self.conn, "u-1")
        self.assertEqual((profile["email"], profile["tags"], profile["version"]), ("ada@new.example", ["vip"], 2))
        self.assertEqual(len(_events(self.conn)), 1)

    def test_running_the_same_request_n_times_gives_the_same_end_state_as_once(self):
        request = {"email": "ada@new.example", "add_tags": ["vip", "beta"], "display_name": "Ada L."}
        self.update(request)
        after_one = state_fingerprint(self.conn)
        for _ in range(5):
            result = self.update(request)
            self.assertTrue(result.replayed)
            self.assertEqual(state_fingerprint(self.conn), after_one)
        self.assertEqual(get_profile(self.conn, "u-1")["version"], 2)
        self.assertEqual(len(_events(self.conn)), 1)

    def test_a_replay_returns_the_same_response_as_the_original(self):
        first = self.update({"add_tags": ["vip"]})
        again = self.update({"add_tags": ["vip"]})
        self.assertEqual((first.profile, first.changed_fields), (again.profile, again.changed_fields))

    def test_set_semantics_make_a_repeat_with_a_new_key_a_no_op_on_the_profile(self):
        # Even without the key store, "be X" applied twice is still X.
        self.update({"email": "ada@new.example", "add_tags": ["vip"]}, key="k-1")
        profile_after_one = get_profile(self.conn, "u-1")
        result = self.update({"email": "ada@new.example", "add_tags": ["vip"]}, key="k-2")
        self.assertEqual(result.changed_fields, [])
        self.assertEqual(get_profile(self.conn, "u-1"), profile_after_one)  # no version bump, no updated_at change
        self.assertEqual(len(_events(self.conn)), 1)

    def test_equivalent_inputs_normalize_to_the_same_request(self):
        self.update({"email": "  Ada@New.Example ", "add_tags": ["VIP", "beta", "vip"]})
        result = self.update({"add_tags": ["beta", "vip"], "email": "ada@new.example"})
        self.assertTrue(result.replayed)  # same key, logically identical payload -> treated as the same request

    def test_a_late_retry_does_not_undo_a_newer_change(self):
        self.update({"email": "ada@first.example"}, key="k-1")
        self.update({"email": "ada@second.example"}, key="k-2")
        self.update({"email": "ada@first.example"}, key="k-1")  # delayed retry of k-1
        self.assertEqual(get_profile(self.conn, "u-1")["email"], "ada@second.example")

    def test_reusing_a_key_for_a_different_request_is_rejected_and_writes_nothing(self):
        self.update({"display_name": "Ada L."})
        before = state_fingerprint(self.conn)
        with self.assertRaises(IdempotencyKeyConflictError):
            self.update({"display_name": "Someone else"})
        self.assertEqual(state_fingerprint(self.conn), before)

    def test_a_crash_before_commit_leaves_no_trace_and_the_retry_succeeds_once(self):
        before = state_fingerprint(self.conn)

        def crash():
            raise ConnectionError("simulated crash after writes, before commit")

        with self.assertRaises(ConnectionError):
            self.update({"email": "ada@new.example"}, before_commit=crash)
        self.assertEqual(state_fingerprint(self.conn), before)  # no half-written profile, event or key

        result = self.update({"email": "ada@new.example"})
        self.assertFalse(result.replayed)
        self.assertEqual(len(_events(self.conn)), 1)

    def test_concurrent_duplicates_apply_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp) / "profiles.db")
            setup = connect(path)
            create_profile(setup, "u-1", "Ada", "ada@old.example")
            setup.close()
            results, barrier = [], threading.Barrier(5)

            def worker():
                conn = connect(path)
                barrier.wait()
                results.append(update_profile(conn, "u-1", {"email": "ada@new.example"}, idempotency_key="k-1"))
                conn.close()

            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(10)

            self.assertEqual(sorted(r.replayed for r in results), [False, True, True, True, True])
            check = connect(path)
            self.assertEqual(get_profile(check, "u-1")["version"], 2)
            self.assertEqual(len(_events(check)), 1)
            check.close()

    def test_re_seeding_a_profile_is_a_no_op(self):
        create_profile(self.conn, "u-1", "Someone else", "other@example.com")
        self.assertEqual(get_profile(self.conn, "u-1")["display_name"], "Ada")


class FailurePathTests(unittest.TestCase):
    def setUp(self):
        self.conn = connect()
        create_profile(self.conn, "u-1", "Ada", "ada@old.example")

    def assert_rejected_without_writes(self, changes, key="k-1", user_id="u-1", error=ProfileValidationError):
        before = state_fingerprint(self.conn)
        with self.assertRaises(error):
            update_profile(self.conn, user_id, changes, idempotency_key=key)
        self.assertEqual(state_fingerprint(self.conn), before)

    def test_malformed_input_is_rejected_before_any_write(self):
        bad_requests = [
            {},
            {"is_admin": True},  # not an editable field
            {"email": "not-an-email"},
            {"email": 42},
            {"display_name": "   "},
            {"display_name": "x" * 101},
            {"add_tags": "vip"},
            {"add_tags": [""]},
            {"add_tags": ["vip"], "remove_tags": ["VIP"]},
        ]
        for changes in bad_requests:
            with self.subTest(changes=changes):
                self.assert_rejected_without_writes(changes)

    def test_a_missing_key_is_rejected(self):
        for key in ("", "   "):
            self.assert_rejected_without_writes({"display_name": "Ada L."}, key=key)

    def test_an_unknown_user_is_rejected_and_the_key_is_not_burned(self):
        self.assert_rejected_without_writes({"display_name": "X"}, user_id="nobody", error=ProfileNotFoundError)

    def test_too_many_tags_is_rejected_inside_the_transaction_and_rolled_back(self):
        self.assert_rejected_without_writes({"add_tags": [f"t{i}" for i in range(21)]})

    def test_the_connection_is_usable_after_a_rollback(self):
        with self.assertRaises(ProfileNotFoundError):
            update_profile(self.conn, "nobody", {"display_name": "X"}, idempotency_key="k-1")
        update_profile(self.conn, "u-1", {"display_name": "Ada L."}, idempotency_key="k-1")
        self.assertFalse(self.conn.in_transaction)
        self.assertIsInstance(self.conn, sqlite3.Connection)


if __name__ == "__main__":
    unittest.main()
