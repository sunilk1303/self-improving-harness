"""Verified Query Repository loader — the VQR as a manifest-pinned artifact.

Entries live in `artifacts/vqr/<version>.yaml`, not in code: the improvement
loop proposes new entries as diffs to a NEW artifact version, and a human
activates them by pinning that version in a manifest (a T2 change). Loading
validates every entry (pattern compiles; SQL passes the read-only allowlist)
so a malformed or write-capable entry can never be served.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from .llm import validate_sql

ARTIFACTS_DIR = Path("artifacts") / "vqr"


@dataclass(frozen=True)
class VQREntry:
    id: str
    pattern: re.Pattern
    sql: str
    params: tuple[str, ...]

    def match(self, question_text: str):
        return self.pattern.search(question_text.strip())

    def bind(self, m: re.Match) -> list[str]:
        groups = m.groupdict()
        return [groups[p] for p in self.params]


def vqr_path(version: str, artifacts_dir: str | Path = ARTIFACTS_DIR) -> Path:
    return Path(artifacts_dir) / f"{version}.yaml"


def load_vqr(version: str, artifacts_dir: str | Path = ARTIFACTS_DIR) -> list[VQREntry]:
    path = vqr_path(version, artifacts_dir)
    with open(path, encoding="utf-8") as f:
        doc = yaml.safe_load(f)
    if doc.get("version") != version:
        raise ValueError(f"VQR artifact {path} declares version "
                         f"{doc.get('version')!r}, expected {version!r}")
    entries = []
    seen: set[str] = set()
    for raw in doc.get("entries", []):
        eid = raw["id"]
        if eid in seen:
            raise ValueError(f"duplicate VQR entry id {eid!r} in {path}")
        seen.add(eid)
        sql = validate_sql(raw["sql"])  # read-only allowlist, raises on writes
        pattern = re.compile(raw["question_pattern"], re.I)
        params = tuple(raw.get("params", []))
        missing = set(params) - set(pattern.groupindex)
        if missing:
            raise ValueError(f"VQR entry {eid!r}: params {sorted(missing)} "
                             f"not captured by question_pattern")
        if sql.count("?") != len(params):
            raise ValueError(f"VQR entry {eid!r}: {sql.count('?')} SQL "
                             f"placeholders but {len(params)} params")
        entries.append(VQREntry(eid, pattern, sql, params))
    return entries
