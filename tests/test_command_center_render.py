"""Tests for the Command Center (STORY-000): every tab renders from the
real .colaberry data files, every card drills down, and nothing claims a
result the data files do not contain.

Background: on 2026-09-13 the platform moved plan.json to schema v2
(schedule and dates can be null, roles became plain names, owners moved to
`owner_agent`, `verification` is null until checked). The page was never
updated and most tabs crashed to a blank screen without any test failing.
These tests render the shipped JavaScript through Node, so a future data
change that breaks a tab fails here instead.

Needs `node` on PATH; skipped otherwise.
"""

import copy
import json
import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDERER = REPO_ROOT / "tests" / "command_center_render.js"
NODE = shutil.which("node")

TABS = ["overview", "investigations", "outcomes", "users", "guardrails",
        "systems", "pm", "agents", "kb", "datamodel"]


def load(rel):
    return json.loads((REPO_ROOT / rel).read_text(encoding="utf-8"))


def real_data():
    return {
        "plan": load(".colaberry/plan.json"),
        "progress": load(".colaberry/progress.json"),
        "investigations": load("command-center/data/investigations_snapshot.json"),
    }


def render(data):
    proc = subprocess.run(
        [NODE, str(RENDERER)], input=json.dumps(data), capture_output=True,
        text=True, encoding="utf-8", timeout=30, check=False,
    )
    if proc.returncode != 0:
        raise AssertionError(f"renderer exited {proc.returncode}: {proc.stderr}")
    return json.loads(proc.stdout)


@unittest.skipUnless(NODE, "node is not installed")
class RealDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = real_data()
        cls.out = render(cls.data)

    def test_every_tab_renders_in_both_modes(self):
        for mode in ("real", "sample"):
            for tab in TABS:
                with self.subTest(mode=mode, tab=tab):
                    self.assertIsNone(self.out[f"{mode}/{tab}"]["error"])

    def test_every_card_drills_down_one_level(self):
        for mode in ("real", "sample"):
            for tab in TABS:
                result = self.out[f"{mode}/{tab}"]
                with self.subTest(mode=mode, tab=tab):
                    self.assertTrue(result["details"], "tab offers no drill-down")
                for key, html in result["details"].items():
                    with self.subTest(mode=mode, tab=tab, card=key):
                        self.assertIn("cc-detail", html)
                        self.assertNotIn("ERROR:", html)

    def test_sample_mode_is_labelled_wherever_it_changes_the_page(self):
        for tab in TABS:
            real, sample = self.out[f"real/{tab}"]["html"], self.out[f"sample/{tab}"]["html"]
            if real != sample:
                with self.subTest(tab=tab):
                    self.assertIn("cc-sample-badge", sample)

    def test_overview_headline_comes_from_progress_totals(self):
        totals = self.data["progress"]["totals"]
        html = self.out["real/overview"]["html"]
        self.assertIn(f"{totals['stories_verified']} / {totals['stories_total']}", html)
        self.assertIn(f"{totals['criteria_passed']} / {totals['criteria_total']}", html)
        points = self.out["real/overview"]["details"]["points"]
        self.assertIn(f"{totals['points_awarded']} awarded so far", points)

    def test_systems_are_never_green_in_real_mode(self):
        html = self.out["real/systems"]["html"]
        self.assertNotIn("cc-dot green", html)
        self.assertIn("Not checked from here", html)


@unittest.skipUnless(NODE, "node is not installed")
class DataShapeTests(unittest.TestCase):
    def test_unchecked_story_shows_not_checked_rather_than_a_state(self):
        data = real_data()
        for s in data["progress"]["stories"]:
            s["verification"] = None
        out = render(data)
        self.assertIsNone(out["real/pm"]["error"])
        self.assertIn("Not checked yet", out["real/pm"]["html"])
        self.assertNotIn("Verified", out["real/pm"]["html"])

    def test_dated_plan_lays_out_by_date_and_flags_slippage(self):
        data = real_data()
        plan = data["plan"]
        plan["schedule"] = {"build_start": "2026-08-30", "build_end": "2026-10-01",
                            "demo_day": "2026-10-08", "demo_release_key": "r4"}
        for i, r in enumerate(plan["releases"]):
            r["starts_on"], r["ends_on"] = f"2026-09-0{i + 1}", f"2026-09-1{i + 1}"
        plan["stories"][0]["due_baseline_on"] = "2026-09-01"
        plan["stories"][0]["due_on"] = "2026-09-05"
        html = render(data)["real/pm"]["html"]
        self.assertIn("2026-09-01 → 2026-09-11", html)
        self.assertIn("slipped", html)

    def test_deleting_a_story_from_the_plan_removes_it_from_the_page(self):
        data = real_data()
        gone = data["plan"]["stories"][-1]["id"]
        data["plan"]["stories"] = data["plan"]["stories"][:-1]
        out = render(data)
        self.assertNotIn(gone, out["real/pm"]["html"])
        self.assertNotIn(gone, out["real/overview"]["details"]["stories"])

    def test_render_is_deterministic(self):
        data = real_data()
        first = render(copy.deepcopy(data))
        second = render(copy.deepcopy(data))
        # The PM tab's "today" marker depends on the clock; everything else
        # must be byte-identical across runs.
        for key in first:
            if key.endswith("/pm"):
                continue
            self.assertEqual(first[key]["html"], second[key]["html"], key)


if __name__ == "__main__":
    unittest.main()
