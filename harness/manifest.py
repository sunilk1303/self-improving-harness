"""Harness Manifest: a pinned lockfile of everything that defines the running agent.

Deploy = repoint a label at a manifest version; rollback = repoint back.
Every eval report and ledger event carries the manifest version, so any answer
is attributable to an exact harness configuration.
"""

from __future__ import annotations

from pathlib import Path

import yaml

MANIFESTS_DIR = Path("manifests")


def load_manifest(version: str, manifests_dir: str | Path = MANIFESTS_DIR) -> dict:
    path = Path(manifests_dir) / f"{version}.yaml"
    with open(path, encoding="utf-8") as f:
        m = yaml.safe_load(f)
    if m.get("version") != version:
        raise ValueError(f"manifest {path} declares version {m.get('version')!r}, "
                         f"expected {version!r}")
    return m


def load_labels(manifests_dir: str | Path = MANIFESTS_DIR) -> dict:
    with open(Path(manifests_dir) / "labels.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_label(label: str, manifests_dir: str | Path = MANIFESTS_DIR) -> dict:
    labels = load_labels(manifests_dir)
    if label not in labels:
        raise KeyError(f"unknown label {label!r}; have {sorted(labels)}")
    return load_manifest(labels[label], manifests_dir)


def repoint(label: str, version: str, ledger=None,
            manifests_dir: str | Path = MANIFESTS_DIR) -> dict:
    """Move a label to a manifest version (deploy/rollback). Ledger-logged."""
    load_manifest(version, manifests_dir)  # must exist and be valid
    labels_path = Path(manifests_dir) / "labels.yaml"
    labels = load_labels(manifests_dir)
    old = labels.get(label)
    labels[label] = version
    with open(labels_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(labels, f, sort_keys=True)
    if ledger is not None:
        ledger.append("label_moved", {"label": label, "from": old, "to": version})
    return labels
