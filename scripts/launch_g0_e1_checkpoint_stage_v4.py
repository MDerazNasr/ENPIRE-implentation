#!/usr/bin/env python3
"""Mint one fresh verifier session and launch the checkpoint staging app."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path


SOURCE_PROFILE = "enpire-evaluator-verifier-final"
ACCOUNT = "960946312280"
TARGET_ROLE_ARN = f"arn:aws:iam::{ACCOUNT}:role/enpire-g0-receipt-verifier"
TARGET_SESSION_NAME = "enpire-g0-stage-v4"
STAGE_SECRET_NAME = "enpire-g0-e1-stage-v4-aws"
EXPECTED_TARGET_ARN = (
    f"arn:aws:sts::{ACCOUNT}:assumed-role/"
    f"enpire-g0-receipt-verifier/{TARGET_SESSION_NAME}"
)
MINIMUM_MINTED_TTL_SECONDS = 3500
MODAL_COMMAND = (
    "modal",
    "run",
    "--detach",
    "modal_e1_checkpoint_stage_v4.py",
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


def _publish_named_secret(credentials: dict[str, str]) -> None:
    descriptor, path_text = tempfile.mkstemp(prefix="enpire-stage-v4-", suffix=".json")
    path = Path(path_text)
    try:
        os.fchmod(descriptor, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(credentials, handle, sort_keys=True)
        completed = subprocess.run(
            [
                "modal",
                "secret",
                "create",
                STAGE_SECRET_NAME,
                "--from-json",
                str(path),
            ],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if completed.returncode:
            raise RuntimeError("failed to create the unique named staging secret")
    finally:
        path.unlink(missing_ok=True)


def _delete_named_secret() -> None:
    subprocess.run(
        [
            "modal",
            "secret",
            "delete",
            "--allow-missing",
            "--yes",
            STAGE_SECRET_NAME,
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-checkpoint-access", action="store_true")
    args = parser.parse_args()
    contract = {
        "command": list(MODAL_COMMAND),
        "duration_seconds": 3600,
        "gpu_used": False,
        "named_secret": STAGE_SECRET_NAME,
        "named_secret_cleanup_required_after_terminal_state": True,
        "source_profile": SOURCE_PROFILE,
        "target_role_arn": TARGET_ROLE_ARN,
    }
    if not args.execute:
        print(json.dumps({**contract, "status": "dry_run"}, indent=2, sort_keys=True))
        return 0
    if not args.acknowledge_checkpoint_access:
        parser.error("--execute requires --acknowledge-checkpoint-access")

    credentials, source_arn = _fresh_target_credentials()
    _publish_named_secret(credentials)
    try:
        completed = subprocess.run(MODAL_COMMAND, check=False)
    except BaseException:
        _delete_named_secret()
        raise
    if completed.returncode:
        _delete_named_secret()
    print(
        json.dumps(
            {
                **contract,
                "exit_code": completed.returncode,
                "source_arn": source_arn,
                "named_secret_cleanup_required": completed.returncode == 0,
                "status": "submitted" if completed.returncode == 0 else "failed",
            },
            indent=2,
            sort_keys=True,
        )
    )
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
