"""Generate the synthetic business, doc corpus, and golden slices.

    python scripts/generate.py [--seed 1303] [--out data]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.ledger import Ledger
from harness.synth.docs import generate_docs
from harness.synth.generator import PlantedParams, generate
from harness.synth.questions import emit, write_slices


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=1303)
    ap.add_argument("--out", default="data")
    args = ap.parse_args()

    out = Path(args.out)
    params = PlantedParams(seed=args.seed)
    db_path = out / "business.duckdb"

    print(f"generating business (seed={args.seed}) -> {db_path}")
    generate(db_path, params)
    docs = generate_docs(out / "docs", params)
    print(f"wrote {len(docs)} docs -> {out / 'docs'}")

    questions = emit(db_path, params)
    counts = write_slices(questions, out / "golden")
    tripwires = sum(1 for q in questions if q.tripwire)
    print(f"golden questions: {counts['public']} public / {counts['private']} private "
          f"({tripwires} tripwires) -> {out / 'golden'}")

    ledger = Ledger(out / "ledger.jsonl")
    ledger.append("dataset_generated",
                  {"seed": args.seed, "db": str(db_path),
                   "public": counts["public"], "private": counts["private"],
                   "tripwires": tripwires})
    print("ledger event appended:", ledger.verify()[1])


if __name__ == "__main__":
    main()
