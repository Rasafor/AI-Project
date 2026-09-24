"""Run the STORY-009 pilot and save its results and audit trail under pilot/results/.

Usage (from the repo root):
  python scripts/run_pilot.py <label> [--operator NAME] [--role ROLE]

<label> names the run (e.g. "baseline", "optimized") and is also its run_id, so
the audit keys are stable. Idempotent: if pilot/results/<label>.json already
exists the script stops without re-running, rather than overwriting recorded
results with new timings. The saved trail can be checked independently with
audit_log.verify_log_integrity().

Exit code: 0 pilot passed, 1 pilot failed, 2 could not run.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from pipeline_incident_investigator.pilot import (  # noqa: E402 -- needs the repo root on sys.path first
    PilotAuditError,
    PilotConfigError,
    UnauthorizedPilotAccessError,
    run_pilot,
)

EXPECTED_PATH = REPO_ROOT / "pilot" / "expected.json"
RESULTS_DIR = REPO_ROOT / "pilot" / "results"


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Run the STORY-009 pilot.")
    parser.add_argument("label", help="name of this run, e.g. baseline or optimized")
    parser.add_argument("--operator", default="pilot-operator")
    parser.add_argument("--role", default="data_engineer")
    args = parser.parse_args(argv)

    results_path = RESULTS_DIR / f"{args.label}.json"
    if results_path.exists():
        print(f"{results_path.relative_to(REPO_ROOT)} already exists; not re-running (results are recorded once).")
        return 0

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        result = run_pilot(EXPECTED_PATH, operator=args.operator, operator_role=args.role,
                           audit_log_path=RESULTS_DIR / f"{args.label}_audit_trail.jsonl", run_id=args.label)
    except (UnauthorizedPilotAccessError, PilotConfigError, PilotAuditError) as exc:
        print(f"Pilot could not run: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2

    results_path.write_text(json.dumps(asdict(result), indent=2) + "\n", encoding="utf-8")
    print_table(result)
    print(f"\nSaved {results_path.relative_to(REPO_ROOT)} and {args.label}_audit_trail.jsonl")
    return 0 if result.passed else 1


def print_table(result) -> None:
    print(f"{'case':<40} {'expected':<20} {'verdict':<20} {'ok':<4} {'seconds':>8}")
    for c in result.cases:
        tag = " (test)" if c.synthetic else " (real)"
        print(f"{Path(c.path).name + tag:<40} {c.expected:<20} {c.verdict:<20} "
              f"{'yes' if c.correct else 'NO':<4} {c.duration_seconds:>8.3f}")
    print(f"\nErrors: {result.errors}/{result.total} = {result.error_rate:.1%} "
          f"(limit {result.error_rate_threshold:.0%})")
    print(f"Time: slowest {result.max_seconds:.3f}s, median {result.median_seconds:.3f}s "
          f"(limit {result.time_budget_seconds:.0f}s per case)")
    print(f"PILOT {'PASSED' if result.passed else 'FAILED'}")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
