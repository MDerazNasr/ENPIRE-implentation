#!/usr/bin/env python3
"""Print the E0 pinned-RLinf actor-objective seam audit as JSON."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.rlt_objective_seam import audit_rlinf_objective_seam


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("rlinf_root", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit_rlinf_objective_seam(args.rlinf_root), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
