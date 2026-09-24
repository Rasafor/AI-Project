import json
import unittest
from pathlib import Path

from pipeline_incident_investigator.log_source import load_incident_logs
from pipeline_incident_investigator.pattern_matcher import (
    CONTEXT_WORDINGS,
    FOLLOW_UP_WORDINGS,
    SEEN_CASE_WORDINGS,
    counts_as_evidence,
    line_level,
    match_patterns,
)
from pipeline_incident_investigator.tests.fixtures import CLEAN_LOGS

REPO_ROOT = Path(__file__).resolve().parents[2]


class MatchPatternsTests(unittest.TestCase):
    def test_matches_schema_mismatch_pattern_in_fixture_one(self):
        logs = load_incident_logs(REPO_ROOT / "data_engineering_incident_test.json")
        matches = match_patterns(logs)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, "schema_mismatch")
        self.assertTrue(any("Cannot resolve column" in line for line in matches[0].evidence))

    def test_matches_resource_exhaustion_pattern_in_fixture_two(self):
        logs = load_incident_logs(REPO_ROOT / "data_engineering_incident_test_2.json")
        matches = match_patterns(logs)
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, "resource_exhaustion")
        self.assertTrue(any("ExecutorLostFailure" in line for line in matches[0].evidence))

    def test_no_match_for_logs_with_no_known_pattern(self):
        self.assertEqual(match_patterns(CLEAN_LOGS), [])

    # Rules added after the STORY-009 baseline pilot failed.
    def _categories(self, line):
        return [m.category for m in match_patterns([line])]

    def test_yarn_memory_limit_is_resource_exhaustion(self):
        line = "WARN Container killed by YARN for exceeding memory limits. 10.4 GB of 10 GB physical memory used"
        self.assertEqual(self._categories(line), ["Resource Exhaustion"])

    def test_postgres_missing_column_is_schema_change(self):
        line = 'ERROR psycopg2.errors.UndefinedColumn: column "customer_type" does not exist'
        self.assertEqual(self._categories(line), ["Schema Change"])

    def test_oom_inside_a_config_key_is_not_a_memory_failure(self):
        for line in ("INFO Effective config: memory.oom.kill_disable=false",
                     "INFO Effective config: spark.executor.oom.retry=true"):
            with self.subTest(line=line):
                self.assertEqual(self._categories(line), [])

    def test_bare_oom_still_matches(self):
        self.assertEqual(self._categories("ERROR executor 4 lost: OOM"), ["Resource Exhaustion"])


class ContextRuleTests(unittest.TestCase):
    """STORY-009 follow-up 2: only lines that show something going wrong count."""

    SPEC = json.loads((REPO_ROOT / "pilot" / "context_fix_spec.json").read_text(encoding="utf-8"))

    def test_code_wordings_are_exactly_the_committed_context_spec(self):
        spec = [(w["category"], w["pattern"]) for w in self.SPEC["wording_additions"]]
        code = [(cat, p) for cat, patterns in CONTEXT_WORDINGS.items() for p in patterns]
        self.assertEqual(code, spec)

    def test_line_levels(self):
        cases = {"2026 ERROR boom": "ERROR", "2026 FATAL: x": "FATAL", "2026 WARN y": "WARN",
                 "2026 WARNING y": "WARNING", "2026 INFO z": "INFO", "no level here": "INFO",
                 'level=error msg="x"': "ERROR",  # follow-up 3: logfmt levels
                 'level=info msg="retry after error"': "INFO",  # the field wins over words in the message
                 "2026 validated 0 error rows": "INFO"}  # bare lowercase words still set no level
        for line, level in cases.items():
            with self.subTest(line=line):
                self.assertEqual(line_level(line), level)

    def test_which_lines_count_as_evidence(self):
        self.assertTrue(counts_as_evidence("ERROR AnalysisException: x"))
        self.assertTrue(counts_as_evidence("FATAL: out of memory"))
        self.assertTrue(counts_as_evidence("WARN Container killed by YARN for exceeding memory limits"))
        self.assertTrue(counts_as_evidence("WARN Pod p terminated: reason=OOMKilled"))
        self.assertFalse(counts_as_evidence("WARN Data quality: 3 rows had an unknown column value"))
        self.assertFalse(counts_as_evidence("INFO Retry policy: on OutOfMemoryError retry once"))

    def test_keyword_on_a_non_fatal_warning_does_not_decide_the_cause(self):
        logs = ["WARN Data quality: 3 rows had an unknown column value in field country",
                "ERROR requests.exceptions.HTTPError: 503 Server Error: Service Unavailable"]
        self.assertEqual(match_patterns(logs), [])

    def test_new_context_wordings(self):
        self.assertEqual([m.category for m in match_patterns(["ERROR kernel: Out of memory: Killed process 1"])],
                         ["Resource Exhaustion"])
        self.assertEqual([m.category for m in match_patterns(
            ["ERROR DSQuotaExceededException: The DiskSpace quota of /user/etl is exceeded: quota = 1 TB"])],
            ["Resource Exhaustion"])


class SeenCaseChangesTests(unittest.TestCase):
    """STORY-009 follow-up 3: changes made after seeing every case, pinned to pilot/followup3_changes.json."""

    CHANGES = json.loads((REPO_ROOT / "pilot" / "followup3_changes.json").read_text(encoding="utf-8"))

    def test_code_wordings_are_exactly_the_recorded_changes(self):
        recorded = [(c["category"], c["pattern"]) for c in self.CHANGES["changes"] if c["kind"] == "wording"]
        code = [(cat, p) for cat, patterns in SEEN_CASE_WORDINGS.items() for p in patterns]
        self.assertEqual(sorted(code), sorted(recorded))

    def test_kubernetes_memory_eviction(self):
        line = "WARN Pod p evicted: The node was low on resource: memory. Container c was using 14Gi"
        self.assertEqual([m.category for m in match_patterns([line])], ["Resource Exhaustion"])

    def test_logfmt_error_with_escaped_quotes(self):
        line = 'time=07:00:09 level=error msg="query failed" err="pq: column \\"sku\\" does not exist"'
        self.assertEqual([m.category for m in match_patterns([line])], ["Schema Change"])

    def test_logfmt_info_line_is_still_ignored(self):
        self.assertEqual(match_patterns(['level=info msg="column \\"sku\\" does not exist, will create it"']), [])


class FollowUpSpecTests(unittest.TestCase):
    """STORY-009 follow-up 1: the code must learn exactly the committed list, no more and no less."""

    SPEC = json.loads((REPO_ROOT / "pilot" / "pattern_fix_spec.json").read_text(encoding="utf-8"))

    def test_code_wordings_are_exactly_the_committed_spec(self):
        spec = {}
        for addition in self.SPEC["additions"]:
            spec.setdefault(addition["category"], []).append(addition["wording"])
        self.assertEqual({k: list(v) for k, v in FOLLOW_UP_WORDINGS.items()}, spec)

    def test_every_spec_wording_is_recognized_under_its_category(self):
        for addition in self.SPEC["additions"]:
            line = f"ERROR something failed: {addition['wording']} (details)"
            with self.subTest(wording=addition["wording"]):
                self.assertEqual([m.category for m in match_patterns([line])], [addition["category"]])


if __name__ == "__main__":
    unittest.main()
