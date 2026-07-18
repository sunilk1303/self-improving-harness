"""A/A calibration: run the same manifest N times over the public slice and
measure the gate's false-accept rate and CI width (the noise floor).

With the deterministic VQR-only baseline the deltas are exactly zero — the run
validates the machinery. With an LLM leg enabled, per-run nondeterminism makes
this the real E0 noise-floor measurement.

    python scripts/aa_calibration.py [--runs 10] [--label prod] [--data data]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.agent.baseline import BaselineAgent
from harness.ledger import Ledger
from harness.manifest import load_labels, resolve_label
from harness.evalkit.runner import run_slice_file
from harness.evalkit.stats import aa_calibration


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=10)
    ap.add_argument("--label", default="prod")
    ap.add_argument("--data", default="data")
    ap.add_argument("--generations", type=int, default=1,
                    help="answers per question per run; LLM-routed only re-run")
    args = ap.parse_args()

    manifest = resolve_label(args.label)
    version = load_labels()[args.label]
    slice_path = Path(args.data) / "golden" / "public.jsonl"

    run_scores = []
    for i in range(args.runs):
        agent = BaselineAgent(manifest)  # no ledger: A/A runs are calibration, not serving
        report = run_slice_file(agent, slice_path, version,
                                generations=args.generations)
        agent.close()
        run_scores.append([r["score"] for r in report["per_question"]])
        print(f"run {i + 1}/{args.runs}: accuracy={report['accuracy']}")

    result = aa_calibration(run_scores)
    result["generations"] = args.generations
    print(json.dumps(result, indent=2))

    ledger = Ledger(Path(args.data) / "ledger.jsonl")
    ledger.append("aa_calibration", {"manifest_version": version, **result})
    print("ledger:", ledger.verify()[1])


if __name__ == "__main__":
    main()
