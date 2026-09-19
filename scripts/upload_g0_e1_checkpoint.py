#!/usr/bin/env python3
"""Create-only uploader for one retained G0 E1 checkpoint directory."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


CHECKPOINT_STEPS = {250, 500, 1000, 2000}
DEFAULT_MAX_TOTAL_BYTES = 350 * 1024**3


class UploadError(RuntimeError):
    """Raised when a checkpoint upload cannot proceed safely."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def inventory(checkpoint_dir: Path) -> tuple[list[dict[str, object]], int]:
    root = checkpoint_dir.resolve(strict=True)
    if not root.is_dir():
        raise UploadError("checkpoint path must be a directory")
    files: list[dict[str, object]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise UploadError(f"checkpoint symlinks are forbidden: {path}")
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        size = path.stat().st_size
        total += size
        files.append({"path": relative, "sha256": _sha256(path), "size_bytes": size})
    if not files:
        raise UploadError("checkpoint directory is empty")
    return files, total


def validate_prefix(prefix: str) -> str:
    path = PurePosixPath(prefix)
    if (
        not prefix.startswith("runs/")
        or not prefix.endswith("/")
        or path.is_absolute()
        or ".." in path.parts
    ):
        raise UploadError("prefix must be a safe runs/.../ prefix ending in '/'")
    return prefix


def _aws_json(profile: str, *arguments: str) -> dict:
    process = subprocess.run(
        ["aws", *arguments, "--profile", profile, "--region", "us-west-2"],
        check=False,
        capture_output=True,
        text=True,
    )
    if process.returncode:
        raise UploadError(process.stderr.strip() or "AWS command failed")
    try:
        return json.loads(process.stdout)
    except json.JSONDecodeError as error:
        raise UploadError("AWS command returned invalid JSON") from error


def list_prefix(bucket: str, prefix: str, profile: str) -> list[dict]:
    value = _aws_json(
        profile,
        "s3api",
        "list-objects-v2",
        "--bucket",
        bucket,
        "--prefix",
        prefix,
    )
    if value.get("IsTruncated"):
        raise UploadError("prefix listing was truncated")
    return list(value.get("Contents", []))


def upload_file(path: Path, bucket: str, key: str, profile: str) -> None:
    process = subprocess.run(
        [
            "aws",
            "s3",
            "cp",
            str(path),
            f"s3://{bucket}/{key}",
            "--only-show-errors",
            "--checksum-algorithm",
            "SHA256",
            "--profile",
            profile,
            "--region",
            "us-west-2",
        ],
        check=False,
    )
    if process.returncode:
        raise UploadError(f"upload failed for {key}")


def build_plan(
    checkpoint_dir: Path,
    *,
    step: int,
    bucket: str,
    campaign_prefix: str,
    profile: str,
    max_total_bytes: int,
) -> dict:
    if step not in CHECKPOINT_STEPS:
        raise UploadError("step must be one of 250, 500, 1000, or 2000")
    campaign_prefix = validate_prefix(campaign_prefix)
    step_prefix = f"{campaign_prefix}checkpoints/global_step_{step}/"
    if list_prefix(bucket, step_prefix, profile):
        raise UploadError("checkpoint prefix is not empty; partial-prefix reuse is forbidden")
    existing = list_prefix(bucket, campaign_prefix, profile)
    existing_bytes = sum(int(item["Size"]) for item in existing)
    files, checkpoint_bytes = inventory(checkpoint_dir)
    if existing_bytes + checkpoint_bytes > max_total_bytes:
        raise UploadError("campaign upload would exceed the frozen byte cap")
    return {
        "schema_version": 1,
        "step": step,
        "bucket": bucket,
        "campaign_prefix": campaign_prefix,
        "step_prefix": step_prefix,
        "checkpoint_path": str(checkpoint_dir.resolve()),
        "checkpoint_bytes": checkpoint_bytes,
        "existing_campaign_bytes": existing_bytes,
        "maximum_campaign_bytes": max_total_bytes,
        "files": files,
        "authority": {
            "evaluation_authorized": False,
            "promotion_authorized": False,
        },
    }


def execute_plan(plan: dict, manifest_out: Path, profile: str) -> dict:
    root = Path(plan["checkpoint_path"])
    for item in plan["files"]:
        upload_file(
            root / str(item["path"]),
            str(plan["bucket"]),
            str(plan["step_prefix"]) + str(item["path"]),
            profile,
        )
    completed = dict(plan)
    completed["uploaded_at"] = datetime.now(timezone.utc).isoformat().replace(
        "+00:00", "Z"
    )
    completed["status"] = "uploaded_manifest_last"
    manifest_out.parent.mkdir(parents=True, exist_ok=True)
    manifest_out.write_text(
        json.dumps(completed, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    upload_file(
        manifest_out,
        str(plan["bucket"]),
        str(plan["step_prefix"]) + "checkpoint-manifest.json",
        profile,
    )
    observed = list_prefix(str(plan["bucket"]), str(plan["step_prefix"]), profile)
    expected_count = len(plan["files"]) + 1
    if len(observed) != expected_count:
        raise UploadError("uploaded object count does not match the manifest")
    return completed


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkpoint-dir", type=Path, required=True)
    parser.add_argument("--step", type=int, required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--campaign-prefix", required=True)
    parser.add_argument("--profile", default="enpire-e1-worker-upload")
    parser.add_argument("--manifest-out", type=Path, required=True)
    parser.add_argument("--max-total-bytes", type=int, default=DEFAULT_MAX_TOTAL_BYTES)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-retained-upload", action="store_true")
    args = parser.parse_args(argv)
    if args.acknowledge_retained_upload and not args.execute:
        parser.error("--acknowledge-retained-upload requires --execute")
    if args.execute and not args.acknowledge_retained_upload:
        parser.error("--execute requires --acknowledge-retained-upload")
    plan = build_plan(
        args.checkpoint_dir,
        step=args.step,
        bucket=args.bucket,
        campaign_prefix=args.campaign_prefix,
        profile=args.profile,
        max_total_bytes=args.max_total_bytes,
    )
    if args.execute:
        plan = execute_plan(plan, args.manifest_out, args.profile)
    print(json.dumps(plan, indent=2, sort_keys=True))
    if not args.execute:
        print("DRY RUN ONLY: no checkpoint bytes uploaded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
