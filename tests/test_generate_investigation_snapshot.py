"""Tests for scripts/generate_investigation_snapshot.py (STORY-007).

Loaded by path since /scripts has no __init__.py -- it is a collection of
one-off repo-root operational scripts, not an importable package.
"""

import importlib.util
import tempfile
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "generate_investigation_snapshot.py"

spec = importlib.util.spec_from_file_location("generate_investigation_snapshot", SCRIPT_PATH)
snapshot_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snapshot_module)


class BuildSnapshotTests(unittest.TestCase):
    def test_produces_one_entry_per_fixture_with_correct_certainty(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_trail_path = Path(tmp) / "audit.jsonl"

            snapshot = snapshot_module.build_snapshot(audit_trail_path)

            self.assertIn("generated_at", snapshot)
            self.assertEqual(len(snapshot["incidents"]), 3)

            by_id = {inc["incident_id"]: inc for inc in snapshot["incidents"]}
            self.assertEqual(set(by_id), {"INC-2026-001", "INC-2026-002", "INC-2026-003"})

            # INC-2026-001: real "Schema Change" recommendation -- certain, major, pending.
            inc1 = by_id["INC-2026-001"]
            self.assertTrue(inc1["certain"])
            self.assertIsNone(inc1["notification"])
            self.assertEqual(inc1["recommendation"]["category"], "Schema Change")
            self.assertTrue(inc1["recommendation"]["is_major"])
            self.assertEqual(inc1["recommendation"]["status"], "pending_approval")

            # INC-2026-002: real "Resource Exhaustion" recommendation -- certain, minor, auto-approved.
            inc2 = by_id["INC-2026-002"]
            self.assertTrue(inc2["certain"])
            self.assertFalse(inc2["recommendation"]["is_major"])
            self.assertEqual(inc2["recommendation"]["status"], "auto_approved")

            # INC-2026-003: no known pattern -- uncertain, notified.
            inc3 = by_id["INC-2026-003"]
            self.assertFalse(inc3["certain"])
            self.assertIsNone(inc3["recommendation"])
            self.assertEqual(inc3["notification"]["status"], "sent")

    def test_every_incident_has_its_full_real_audit_trail_including_the_final_activity(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_trail_path = Path(tmp) / "audit.jsonl"

            snapshot = snapshot_module.build_snapshot(audit_trail_path)
            by_id = {inc["incident_id"]: inc for inc in snapshot["incidents"]}

            # Certain incidents: log_analysis, recommendation, recommendation_submitted.
            activities_1 = [e["activity"] for e in by_id["INC-2026-001"]["audit_entries"]]
            self.assertEqual(activities_1, ["log_analysis", "recommendation", "recommendation_submitted"])
            for entry in by_id["INC-2026-001"]["audit_entries"]:
                self.assertTrue(entry["timestamp"])

            # Uncertain incident: log_analysis, recommendation (no_recommendation), notification_sent.
            # This is the entry that a correlation_id-only filter would miss -- see the module
            # docstring's explanation of why notify_if_uncertain audits under its own id.
            activities_3 = [e["activity"] for e in by_id["INC-2026-003"]["audit_entries"]]
            self.assertEqual(activities_3, ["log_analysis", "recommendation", "notification_sent"])

    def test_rerunning_produces_a_clean_trail_not_a_doubled_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            audit_trail_path = Path(tmp) / "audit.jsonl"

            snapshot_module.build_snapshot(audit_trail_path)
            second = snapshot_module.build_snapshot(audit_trail_path)

            inc1 = next(i for i in second["incidents"] if i["incident_id"] == "INC-2026-001")
            self.assertEqual(len(inc1["audit_entries"]), 3)  # not 6 -- no duplication across runs

    def test_raises_rather_than_producing_a_broken_snapshot_when_the_audit_log_cannot_be_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            blocking_file = Path(tmp) / "not_a_directory"
            blocking_file.write_text("blocking")
            audit_trail_path = blocking_file / "audit.jsonl"

            with self.assertRaises(Exception):
                snapshot_module.build_snapshot(audit_trail_path)


if __name__ == "__main__":
    unittest.main()
