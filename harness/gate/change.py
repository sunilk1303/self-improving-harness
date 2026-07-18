"""Candidate change format — the unit everything in the gate pipeline judges.

A change is data, never live code mutation: new/updated artifact files plus
an optional manifest diff, with the proposer's own claims (declared_tier,
predicted effect) attached. The gate treats every claim as untrusted input to
be cross-checked (docs/08 finding #4: self-attested tiers are privilege
escalation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


@dataclass
class CandidateChange:
    change_id: str
    description: str
    declared_tier: str                      # proposer's CLAIM — always cross-checked
    files: dict = field(default_factory=dict)          # path -> full new content
    manifest_diff: dict = field(default_factory=dict)  # dotted key -> new value
    evidence: list = field(default_factory=list)       # trace/limitation ids
    predicted_effect: str = ""

    @classmethod
    def from_yaml(cls, path: str | Path) -> "CandidateChange":
        with open(path, encoding="utf-8") as f:
            d = yaml.safe_load(f)
        return cls(
            change_id=d["change_id"],
            description=d.get("description", ""),
            declared_tier=d["declared_tier"],
            files=d.get("files", {}) or {},
            manifest_diff=d.get("manifest_diff", {}) or {},
            evidence=d.get("evidence", []) or [],
            predicted_effect=d.get("predicted_effect", ""),
        )
