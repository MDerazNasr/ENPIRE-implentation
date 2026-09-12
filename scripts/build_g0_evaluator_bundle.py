#!/usr/bin/env python3
"""Build a hash-manifested read-only G0 evaluator bundle outside the repo."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import stat
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    "run_evaluator.py": "scripts/g0_independent_evaluator.py",
    "supervisor/__init__.py": None,
    "supervisor/canonical.py": "supervisor/canonical.py",
    "supervisor/evaluator_integrity.py": "supervisor/evaluator_integrity.py",
    "supervisor/g0_decision.py": "supervisor/g0_decision.py",
    "agent/__init__.py": None,
}


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def build_bundle(output: Path, root: Path = ROOT) -> dict:
    output = output.resolve()
    root = root.resolve()
    if _inside(output, root):
        raise ValueError("evaluator bundle must be outside the repository")
    if output.exists():
        raise ValueError("evaluator bundle output already exists")
    artifacts = []
    for destination, source in FILES.items():
        target = output / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        if source is None:
            target.write_text("\"\"\"Minimal isolated evaluator package.\"\"\"\n", encoding="utf-8")
        else:
            shutil.copy2(root / source, target)
        content = target.read_bytes()
        artifacts.append({"path": destination, "size_bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()})
    payload = {
        "schema_version": 1,
        "bundle_role": "g0-independent-evaluator",
        "artifacts": sorted(artifacts, key=lambda item: item["path"]),
        "evaluation_authorized": False,
        "gpu_execution_authorized": False,
        "promotion_authorized": False,
    }
    manifest = {"payload": payload, "sha256": hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for path in sorted(output.rglob("*"), reverse=True):
        path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH | (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH if path.is_dir() else 0))
    output.chmod(0o555)
    return manifest


def verify_bundle(output: Path) -> dict:
    output = output.resolve()
    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if set(manifest) != {"payload", "sha256"}:
        raise ValueError("evaluator bundle manifest fields are invalid")
    payload = manifest["payload"]
    expected_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if manifest["sha256"] != expected_hash:
        raise ValueError("evaluator bundle manifest hash mismatch")
    if payload.get("bundle_role") != "g0-independent-evaluator":
        raise ValueError("evaluator bundle role is invalid")
    for field in ("evaluation_authorized", "gpu_execution_authorized", "promotion_authorized"):
        if payload.get(field) is not False:
            raise ValueError("evaluator bundle grants forbidden authority")
    declared = {item["path"] for item in payload.get("artifacts", [])}
    if declared != set(FILES):
        raise ValueError("evaluator bundle artifact inventory is invalid")
    for item in payload["artifacts"]:
        path = output / item["path"]
        content = path.read_bytes()
        if len(content) != item["size_bytes"] or hashlib.sha256(content).hexdigest() != item["sha256"]:
            raise ValueError("evaluator bundle artifact mismatch")
    actual = {
        str(path.relative_to(output))
        for path in output.rglob("*")
        if path.is_file() and path.name != "manifest.json"
    }
    if actual != declared:
        raise ValueError("evaluator bundle contains undeclared files")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    manifest = build_bundle(args.output)
    verify_bundle(args.output)
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
