"""End-to-end cascade demo on the real generated business — deterministic, free.

Runs a candidate through S1->S2->S3->S4 with a DETERMINISTIC eval_fn (the
VQR-only agent, no LLM), so the paid stages are exercised on real golden-slice
accuracy without any Azure cost or nondeterminism. Proves the orchestration
discriminates a genuine improvement from a subtle regression.

Incumbent = v0. Candidates propose vqr_version v1; the eval_fn resolves each
manifest's vqr_version to the right artifact directory (v0 = shipped artifacts,
v1 = the candidate's file staged in a temp dir).

    python scripts/run_cascade_demo.py experiments/e1/candidates/cand-11-good-churn-vq.yaml
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from harness.agent.baseline import BaselineAgent
from harness.gate.cascade import run_cascade
from harness.gate.change import CandidateChange
from harness.ledger import Ledger
from harness.evalkit.runner import run_slice_file


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("candidate")
    ap.add_argument("--data", default="data")
    ap.add_argument("--generations", type=int, default=1)
    args = ap.parse_args()

    data = Path(args.data)
    snapshot = data / "business.duckdb"
    change = CandidateChange.from_yaml(args.candidate)

    base_manifest = {"version": "v0",
                     "agent": {"router": "vqr-first", "nl2sql": "none",
                               "vqr_version": "v0"},
                     "data": {"snapshot": str(snapshot)}}

    # stage the candidate's v1 artifact so the eval_fn can load it by version
    tmp = Path(tempfile.mkdtemp(prefix="cascade-demo-"))
    cand_vqr_dir = tmp / "vqr"
    shutil.copytree("artifacts/vqr", cand_vqr_dir)
    for rel, content in change.files.items():
        if rel.replace("\\", "/").startswith("artifacts/vqr/"):
            (cand_vqr_dir / Path(rel).name).write_text(str(content), encoding="utf-8")

    def eval_fn(manifest, slice_name):
        version = manifest["agent"].get("vqr_version", "v0")
        vqr_dir = cand_vqr_dir if version != "v0" else Path("artifacts/vqr")
        agent = BaselineAgent(manifest, vqr_artifacts_dir=vqr_dir)
        try:
            return run_slice_file(agent, data / "golden" / f"{slice_name}.jsonl",
                                  manifest["version"], generations=args.generations)
        finally:
            agent.close()

    ledger = Ledger(data / "ledger.jsonl")
    result = run_cascade(change, base_manifest, snapshot=snapshot,
                         workdir=tmp / "sandbox", eval_fn=eval_fn, ledger=ledger)

    print(f"\ncandidate : {change.change_id}")
    print(f"declared  : {change.declared_tier}   derived: {result.derived_tier}")
    print(f"reached   : {result.reached}   failed_at: {result.failed_at}")
    if result.public:
        p = result.public
        print(f"S3 public : delta={p.mean_delta:+.4f} CI[{p.ci_low:+.4f},{p.ci_high:+.4f}] "
              f"paired={p.n_paired} -> {'ACCEPT' if p.accepted else 'REJECT'}")
        print(f"            {p.reason}")
        if p.regressing_strata:
            print(f"            regressing strata: {p.regressing_strata}")
    if result.private_accept is not None:
        print(f"S4 private: {'ACCEPT' if result.private_accept else 'REJECT'}")
    print(f"\nVERDICT   : {'ACCEPTED' if result.accepted else 'REJECTED'}")
    print("ledger    :", ledger.verify()[1])
    shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    main()
