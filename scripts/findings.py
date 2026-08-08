"""findings list/show/compare -- RFC 0001 SS7's `findings` CLI verbs,
against the finding.json storage convention slimybug/finding.py defines.
`compare` is the shallow tier only (status, validity, scope) -- a rich,
quantitative diff into analysis_ref's actual measured values needs
mechanism-template-specific interpretation core can't provide generically
(RFC 0001 SS3), unbuilt regardless of compatibility.

Usage:
  python scripts/findings.py list
  python scripts/findings.py show 011
  python scripts/findings.py compare 011 R003
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from slimybug.finding import Finding, compatible, find_all, load


def cmd_list(_args) -> None:
    paths = find_all()
    if not paths:
        print("No finding.json found under experiments/ or reference/")
        return

    header = f"{'id':6s} {'grade':10s} {'status':10s} {'refines':8s} claim"
    print(header)
    print("-" * len(header))
    for path in paths:
        f = Finding.read(path)
        claim = f.claim if len(f.claim) <= 70 else f.claim[:67] + "..."
        print(f"{f.id:6s} {f.evidence.grade:10s} {f.status:10s} {(f.refines or '-'):8s} {claim}")


def cmd_show(args) -> None:
    try:
        f = load(args.finding_id)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    print(f"Finding {f.id}  [{f.status}, {f.evidence.grade}-grade]")
    if f.refines:
        print(f"  refines: {f.refines}")
    if f.supersedes:
        print(f"  supersedes: {f.supersedes}")
    print()
    print(f.claim)
    print()
    print(f"Scope (experiment {f.scope.experiment_id}):")
    print(f"  swept: {f.scope.swept.variable} over {f.scope.swept.tested_values}")
    print(f"  fixed_params: {f.scope.fixed_params}")
    print()
    print("Evidence:")
    print(f"  n_per_condition: {f.evidence.n_per_condition}")
    print(f"  variance_reported: {f.evidence.variance_reported}")
    total_runs = sum(len(v) for v in f.evidence.run_ids.values())
    print(f"  run_ids: {len(f.evidence.run_ids)} cells, {total_runs} runs total")
    print(f"  analysis_ref: {f.evidence.analysis_ref}")
    print()
    print("Validity checks:")
    for v in f.validity_checks:
        mark = "PASS" if v.passed else "FAIL"
        print(f"  [{mark}] {v.name}{': ' + v.note if v.note else ''}")
    print()
    print(f"Narrative: {f.narrative_ref}")


def cmd_compare(args) -> None:
    try:
        a = load(args.finding_a)
        b = load(args.finding_b)
    except FileNotFoundError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

    is_compatible, reason = compatible(a, b)
    if not is_compatible:
        print(f"{a.id} and {b.id} are NOT comparable: {reason}")
        sys.exit(1)

    print(f"{a.id} vs {b.id}  ({reason})")
    print()
    print(f"{'':20s} {a.id:25s} {b.id:25s}")
    print(f"{'status':20s} {a.status:25s} {b.status:25s}")
    print(f"{'grade':20s} {a.evidence.grade:25s} {b.evidence.grade:25s}")
    print(f"{'swept.variable':20s} {a.scope.swept.variable:25s} {b.scope.swept.variable:25s}")
    print(f"{'n_per_condition':20s} {str(a.evidence.n_per_condition):25s} {str(b.evidence.n_per_condition):25s}")
    print()

    print("fixed_params (shared keys only):")
    shared = set(a.scope.fixed_params) & set(b.scope.fixed_params)
    for k in sorted(shared):
        av, bv = a.scope.fixed_params[k], b.scope.fixed_params[k]
        flag = "" if av == bv else "  <-- differs"
        print(f"  {k:25s} {str(av):15s} {str(bv):15s}{flag}")
    only_a = set(a.scope.fixed_params) - shared
    only_b = set(b.scope.fixed_params) - shared
    if only_a:
        print(f"  only in {a.id}: {sorted(only_a)}")
    if only_b:
        print(f"  only in {b.id}: {sorted(only_b)}")
    print()

    print("validity checks:")
    names = {v.name for v in a.validity_checks} | {v.name for v in b.validity_checks}
    a_checks = {v.name: v.passed for v in a.validity_checks}
    b_checks = {v.name: v.passed for v in b.validity_checks}
    for name in sorted(names):
        a_mark = "PASS" if a_checks.get(name) else ("FAIL" if name in a_checks else "-")
        b_mark = "PASS" if b_checks.get(name) else ("FAIL" if name in b_checks else "-")
        print(f"  {name:30s} {a_mark:10s} {b_mark:10s}")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="list every Finding")

    p_show = sub.add_parser("show", help="show one Finding's structured fields")
    p_show.add_argument("finding_id", help="e.g. 011, R003")

    p_compare = sub.add_parser("compare", help="shallow compare two Findings (status/validity/scope)")
    p_compare.add_argument("finding_a", help="e.g. 011")
    p_compare.add_argument("finding_b", help="e.g. R003")

    args = parser.parse_args()
    if args.command == "list":
        cmd_list(args)
    elif args.command == "show":
        cmd_show(args)
    elif args.command == "compare":
        cmd_compare(args)


if __name__ == "__main__":
    main()
