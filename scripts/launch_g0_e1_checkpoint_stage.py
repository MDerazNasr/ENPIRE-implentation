#!/usr/bin/env python3
"""Mint one fresh verifier session and launch the checkpoint staging app."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from datetime import datetime, timezone


SOURCE_PROFILE = "enpire-evaluator-verifier-final"
ACCOUNT = "960946312280"
TARGET_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/enpire-g0-receipt-verifier"
TARGET_SESSION_NAME = "enpire-g0-stage-v1"
EXPECTED_TARGET_ARN = (
    f"arn:aws:sts::{ACCOUNT}:assumed-role/"
    f"enpire-g0-receipt-verifier/{TARGET_SESSION_NAME}"
)
MINIMUM_MINTED_TTL_SECONDS = 3500
MODAL_COMMAND = (
    "modal",
    "run",
    "--detach",
    "modal_e1_checkpoint_stage_v1.py",
    "--acknowledge-checkpoint-stage",
)


def _run_json(argv: list[str]) -> dict[str, object]:
    completed = subprocess.run(
        argv,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    value = json.loads(completed.stdout)
    if not isinstance(value, dict):
        raise RuntimeError("AWS command returned a non-object response")
    return value


def _fresh_target_credentials() -> tuple[dict[str, str], str]:
    source = _run_json(
        ["aws", "sts", "get-caller-identity", "--profile", SOURCE_PROFILE]
    )
    source_arn = source.get("Arn")
    if source.get("Account") != ACCOUNT or not isinstance(source_arn, str):
        raise RuntimeError("source AWS identity account mismatch")
    if "assumed-role/AWSReservedSSO_ENPIREG0VerifierAccess_" not in source_arn:
        raise RuntimeError("source AWS identity is not the dedicated verifier")

    assumed = _run_json(
        [
            "aws",
            "sts",
            "assume-role",
            "--profile",
            SOURCE_PROFILE,
            "--role-arn",
            TARGET_ROLE_ARN,
            "--role-session-name",
            TARGET_SESSION_NAME,
            "--duration-seconds",
            "3600",
        ]
    )
    identity = assumed.get("AssumedRoleUser")
    credentials = assumed.get("Credentials")
    if not isinstance(identity, dict) or identity.get("Arn") != EXPECTED_TARGET_ARN:
        raise RuntimeError("fresh target role identity mismatch")
    if not isinstance(credentials, dict):
        raise RuntimeError("fresh target role credentials are missing")
    expiration_text = credentials.get("Expiration")
    if not isinstance(expiration_text, str):
        raise RuntimeError("fresh target role expiration is missing")
    expiration = datetime.fromisoformat(expiration_text.replace("Z", "+00:00"))
    remaining = (expiration - datetime.now(timezone.utc)).total_seconds()
    if remaining < MINIMUM_MINTED_TTL_SECONDS:
        raise RuntimeError("fresh target role has less than 3500 seconds remaining")
    names = {
        "AWS_ACCESS_KEY_ID": "AccessKeyId",
        "AWS_SECRET_ACCESS_KEY": "SecretAccessKey",
        "AWS_SESSION_TOKEN": "SessionToken",
    }
    environment: dict[str, str] = {}
    for environment_name, response_name in names.items():
        value = credentials.get(response_name)
        if not isinstance(value, str) or not value:
            raise RuntimeError("fresh target role credential field is missing")
        environment[environment_name] = value
    environment["AWS_CREDENTIAL_EXPIRATION"] = expiration_text
    return environment, source_arn


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-checkpoint-access", action="store_true")
    args = parser.parse_args()
    contract = {
        "command": list(MODAL_COMMAND),
        "duration_seconds": 3600,
        "gpu_used": False,
        "source_profile": SOURCE_PROFILE,
        "target_role_arn": TARGET_ROLE_ARN,
    }
    if not args.execute:
        print(json.dumps({**contract, "status": "dry_run"}, indent=2, sort_keys=True))
        return 0
    if not args.acknowledge_checkpoint_access:
        parser.error("--execute requires --acknowledge-checkpoint-access")

    credentials, source_arn = _fresh_target_credentials()
    environment = {**os.environ, **credentials}
    completed = subprocess.run(MODAL_COMMAND, env=environment, check=False)
    print(
        json.dumps(
            {
                **contract,
                "exit_code": completed.returncode,
                "source_arn": source_arn,
                "status": "submitted" if completed.returncode == 0 else "failed",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
