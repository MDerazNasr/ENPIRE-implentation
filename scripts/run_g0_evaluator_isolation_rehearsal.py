#!/usr/bin/env python3
"""Create a non-authorizing local G0 evaluator-isolation rehearsal."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.build_g0_evaluator_bundle import build_bundle, verify_bundle
from supervisor.evaluator_deployment import build_local_isolation_receipt


def run_rehearsal(
    *, private_final: Path, bundle_output: Path, ledger_root: Path,
    anchor_root: Path, repository: Path = ROOT,
) -> dict:
    for path, field in ((ledger_root, "ledger root"), (anchor_root, "anchor root")):
        if path.exists():
            raise ValueError(f"{field} already exists")
        path.mkdir(parents=True, mode=0o700)
        os.chmod(path, 0o700)
    manifest = build_bundle(bundle_output, repository)
    verified = verify_bundle(bundle_output)
    if verified != manifest:
        raise ValueError("evaluator bundle verification was not stable")
    return build_local_isolation_receipt(
        repository=repository,
        private_final=private_final,
        bundle_root=bundle_output,
        bundle_manifest=manifest,
        ledger_root=ledger_root,
        anchor_root=anchor_root,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-final", type=Path, required=True)
    parser.add_argument("--bundle-output", type=Path, required=True)
    parser.add_argument("--ledger-root", type=Path, required=True)
    parser.add_argument("--anchor-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists")
    result = run_rehearsal(
        private_final=args.private_final,
        bundle_output=args.bundle_output,
        ledger_root=args.ledger_root,
        anchor_root=args.anchor_root,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
