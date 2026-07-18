"""Run the S1 static gate over the labeled E1 candidate suite and score it.

Each candidate YAML carries an `expected` block (passed / derived_tier /
fabrication). This harness runs the real gate and reports, per candidate,
whether the gate's verdict matched — plus aggregate tier-derivation accuracy,
fabrication-catch rate, and the pass/reject confusion counts.

    python scripts/run_gate_suite.py [--dir experiments/e1/candidates]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.gate.change import CandidateChange
from harness.gate.static_checks import run_static_gate


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default="experiments/e1/candidates")
    args = ap.parse_args()

    files = sorted(Path(args.dir).glob("*.yaml"))
    rows, mismatches = [], []
    tier_ok = fab_ok = pass_ok = 0

    for path in files:
        expected = yaml.safe_load(path.read_text(encoding="utf-8")).get("expected", {})
        change = CandidateChange.from_yaml(path)
        r = run_static_gate(change)

        t_ok = r.tier.derived_tier == expected.get("derived_tier")
        f_ok = r.fabrication == expected.get("fabrication")
        p_ok = r.passed == expected.get("passed")
        tier_ok += t_ok
        fab_ok += f_ok
        pass_ok += p_ok
        verdict = "PASS" if r.passed else "REJECT"
        flag = "" if (t_ok and f_ok and p_ok) else "  <-- MISMATCH"
        if flag:
            mismatches.append(change.change_id)
        rows.append(f"  {change.change_id:28s} tier={r.tier.derived_tier:6s} "
                    f"fab={str(r.fabrication):5s} {verdict:6s}{flag}")

    n = len(files)
    print(f"E1 static-gate suite: {n} candidates\n")
    print("\n".join(rows))
    print(f"\ntier-derivation accuracy : {tier_ok}/{n}")
    print(f"fabrication-flag accuracy: {fab_ok}/{n}")
    print(f"pass/reject accuracy     : {pass_ok}/{n}")
    if mismatches:
        print(f"\nMISMATCHES: {', '.join(mismatches)}")
        sys.exit(1)
    print("\nAll candidates scored as expected.")


if __name__ == "__main__":
    main()
