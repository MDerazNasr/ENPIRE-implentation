#!/usr/bin/env python3
"""Audit the frozen C0 Claude CLI contract without submitting a prompt."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.provider_contract import audit_local_contract  # noqa: E402
from supervisor.canonical import canonical_json  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--claude", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    command = args.claude or (Path(found) if (found := shutil.which("claude")) else None)
    if command is None:
        parser.error("Claude CLI was not found; pass --claude with an absolute path")
    command = command.absolute()
    report = audit_local_contract(command, ROOT)
    rendered = canonical_json(report) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        sys.stdout.write(rendered)
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
