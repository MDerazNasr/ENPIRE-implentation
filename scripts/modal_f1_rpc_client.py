#!/usr/bin/env python3
"""Fixed local client for the deployed F1 Modal RPC; not an agent command API."""

from __future__ import annotations

import argparse
import base64
import json
import subprocess
import sys

import modal


APP_NAME = "enpire-f1-worker-rpc-v1"
FUNCTION_NAME = "rpc"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expected-profile", required=True)
    parser.add_argument("--payload-b64", required=True)
    args = parser.parse_args()
    profile = subprocess.run(
        [sys.executable, "-m", "modal", "profile", "current"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    ).stdout.strip()
    if profile != args.expected_profile:
        raise SystemExit(f"active Modal profile {profile!r} is not approved")
    raw = base64.urlsafe_b64decode(args.payload_b64.encode("ascii"))
    payload = json.loads(raw)
    function = modal.Function.from_name(APP_NAME, FUNCTION_NAME)
    result = function.remote(payload)
    sys.stdout.write(json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
