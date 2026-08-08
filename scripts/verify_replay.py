"""Phase A migration verification: confirm analyze() output is bit-for-bit
unchanged across a refactor.

Replays every experiment's and reference validation's analyze() over its
already-recorded runs/ directory (no new runs executed) and either saves the
result as a baseline or diffs the current result against a previously saved
baseline. This is the verification tool RFC 0001 section 9 (Phase A) calls
for at each migration milestone.

Usage:
  python scripts/verify_replay.py --save-baseline migration/baseline
  python scripts/verify_replay.py --check migration/baseline
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from slimybug.aggregate import load_runs
from slimybug.experiment import EXPERIMENTS_DIR, REFERENCE_DIR, load_experiment


def discover_experiment_ids() -> list[str]:
    ids = set()
    for base in (EXPERIMENTS_DIR, REFERENCE_DIR):
        for path in base.glob("*/experiment.py"):
            ids.add(path.parent.name.split("-", 1)[0])
    return sorted(ids)


def snapshot(experiment_id: str) -> dict | None:
    experiment = load_experiment(experiment_id)
    runs = load_runs(experiment.runs_dir)
    if not runs:
        return None
    analysis = experiment.analyze(runs)
    return {
        "runs": sorted(runs, key=lambda r: r["run_id"]),
        "analysis": analysis,
    }


def canonical_json(data: dict) -> str:
    return json.dumps(data, sort_keys=True, indent=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--save-baseline", metavar="DIR", help="write current snapshots to DIR")
    group.add_argument("--check", metavar="DIR", help="diff current snapshots against baseline in DIR")
    args = parser.parse_args()

    ids = discover_experiment_ids()
    if args.save_baseline:
        out_dir = Path(args.save_baseline)
        out_dir.mkdir(parents=True, exist_ok=True)
        written = 0
        for eid in ids:
            snap = snapshot(eid)
            if snap is None:
                continue
            (out_dir / f"{eid}.json").write_text(canonical_json(snap))
            written += 1
        print(f"Saved {written} baseline snapshot(s) to {out_dir}/")
        return

    baseline_dir = Path(args.check)
    mismatches = []
    checked = 0
    for eid in ids:
        baseline_path = baseline_dir / f"{eid}.json"
        if not baseline_path.exists():
            continue
        current = snapshot(eid)
        current_json = canonical_json(current) if current is not None else None
        baseline_json = baseline_path.read_text()
        checked += 1
        if current_json != baseline_json:
            mismatches.append(eid)

    print(f"Checked {checked} experiment(s) against {baseline_dir}/")
    if mismatches:
        print(f"MISMATCH in {len(mismatches)}: {', '.join(mismatches)}")
        sys.exit(1)
    print("All snapshots match baseline (bit-for-bit).")


if __name__ == "__main__":
    main()
