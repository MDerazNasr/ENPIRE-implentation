#!/usr/bin/env python3
"""Offline security checks for the non-authorizing G0 AWS templates."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.canonical import fingerprint


class G0AwsInfrastructureError(ValueError):
    """Raised when an infrastructure template weakens the custody boundary."""


TEMPLATES = {
    "audit": "infra/aws-g0/audit-account.template.json",
    "evaluator": "infra/aws-g0/evaluator-account.template.json",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or value.get("AWSTemplateFormatVersion") != "2010-09-09":
        raise G0AwsInfrastructureError(f"invalid CloudFormation template: {path}")
    return value


def _actions(role: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for policy in role.get("Properties", {}).get("Policies", []):
        for statement in policy.get("PolicyDocument", {}).get("Statement", []):
            actions = statement.get("Action", [])
            result.update([actions] if isinstance(actions, str) else actions)
    return result


def _assert_locked_bucket(resource: dict[str, Any], name: str) -> None:
    if resource.get("Type") != "AWS::S3::Bucket":
        raise G0AwsInfrastructureError(f"{name} is not an S3 bucket")
    if resource.get("DeletionPolicy") != "Retain" or resource.get("UpdateReplacePolicy") != "Retain":
        raise G0AwsInfrastructureError(f"{name} is not retained on stack changes")
    properties = resource.get("Properties", {})
    if properties.get("ObjectLockEnabled") is not True:
        raise G0AwsInfrastructureError(f"{name} does not enable Object Lock")
    lock = properties.get("ObjectLockConfiguration", {})
    retention = lock.get("Rule", {}).get("DefaultRetention", {})
    if lock.get("ObjectLockEnabled") != "Enabled" or retention != {
        "Mode": "COMPLIANCE", "Days": {"Ref": "RetentionDays"}
    }:
        raise G0AwsInfrastructureError(f"{name} does not enforce parameterized compliance retention")
    if properties.get("VersioningConfiguration") != {"Status": "Enabled"}:
        raise G0AwsInfrastructureError(f"{name} does not enable versioning")
    public = properties.get("PublicAccessBlockConfiguration", {})
    if set(public) != {
        "BlockPublicAcls", "BlockPublicPolicy", "IgnorePublicAcls", "RestrictPublicBuckets"
    } or set(public.values()) != {True}:
        raise G0AwsInfrastructureError(f"{name} does not block all public access")
    encryption = properties.get("BucketEncryption", {}).get(
        "ServerSideEncryptionConfiguration", []
    )
    if encryption != [{"ServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"}}]:
        raise G0AwsInfrastructureError(f"{name} does not enforce encryption at rest")


def check_templates(root: Path = ROOT) -> dict[str, Any]:
    audit_path = root / TEMPLATES["audit"]
    evaluator_path = root / TEMPLATES["evaluator"]
    audit = _load(audit_path)
    evaluator = _load(evaluator_path)
    for template, label in ((audit, "audit"), (evaluator, "evaluator")):
        retention = template.get("Parameters", {}).get("RetentionDays", {})
        if retention.get("MinValue") != 30 or retention.get("Default") != 30:
            raise G0AwsInfrastructureError(f"{label} retention parameter is unsafe")
    for name in ("AnchorBucket", "AuditLogBucket"):
        _assert_locked_bucket(audit["Resources"].get(name, {}), name)
    for name in ("FinalInputBucket", "EvidenceBucket", "LedgerBucket"):
        _assert_locked_bucket(evaluator["Resources"].get(name, {}), name)

    roles = {
        name: resource for name, resource in {**audit["Resources"], **evaluator["Resources"]}.items()
        if resource.get("Type") == "AWS::IAM::Role"
    }
    forbidden = {
        "s3:DeleteObject", "s3:DeleteObjectVersion", "s3:DeleteBucket",
        "s3:PutBucketPolicy", "s3:PutBucketObjectLockConfiguration", "s3:*",
    }
    for name, role in roles.items():
        overlap = _actions(role) & forbidden
        if overlap:
            raise G0AwsInfrastructureError(f"{name} grants forbidden actions: {sorted(overlap)}")
    anchor_trust = roles["AnchorWriterRole"]["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    expected_anchor_trust = [{
        "Effect": "Allow",
        "Principal": {
            "AWS": {"Fn::Sub": "arn:${AWS::Partition}:iam::${EvaluatorAccountId}:root"}
        },
        "Action": "sts:AssumeRole",
        "Condition": {
            "ArnEquals": {
                "aws:PrincipalArn": {
                    "Fn::Sub": (
                        "arn:${AWS::Partition}:iam::${EvaluatorAccountId}:"
                        "role/${EvaluatorRoleName}"
                    )
                }
            }
        },
    }]
    if anchor_trust != expected_anchor_trust:
        raise G0AwsInfrastructureError(
            "anchor writer trust must use the evaluator account root constrained "
            "to the exact evaluator role ARN"
        )
    worker_actions = _actions(roles["WorkerUploadRole"])
    if "s3:GetObject" in worker_actions or "s3:GetObjectVersion" in worker_actions:
        raise G0AwsInfrastructureError("worker can read evidence or final inputs")
    worker_policy = json.dumps(roles["WorkerUploadRole"], sort_keys=True)
    if "FinalInputBucket" in worker_policy or "LedgerBucket" in worker_policy:
        raise G0AwsInfrastructureError("worker role crosses the evaluator boundary")
    verifier_policy = json.dumps(roles["ReceiptVerifierRole"], sort_keys=True)
    if "${FinalInputBucket.Arn}/" in verifier_policy:
        raise G0AwsInfrastructureError("receipt verifier can read final inputs")
    trail = evaluator["Resources"].get("EvaluatorTrail", {}).get("Properties", {})
    if trail.get("EnableLogFileValidation") is not True or trail.get("IsMultiRegionTrail") is not True:
        raise G0AwsInfrastructureError("evaluator CloudTrail integrity is incomplete")
    if trail.get("S3BucketName") != {"Ref": "AuditLogBucketName"}:
        raise G0AwsInfrastructureError("evaluator trail is not cross-account parameterized")

    payload = {
        "schema_version": 1,
        "status": "pass_offline_non_authorizing_template_check",
        "templates": {name: {"path": relative, "sha256": _sha256(root / relative)} for name, relative in TEMPLATES.items()},
        "locked_bucket_count": 5,
        "minimum_retention_days": 30,
        "worker_final_input_access": False,
        "worker_delete_access": False,
        "receipt_verifier_final_input_read_access": False,
        "cross_account_audit_parameterized": True,
        "cloud_resources_created": False,
        "object_lock_activated": False,
        "private_artifact_uploaded": False,
        "scientific_execution_authorized": False,
        "campaign_activation_authorized": False,
        "gpu_execution_authorized": False,
        "paid_execution_authorized": False,
        "provider_call_authorized": False,
        "model_egress_authorized": False,
        "promotion_authorized": False,
    }
    return {"payload": payload, "sha256": fingerprint(payload)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = check_templates()
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        if args.output.exists():
            parser.error("output already exists")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
