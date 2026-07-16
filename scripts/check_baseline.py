"""Baseline comparator (AD-8, spec §8). Re-runs retrieval-only eval and fails if
recall@5 drops more than the tolerance band vs. `evals/baseline.json`.

NOT wired into CI yet (AD-8): CI has no Postgres and no embedded corpus, so it
cannot run this script at all. A seeded-fixture strategy for CI is a Week-4
decision. This script is meant to be run locally/manually before a PR that
touches chunking, retrieval, fusion, or thresholds (CLAUDE.md rule 4), and is
the mechanical half of that rule — the eval run itself is still required in
the PR/commit message regardless of what this script reports.

Compares recall@5 only (spec §8's designated "most stable CI signal"); recall@10
and MRR are reported for context but do not gate. Tolerance is an absolute-point
drop, not relative (spec §8: a bad number is a big deal at this corpus size).

Usage (from core/):
    uv run python ../scripts/check_baseline.py
    uv run python ../scripts/check_baseline.py --tolerance 0.05 --slug far-25
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from groundcite.config import get_settings
from groundcite.container import build_services

_REPO_ROOT = Path(__file__).resolve().parent.parent
_BASELINE_PATH = _REPO_ROOT / "evals" / "baseline.json"

# spec §8: recall@5 is the designated stable CI signal; this is the ONLY gating
# metric. An absolute-point drop, not relative — a 5pt drop on ~60 cases is a
# handful of regressed cases, which is exactly the granularity worth failing on.
_DEFAULT_TOLERANCE = 0.05


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--slug", default="far-25")
    ap.add_argument("--baseline", type=Path, default=_BASELINE_PATH)
    ap.add_argument(
        "--tolerance",
        type=float,
        default=_DEFAULT_TOLERANCE,
        help="Max allowed recall@5 drop (absolute points) before failing.",
    )
    args = ap.parse_args()

    if not args.baseline.exists():
        print(f"no baseline found at {args.baseline} — nothing to compare against", file=sys.stderr)
        return 2
    baseline = json.loads(args.baseline.read_text(encoding="utf-8"))

    settings = get_settings()
    services = build_services(settings)

    print(f"baseline git sha : {baseline['git_sha']}")
    print(f"baseline recorded: {baseline['recorded_at']}")
    print(f"tolerance         : {args.tolerance:.3f} recall@5 points")
    print()

    header = (
        f"{'suite':<10} {'metric':<12} {'baseline':>10} {'current':>10} {'delta':>8} {'gate':>6}"
    )
    print(header)
    print("-" * len(header))

    failed_suites: list[str] = []
    for suite, base_metrics in baseline["suites"].items():
        report = services.evals.run_retrieval(
            suite,
            git_sha=baseline["git_sha"],
            document_slugs=[args.slug],
        )
        current = {
            "recall_at_5": report.recall_at_5,
            "recall_at_10": report.recall_at_10,
            "mrr": report.mrr,
        }
        gate_ok = True
        for metric in ("recall_at_5", "recall_at_10", "mrr"):
            base_v = base_metrics[metric]
            cur_v = current[metric]
            delta = cur_v - base_v
            gates = metric == "recall_at_5"
            passed = (not gates) or delta >= -args.tolerance
            gate_ok = gate_ok and passed
            mark = "PASS" if passed else "FAIL"
            mark = mark if gates else "  —"
            row = f"{suite:<10} {metric:<12} {base_v:>10.3f} {cur_v:>10.3f}"
            row += f" {delta:>+8.3f} {mark:>6}"
            print(row)
        if not gate_ok:
            failed_suites.append(suite)

    print()
    if failed_suites:
        bad = ", ".join(failed_suites)
        print(f"FAIL: recall@5 dropped more than {args.tolerance:.3f} on: {bad}")
        return 1
    print("PASS: recall@5 within tolerance on all suites.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
