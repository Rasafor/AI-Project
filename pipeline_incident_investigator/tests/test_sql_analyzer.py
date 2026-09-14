import unittest
from pathlib import Path

from pipeline_incident_investigator.sql_analyzer import analyze_query
from pipeline_incident_investigator.sql_source import load_incident_sql

REPO_ROOT = Path(__file__).resolve().parents[2]


class AnalyzeQueryTests(unittest.TestCase):
    def test_flags_select_star(self):
        issues = analyze_query("SELECT * FROM orders WHERE status = 'COMPLETED'")
        self.assertIn("select_star", [i.id for i in issues])

    def test_flags_delete_with_no_where(self):
        issues = analyze_query("DELETE FROM orders")
        self.assertIn("missing_where_on_mutation", [i.id for i in issues])

    def test_flags_update_with_no_where(self):
        issues = analyze_query("UPDATE orders SET status = 'CANCELLED'")
        self.assertIn("missing_where_on_mutation", [i.id for i in issues])

    def test_does_not_flag_delete_with_where(self):
        issues = analyze_query("DELETE FROM orders WHERE order_id = 'X1'")
        self.assertNotIn("missing_where_on_mutation", [i.id for i in issues])

    def test_flags_join_with_no_condition(self):
        issues = analyze_query("SELECT a.id FROM a JOIN b")
        self.assertIn("cartesian_join", [i.id for i in issues])

    def test_does_not_flag_join_with_on_condition(self):
        issues = analyze_query("SELECT a.id FROM a JOIN b ON a.id = b.id")
        self.assertNotIn("cartesian_join", [i.id for i in issues])

    def test_flags_column_not_in_given_schema(self):
        issues = analyze_query(
            "SELECT customer_id, customer_type FROM orders",
            current_schema_columns=["customer_id", "customer_category"],
        )
        self.assertIn("undefined_column", [i.id for i in issues])
        undefined = next(i for i in issues if i.id == "undefined_column")
        self.assertIn("customer_type", undefined.description)

    def test_no_schema_provided_skips_undefined_column_check(self):
        issues = analyze_query("SELECT anything, goes FROM orders")
        self.assertNotIn("undefined_column", [i.id for i in issues])

    def test_clean_query_reports_no_issues(self):
        issues = analyze_query(
            "SELECT customer_id, order_amount FROM orders WHERE order_status = 'COMPLETED'",
            current_schema_columns=["customer_id", "order_amount", "order_status"],
        )
        self.assertEqual(issues, [])

    def test_real_fixture_one_query_flags_the_actual_root_cause_column(self):
        sql = load_incident_sql(REPO_ROOT / "data_engineering_incident_test.json")
        issues = analyze_query(sql["query"], sql["current_schema_columns"])

        self.assertEqual([i.id for i in issues], ["undefined_column"])
        self.assertIn("customer_type", issues[0].description)

    def test_real_fixture_two_query_has_no_issues(self):
        sql = load_incident_sql(REPO_ROOT / "data_engineering_incident_test_2.json")
        issues = analyze_query(sql["query"], sql["current_schema_columns"])

        self.assertEqual(issues, [])


if __name__ == "__main__":
    unittest.main()
