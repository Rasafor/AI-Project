"""Score the investigator's outputs against the Gate 1 (release) quality-gate criteria.

    python scripts/evaluate_quality_gates.py [--out pilot/results/quality-gate-<date>.json]

Runs every case in pilot/expected.json through investigate() (audit trail goes to a
temp dir, so the repo is not written to except the report), then scores accuracy,
grounding, hallucination, completeness, schema validity, consistency, regression and
latency. Criteria this harness cannot measure (relevance, safety red-team, user
feedback) are reported as NOT_MEASURED, never as PASS: an unmeasured hard criterion
caps the overall verdict at WARN.

Also reports:
- first-sight accuracy: each case's verdict in the first recorded run that contained
  it, i.e. before any fix informed by that case (the most honest accuracy estimate);
- a contamination ablation: accuracy with SEEN_CASE_WORDINGS removed, since
  pattern_matcher.py says those were added after seeing every pilot case;
- the release verdict each historical pilot run would have received.
"""

from __future__ import annotations

import argparse
import json
import re
import statistics
import sys
import tempfile
import time
from datetime import date
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from pipeline_incident_investigator import pattern_matcher  # noqa: E402
from pipeline_incident_investigator.investigator import investigate  # noqa: E402
from pipeline_incident_investigator.log_source import LogsIncompleteError, LogsUnavailableError  # noqa: E402
from pipeline_incident_investigator.recommendation import RecommendationGenerationError  # noqa: E402

UNCERTAIN, ERROR = "uncertain", "error"
CATEGORIES = {"Schema Change", "Resource Exhaustion"}
PRODUCTION_RUN = "followup-3"  # the run currently treated as production
HISTORY = ["baseline", "run-2026-09-24", "fixed", "optimized", "followup-1", "followup-2", "followup-3"]
CONSISTENCY_RUNS = 5
SECRET_RE = re.compile(r"(api[_-]?key|secret|password|token)\s*[:=]\s*\S{8,}|sk-[A-Za-z0-9-]{20,}", re.IGNORECASE)


def run_case(path: Path, audit: Path) -> dict:
    """One output: verdict plus the full recommendation, timed. Known failures become verdict 'error'."""
    start = time.perf_counter()
    try:
        rec = investigate(path, audit_log_path=audit).recommendation
    except (LogsUnavailableError, LogsIncompleteError, RecommendationGenerationError) as exc:
        return {"verdict": ERROR, "error_class": type(exc).__name__, "seconds": time.perf_counter() - start}
    out = {"verdict": rec.category if rec else UNCERTAIN, "seconds": time.perf_counter() - start, "error_class": None}
    if rec:
        out.update(root_cause=rec.root_cause, recommended_action=rec.recommended_action,
                   evidence=list(rec.evidence), pattern_id=rec.pattern_id)
    return out


def score_output(case: dict, out: dict, logs: list[str]) -> dict:
    """Per-output checks (these are also the Gate 2 runtime checks)."""
    certain = out["verdict"] not in (UNCERTAIN, ERROR)
    evidence = out.get("evidence", [])
    grounded = all(line in logs for line in evidence)
    schema_ok = not certain or (
        isinstance(out.get("root_cause"), str) and isinstance(out.get("recommended_action"), str)
        and isinstance(evidence, list) and all(isinstance(e, str) for e in evidence)
    )
    complete = not certain or bool(out.get("root_cause", "").strip() and out.get("recommended_action", "").strip()
                                   and evidence)
    hallucinated = certain and (out["verdict"] not in CATEGORIES or not evidence or not grounded)
    text = json.dumps(out)
    return {
        "correct": out["verdict"] == case["expected"],
        "certain": certain,
        "false_certain": certain and case["expected"] == UNCERTAIN,          # unsafe: asserted a cause it shouldn't
        "false_uncertain": out["verdict"] == UNCERTAIN and case["expected"] != UNCERTAIN,  # safe: escalated
        "grounded": grounded, "schema_ok": schema_ok, "complete": complete, "hallucinated": hallucinated,
        "secret_in_output": bool(SECRET_RE.search(text)),
        "runtime_gate": "BLOCK" if (not schema_ok or not grounded or hallucinated)
        else "ESCALATE" if out["verdict"] in (UNCERTAIN, ERROR) else "PASS",
    }


def clopper_pearson_upper(failures: int, n: int, alpha: float = 0.05) -> float:
    """One-sided 95% upper bound on the true failure rate (exact binomial), by bisection."""
    if failures >= n:
        return 1.0

    def cdf(p: float) -> float:  # P(X <= failures) for X ~ Binomial(n, p)
        total, term = 0.0, (1 - p) ** n
        for k in range(failures + 1):
            total += term
            term *= (n - k) / (k + 1) * p / (1 - p) if p < 1 else 0
        return total

    lo, hi = failures / n, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if cdf(mid) > alpha else (lo, mid)
    return hi


def ablated_patterns():
    """KNOWN_PATTERNS with the SEEN_CASE_WORDINGS alternatives stripped off the end of each regex."""
    rebuilt = []
    for p in pattern_matcher.KNOWN_PATTERNS:
        suffix = "|" + "|".join(pattern_matcher.SEEN_CASE_WORDINGS[p.category])
        source = p.matcher.pattern
        if not source.endswith(suffix):
            raise RuntimeError(f"cannot ablate {p.id}: seen-case wordings are not the regex suffix")
        rebuilt.append(pattern_matcher.LogPattern(p.id, p.category, p.description,
                                                  re.compile(source[: -len(suffix)], re.IGNORECASE)))
    return tuple(rebuilt)


def criterion(cid, name, value, threshold, ok, hard, note=""):
    status = "NOT_MEASURED" if ok is None else "PASS" if ok else ("FAIL" if hard else "WARN")
    return {"id": cid, "name": name, "value": value, "threshold": threshold, "status": status,
            "type": "hard" if hard else "soft", "note": note}


def history_verdicts() -> list[dict]:
    rows = []
    for run in HISTORY:
        d = json.loads((REPO / "pilot/results" / f"{run}.json").read_text(encoding="utf-8"))
        acc = 1 - d["errors"] / d["total"]
        rows.append({"run": run, "cases": d["total"], "errors": d["errors"], "accuracy": round(acc, 4),
                     "error_upper_95": round(clopper_pearson_upper(d["errors"], d["total"]), 4),
                     "gate_1_1": "PASS" if acc >= 0.90 else "FAIL"})
    return rows


def first_sight(cases: list[dict]) -> dict:
    seen: dict[str, bool] = {}
    for run in HISTORY:
        for c in json.loads((REPO / "pilot/results" / f"{run}.json").read_text(encoding="utf-8"))["cases"]:
            seen.setdefault(c["path"], c["correct"])
    wrong = sum(not v for v in seen.values())
    return {"cases": len(seen), "wrong": wrong, "accuracy": round(1 - wrong / len(seen), 4),
            "error_upper_95": round(clopper_pearson_upper(wrong, len(seen)), 4)}


def evaluate() -> dict:
    expected = json.loads((REPO / "pilot/expected.json").read_text(encoding="utf-8"))
    cases = expected["cases"]
    prod = {c["path"]: c for c in json.loads(
        (REPO / "pilot/results" / f"{PRODUCTION_RUN}.json").read_text(encoding="utf-8"))["cases"]}

    with tempfile.TemporaryDirectory() as tmp:
        audit = Path(tmp) / "audit.jsonl"
        rows = []
        for case in cases:
            path = REPO / case["path"]
            logs = json.loads(path.read_text(encoding="utf-8")).get("execution_logs", [])
            runs = [run_case(path, audit) for _ in range(CONSISTENCY_RUNS)]
            out = runs[0]
            agree = sum((r["verdict"], r.get("evidence")) == (out["verdict"], out.get("evidence")) for r in runs)
            rows.append({"path": case["path"], "expected": case["expected"], "verdict": out["verdict"],
                         "holdout": "holdout" in case["path"], "consistency": agree / CONSISTENCY_RUNS,
                         "seconds": statistics.median(r["seconds"] for r in runs),
                         "evidence": out.get("evidence", []), **score_output(case, out, logs)})
        with mock.patch.object(pattern_matcher, "KNOWN_PATTERNS", ablated_patterns()):
            ablated = {c["path"]: run_case(REPO / c["path"], audit)["verdict"] for c in cases}

    n = len(rows)
    wrong = sum(not r["correct"] for r in rows)
    certain = [r for r in rows if r["certain"]]
    acc = 1 - wrong / n
    prod_acc = sum(c["correct"] for c in prod.values()) / len(prod)
    regressions = [r["path"] for r in rows if prod.get(r["path"], {}).get("correct") and not r["correct"]]
    p95 = sorted(r["seconds"] for r in rows)[max(0, int(0.95 * n) - 1)]
    upper = clopper_pearson_upper(wrong, n)
    ablated_wrong = [p for p in ablated if ablated[p] != next(c["expected"] for c in cases if c["path"] == p)]
    rate = lambda key, pool: sum(r[key] for r in pool) / len(pool) if pool else 1.0  # noqa: E731

    criteria = [
        criterion("1.1", "Accuracy", round(acc, 4), ">= 0.90 and no drop > 2 pts vs production",
                  acc >= 0.90 and acc >= prod_acc - 0.02, True,
                  f"{n - wrong}/{n} correct; production ({PRODUCTION_RUN}) {prod_acc:.2%}"),
        criterion("1.1s", "Accuracy is statistically shown (95% upper bound on error rate)", round(upper, 4),
                  f"<= {expected['error_rate_threshold']}", upper <= expected["error_rate_threshold"], False,
                  f"{wrong} errors in {n} cases cannot rule out a true error rate up to {upper:.1%}"),
        criterion("1.2", "Factual grounding (evidence lines present verbatim in the input logs)",
                  round(rate("grounded", certain), 4), ">= 0.95", rate("grounded", certain) >= 0.95, True,
                  f"over {len(certain)} outputs that assert a root cause"),
        criterion("1.3", "Hallucination rate", round(rate("hallucinated", certain), 4), "<= 0.02",
                  rate("hallucinated", certain) <= 0.02, True,
                  f"false-certain (asserted a cause when 'uncertain' was right): "
                  f"{sum(r['false_certain'] for r in rows)}"),
        criterion("1.4", "Relevance (rubric 1-5)", None, ">= 4.0", None, False,
                  "Needs a human rubric or an LLM judge; the Anthropic API is a paid service, off until the owner"
                  " enables it. Verdicts here are categories, so relevance is largely implied by 1.1."),
        criterion("1.5", "Completeness (root cause + action + evidence)", round(rate("complete", certain), 4),
                  ">= 0.95", rate("complete", certain) >= 0.95, False),
        criterion("1.6", "Schema validity", round(rate("schema_ok", rows), 4), "1.00", rate("schema_ok", rows) == 1,
                  True),
        criterion("1.7", "Safety and policy (red-team set)", None, "1.00", None, True,
                  f"No red-team set exists. Partial check only: secrets in outputs = "
                  f"{sum(r['secret_in_output'] for r in rows)}; injection/PII cases untested."),
        criterion("1.8", "Consistency (same verdict and evidence over 5 runs)", round(rate("consistency", rows), 4),
                  ">= 0.85", rate("consistency", rows) >= 0.85, False),
        criterion("1.9", "Regression vs production", len(regressions), "0", not regressions, True,
                  ", ".join(regressions)),
        criterion("1.10", "Latency p95 (seconds)", round(p95, 4), f"<= {expected['time_budget_seconds']}",
                  p95 <= expected["time_budget_seconds"], False),
        criterion("1.E", "Evaluation set is independent of the system under test",
                  f"{len(ablated_wrong)} case(s) pass only via SEEN_CASE_WORDINGS", "0", not ablated_wrong, False,
                  "All 34 cases were seen during development; first-sight accuracy is the independent estimate. "
                  + ", ".join(ablated_wrong)),
    ]
    statuses = [(c["status"], c["type"]) for c in criteria]
    if ("FAIL", "hard") in statuses:
        verdict = "BLOCK"
    elif any(s != "PASS" for s, _ in statuses):
        verdict = "WARN"
    else:
        verdict = "PASS"

    return {
        "evaluated_on": date.today().isoformat(), "gate": "Gate 1 (release)", "verdict": verdict,
        "criteria": criteria,
        "runtime_gate_counts": {k: sum(r["runtime_gate"] == k for r in rows) for k in ("PASS", "ESCALATE", "BLOCK")},
        "error_split": {"false_certain_unsafe": sum(r["false_certain"] for r in rows),
                        "false_uncertain_safe": sum(r["false_uncertain"] for r in rows)},
        "first_sight": first_sight(cases),
        "ablation_without_seen_case_wordings": {"wrong": len(ablated_wrong), "accuracy": round(1 - len(ablated_wrong) / n, 4),
                                                "cases": ablated_wrong},
        "history": history_verdicts(),
        "gate_3_production": "NOT_MEASURED: no production traffic or user feedback exists yet.",
        "cases": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=str(REPO / "pilot/results" / f"quality-gate-{date.today().isoformat()}.json"))
    report = evaluate()
    Path(parser.parse_args().out).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Gate 1 verdict: {report['verdict']}")
    for c in report["criteria"]:
        print(f"  [{c['status']:<12}] {c['id']:<5} {c['name']}: {c['value']} (target {c['threshold']})")
    print(f"  runtime gate: {report['runtime_gate_counts']}  errors: {report['error_split']}")
    print(f"  first-sight: {report['first_sight']}")
    print(f"  ablation: {report['ablation_without_seen_case_wordings']}")
    for h in report["history"]:
        print(f"  history {h['run']:<15} {h['errors']}/{h['cases']} wrong  acc={h['accuracy']:.1%}  "
              f"err<= {h['error_upper_95']:.1%}  1.1={h['gate_1_1']}")


if __name__ == "__main__":
    main()
