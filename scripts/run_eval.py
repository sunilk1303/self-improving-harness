"""Run the labeled manifest's agent over a golden slice and print the report.

    python scripts/run_eval.py [--label prod] [--slice public] [--data data]
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


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", default="prod")
    ap.add_argument("--slice", default="public", choices=["public", "private"])
    ap.add_argument("--data", default="data")
    ap.add_argument("--generations", type=int, default=1,
                    help="answers per question; LLM-routed questions only re-run")
    args = ap.parse_args()

    manifest = resolve_label(args.label)
    version = load_labels()[args.label]
    ledger = Ledger(Path(args.data) / "ledger.jsonl")
    agent = BaselineAgent(manifest, ledger=ledger)

    slice_path = Path(args.data) / "golden" / f"{args.slice}.jsonl"
    report_path = Path(args.data) / "reports" / f"eval-{version}-{args.slice}.json"
    report = run_slice_file(agent, slice_path, version, ledger, report_path,
                            generations=args.generations)
    agent.close()

    printable = {k: v for k, v in report.items() if k != "per_question"}
    print(json.dumps(printable, indent=2))
    print(f"\nfull report -> {report_path}")
    print("ledger:", ledger.verify()[1])


if __name__ == "__main__":
    main()
