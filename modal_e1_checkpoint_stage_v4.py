"""Create-only CPU staging of the exact checkpoint-2000 object on Modal.

This app performs no GPU work and no simulator rollout. It writes a terminal
receipt even when S3 access, download, size verification, or hashing fails.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import modal

from e1_staged_checkpoint_runtime import (
    STAGE_SCHEMA_VERSION,
    STAGE_STATUS_COMPLETE,
    bounded_error,
    sha256_file,
)


APP_NAME = "enpire-g0-e1-checkpoint-stage-v4"
STAGE_SECRET_NAME = "enpire-g0-e1-stage-v4-aws"
WORKSPACE = "/workspace"
RESULTS_ROOT = f"{WORKSPACE}/e1-l40s-results"
STAGE_ROOT = Path(f"{WORKSPACE}/e1-checkpoints/step-2000-stage-v4")
STAGED_CHECKPOINT = STAGE_ROOT / "actor/model_state_dict/full_weights.pt"
STAGE_RECEIPT = Path(RESULTS_ROOT) / "step-2000-stage-v4-terminal.json"
BUCKET = "enpire-g0-evaluator-evidencebucket-atlpylr0fwjq"
CHECKPOINT_KEY = (
    "runs/g0-e1-stage1-seed2026-v1/checkpoints/global_step_2000/"
    "actor/model_state_dict/full_weights.pt"
)
CHECKPOINT = {
    "sha256": "4f80c4a68a9e1118b1750fb11b9092d5592d3082160b983329b2f12bd067a146",
    "size_bytes": 10015912662,
    "step": 2000,
    "version_id": "LvdNrl8pPsbD6s9tdJ8.__.1V2B00077",
}
AWS_ENVIRONMENT = (
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
    "AWS_CREDENTIAL_EXPIRATION",
)
MINIMUM_CREDENTIAL_TTL_SECONDS = 1800
MAXIMUM_STAGE_COST_USD = "1.000000"


def _validate_injected_aws_credentials() -> None:
    missing = [name for name in AWS_ENVIRONMENT if not os.environ.get(name)]
    if missing:
        raise RuntimeError("named staging secret is missing required AWS credentials")
    try:
        expiration = datetime.fromisoformat(
            os.environ["AWS_CREDENTIAL_EXPIRATION"].replace("Z", "+00:00")
        )
    except ValueError as error:
        raise RuntimeError("AWS credential expiration must be ISO-8601") from error
    remaining = (expiration - datetime.now(timezone.utc)).total_seconds()
    if remaining < MINIMUM_CREDENTIAL_TTL_SECONDS:
        raise RuntimeError("AWS credentials do not have the required 30-minute TTL")


app = modal.App(APP_NAME, tags={"project": "enpire", "phase": "g0-e1-stage-v4"})
workspace = modal.Volume.from_name("enpire-workspace", create_if_missing=False)
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "boto3==1.40.45",
        "modal==1.5.4",
    )
    .add_local_file(
        "e1_staged_checkpoint_runtime.py",
        "/root/e1_staged_checkpoint_runtime.py",
        copy=True,
    )
)


@app.function(
    image=image,
    cpu=2,
    memory=4096,
    timeout=1800,
    retries=0,
    single_use_containers=True,
    secrets=[modal.Secret.from_name(STAGE_SECRET_NAME, required_keys=list(AWS_ENVIRONMENT))],
    volumes={WORKSPACE: workspace},
)
def stage_checkpoint() -> dict[str, object]:
    import boto3

    if STAGE_ROOT.exists() or STAGE_RECEIPT.exists():
        raise RuntimeError("create-only checkpoint staging destination already exists")
    _validate_injected_aws_credentials()
    started = time.monotonic()
    partial = STAGED_CHECKPOINT.with_suffix(".pt.partial")
    receipt: dict[str, object] = {
        "authority": {
            "additional_checkpoint_access_authorized": False,
            "e2_authorized": False,
            "evaluation_authorized": False,
            "final_reset_access_authorized": False,
            "policy_promotion_authorized": False,
        },
        "bucket": BUCKET,
        "checkpoint": CHECKPOINT,
        "checkpoint_path": str(STAGED_CHECKPOINT),
        "key": CHECKPOINT_KEY,
        "schema_version": STAGE_SCHEMA_VERSION,
        "status": "failed_checkpoint_stage",
    }
    failure: BaseException | None = None
    try:
        partial.parent.mkdir(parents=True, exist_ok=False)
        boto3.client("s3", region_name="us-west-2").download_file(
            BUCKET,
            CHECKPOINT_KEY,
            str(partial),
            ExtraArgs={"VersionId": CHECKPOINT["version_id"]},
        )
        if partial.stat().st_size != CHECKPOINT["size_bytes"]:
            raise RuntimeError("downloaded checkpoint size mismatch")
        if sha256_file(partial) != CHECKPOINT["sha256"]:
            raise RuntimeError("downloaded checkpoint SHA-256 mismatch")
        partial.replace(STAGED_CHECKPOINT)
        receipt["status"] = STAGE_STATUS_COMPLETE
    except BaseException as error:
        failure = error
        receipt["error"] = bounded_error(error)
    finally:
        receipt["elapsed_seconds"] = time.monotonic() - started
        STAGE_RECEIPT.parent.mkdir(parents=True, exist_ok=True)
        with STAGE_RECEIPT.open("x", encoding="utf-8") as handle:
            handle.write(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
        workspace.commit()
    if failure is not None:
        raise RuntimeError("checkpoint staging failed; inspect terminal receipt") from None
    return receipt


@app.local_entrypoint()
def main(acknowledge_checkpoint_stage: bool = False):
    if not acknowledge_checkpoint_stage:
        raise RuntimeError("explicit checkpoint-staging acknowledgement is required")
    call = stage_checkpoint.spawn()
    print(
        json.dumps(
            {
                "app_name": APP_NAME,
                "function_call_id": call.object_id,
                "gpu_used": False,
                "maximum_stage_cost_usd": MAXIMUM_STAGE_COST_USD,
                "status": "checkpoint_stage_launched_detached",
            },
            indent=2,
            sort_keys=True,
        )
    )
