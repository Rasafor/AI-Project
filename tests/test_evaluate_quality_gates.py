import unittest

from scripts.evaluate_quality_gates import (
    UNCERTAIN,
    ablated_patterns,
    clopper_pearson_upper,
    criterion,
    score_output,
)

LOGS = ["2026-09-01 03:14:55 ERROR java.lang.OutOfMemoryError: Java heap space"]
GOOD = {"verdict": "Resource Exhaustion", "root_cause": "OOM", "recommended_action": "Raise memory",
        "evidence": LOGS[:], "error_class": None}


class ClopperPearsonTests(unittest.TestCase):
    def test_zero_failures_matches_the_closed_form(self):
        self.assertAlmostEqual(clopper_pearson_upper(0, 34), 1 - 0.05 ** (1 / 34), places=6)

    def test_bound_shrinks_as_evidence_grows_and_never_undercuts_the_point_estimate(self):
        self.assertGreater(clopper_pearson_upper(0, 10), clopper_pearson_upper(0, 100))
        self.assertGreater(clopper_pearson_upper(2, 34), 2 / 34)
        self.assertEqual(clopper_pearson_upper(5, 5), 1.0)


class ScoreOutputTests(unittest.TestCase):
    def test_a_correct_grounded_complete_output_passes_the_runtime_gate(self):
        s = score_output({"expected": "Resource Exhaustion"}, GOOD, LOGS)
        self.assertTrue(s["correct"] and s["grounded"] and s["complete"] and s["schema_ok"])
        self.assertFalse(s["hallucinated"])
        self.assertEqual(s["runtime_gate"], "PASS")

    def test_evidence_not_in_the_input_is_ungrounded_hallucinated_and_blocked(self):
        out = {**GOOD, "evidence": ["ERROR a line the model made up"]}
        s = score_output({"expected": "Resource Exhaustion"}, out, LOGS)
        self.assertFalse(s["grounded"])
        self.assertTrue(s["hallucinated"])
        self.assertEqual(s["runtime_gate"], "BLOCK")

    def test_asserting_a_cause_when_uncertain_was_right_is_an_unsafe_error(self):
        s = score_output({"expected": UNCERTAIN}, GOOD, LOGS)
        self.assertTrue(s["false_certain"])
        self.assertFalse(s["false_uncertain"])

    def test_saying_uncertain_when_a_cause_was_known_is_a_safe_escalation(self):
        s = score_output({"expected": "Schema Change"}, {"verdict": UNCERTAIN, "error_class": None}, LOGS)
        self.assertTrue(s["false_uncertain"])
        self.assertEqual(s["runtime_gate"], "ESCALATE")

    def test_a_certain_output_missing_its_action_is_incomplete(self):
        s = score_output({"expected": "Resource Exhaustion"}, {**GOOD, "recommended_action": " "}, LOGS)
        self.assertFalse(s["complete"])


class CriterionTests(unittest.TestCase):
    def test_unmeasured_is_never_reported_as_pass(self):
        self.assertEqual(criterion("x", "n", None, "t", None, True)["status"], "NOT_MEASURED")

    def test_a_soft_miss_warns_and_a_hard_miss_fails(self):
        self.assertEqual(criterion("x", "n", 0, "t", False, False)["status"], "WARN")
        self.assertEqual(criterion("x", "n", 0, "t", False, True)["status"], "FAIL")


class AblationTests(unittest.TestCase):
    def test_ablated_patterns_no_longer_match_seen_case_wordings_but_keep_the_rest(self):
        by_cat = {p.category: p for p in ablated_patterns()}
        self.assertIsNone(by_cat["Resource Exhaustion"].matcher.search("node low on resource: memory"))
        self.assertIsNotNone(by_cat["Resource Exhaustion"].matcher.search("java.lang.OutOfMemoryError"))


if __name__ == "__main__":
    unittest.main()
