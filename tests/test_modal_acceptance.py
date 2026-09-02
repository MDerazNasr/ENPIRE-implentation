from __future__ import annotations

import base64
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from agent.d1_config import load_d1_config
from supervisor.canonical import canonical_json, fingerprint
from supervisor.contracts import (
    ApprovalEnvelope,
    CampaignSpec,
    EngineeringAcceptanceApproval,
)
from supervisor.d1_backend import (
    BackendStatus,
    D1ExperimentBackend,
    D1PlanBuilder,
    ExecutionMode,
    M5Authorization,
    ProcessOutcome,
)
from supervisor.modal_acceptance import (
    ModalAcceptanceError,
    ModalAcceptanceReceipt,
    ModalAcceptanceRequest,
    ModalAcceptanceTransport,
    RESULT_MARKER,
)


ROOT = Path(__file__).resolve().parents[1]


def git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


class ReceiptTransport:
    def __init__(self, receipt: ModalAcceptanceReceipt) -> None:
        self.receipt = receipt

    def run_plan(self, plan):
        ModalAcceptanceTransport._materialize(plan, self.receipt)
        return ProcessOutcome(
            return_code=self.receipt.return_code,
            started_at="2026-09-02T20:00:00Z",
            finished_at="2026-09-02T20:00:01Z",
            elapsed_seconds=1,
            stdout_hash="a" * 64,
            stderr_hash="b" * 64,
            timed_out=False,
        )


class ModalAcceptanceContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repository = self.root / "stable"
        self.repository.mkdir()
        git(self.repository, "init", "-q", "-b", "main")
        (self.repository / "agent").symlink_to(ROOT / "agent", target_is_directory=True)
        (self.repository / "envs").symlink_to(ROOT / "envs", target_is_directory=True)
        (self.repository / "scripts").symlink_to(ROOT / "scripts", target_is_directory=True)
        (self.repository / "supervisor").symlink_to(
            ROOT / "supervisor", target_is_directory=True
        )
        (self.repository / "sitecustomize.py").symlink_to(ROOT / "sitecustomize.py")
        (self.repository / "modal_d2_acceptance.py").symlink_to(
            ROOT / "modal_d2_acceptance.py"
        )
        (self.repository / "candidates").mkdir()
        config = load_d1_config(ROOT / "configs/d1/d2_paid_acceptance.yaml")
        config["scientific_values"]["online_bc_weight"] = 2.25
        (self.repository / "candidates/config_override.json").write_text(
            canonical_json(config) + "\n", encoding="utf-8"
        )
        git(self.repository, "add", ".")
        git(
            self.repository,
            "-c", "user.name=Fixture",
            "-c", "user.email=fixture@invalid.local",
            "commit", "-q", "-m", "D2 acceptance candidate",
        )
        self.candidate = git(self.repository, "rev-parse", "HEAD")
        self.workspace = self.root / "candidate-worktree"
        git(
            self.repository,
            "worktree", "add", "--detach", str(self.workspace), self.candidate,
        )
        self.campaign = CampaignSpec.from_dict(
            {
                "schema_version": 1,
                "campaign_id": "d2-modal-acceptance-test",
                "research_question": "Does the immutable Modal attachment work?",
                "baseline_commit": self.candidate,
                "rlinf_commit": "c90951a0c799a750cb5294ed10587c61cc2af8bf",
                "edit_mode": "config_only",
                "editable_paths": ["candidates/config_override.json"],
                "allowed_parameters": {
                    "scientific_values.online_bc_weight": {
                        "kind": "number", "minimum": "1", "maximum": "3.5"
                    }
                },
                "seeds": [2026],
                "reset_set_hash": "c" * 64,
                "evaluator_version": "d2-acceptance-no-evaluator-v1",
                "training_budget_steps": 1,
                "evaluation_trajectories": 1,
                "max_concurrency": 1,
                "artifact_namespace": "d2-modal-acceptance-test",
                "created_at": "2026-09-02T19:00:00Z",
                "budget": {
                    "max_trials": 1,
                    "max_wall_time_seconds": 1800,
                    "max_gpu_cost_usd": "1.5156",
                    "max_llm_cost_usd": "0.01",
                },
            }
        )
        self.plan = D1PlanBuilder(
            results_root=self.root / "results",
            python_executable=Path(sys.executable),
            environment={
                "RLINF_HOME": "/opt/RLinf",
                "MODAL_ADAPTER_ROOT": "/opt/qualia",
                "STAGE1_CHECKPOINT": "/workspace/checkpoints/stage1-step-500-actor",
                "NORM_STATS_PATH": "/opt/qualia/norm_stats.json",
                "WANDB_PROJECT": "qualia-rlt-d2-acceptance",
                "D2_WANDB_DIR": "/workspace/results/d2-wandb/test",
                "D1_SEED": "2026",
            },
        ).build(
            campaign=self.campaign,
            workspace=self.workspace,
            source_config_relative_path="candidates/config_override.json",
            trial_id="d2-modal-acceptance.s2026",
            arm_id="acceptance-config",
            parent_commit=self.candidate,
            candidate_commit=self.candidate,
            seed=2026,
            max_wall_time_seconds=1800,
            max_gpu_cost_usd="1.5156",
            mode=ExecutionMode.PAID_ACCEPTANCE,
        )
        approval = ApprovalEnvelope.from_dict(
            {
                "schema_version": 1,
                "campaign_id": self.campaign.campaign_id,
                "campaign_spec_hash": self.campaign.fingerprint(),
                "approved_by": "Fixture",
                "approved_at": "2026-09-02T19:00:00Z",
                "expires_at": "2026-09-03T19:00:00Z",
                "edit_mode": "config_only",
                "max_concurrency": 1,
                "budget": self.campaign.budget.to_dict(),
            }
        )
        self.authorization = M5Authorization.create(
            campaign=self.campaign,
            mode=ExecutionMode.PAID_ACCEPTANCE,
            authorized_at=datetime(2026, 9, 2, 20, tzinfo=timezone.utc),
            acceptance_approval=EngineeringAcceptanceApproval.from_dict(
                {
                    "schema_version": 1,
                    "campaign_approval": approval.to_dict(),
                    "profile_hash": "d" * 64,
                    "provider": "Modal",
                    "provider_profile": "fixture-profile",
                    "max_total_cost_usd": "3",
                    "promotion_allowed": False,
                }
            ),
            acknowledge_paid_run=True,
            allow_paid_acceptance=True,
        )

    def request(self) -> ModalAcceptanceRequest:
        return ModalAcceptanceRequest.create(self.plan)

    def receipt(self, request: ModalAcceptanceRequest) -> ModalAcceptanceReceipt:
        subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/m5_fixture_launcher.py"),
                "--config", self.plan.derived_config_path,
                "--results-root", self.plan.results_root,
                "--run-id", self.plan.contract.trial_id,
                "--logical-command-json", canonical_json(list(self.plan.logical_rlinf_command)),
                "--fixture-execute",
            ],
            cwd=self.workspace,
            check=True,
        )
        manifest_path = Path(self.plan.manifest_path)
        log_path = Path(self.plan.log_path)
        manifest = manifest_path.read_bytes()
        log = log_path.read_bytes()
        manifest_path.unlink()
        log_path.unlink()
        return ModalAcceptanceReceipt.from_dict(
            {
                "schema_version": 1,
                "request_hash": request.fingerprint(),
                "status": "complete",
                "return_code": 0,
                "manifest_b64": base64.b64encode(manifest).decode("ascii"),
                "manifest_sha256": hashlib.sha256(manifest).hexdigest(),
                "log_b64": base64.b64encode(log).decode("ascii"),
                "log_sha256": hashlib.sha256(log).hexdigest(),
                "artifact_inventory": [
                    {
                        "path": "remote/manifest.json",
                        "sha256": hashlib.sha256(manifest).hexdigest(),
                        "size_bytes": len(manifest),
                    },
                    {
                        "path": "remote/run.log",
                        "sha256": hashlib.sha256(log).hexdigest(),
                        "size_bytes": len(log),
                    },
                ],
                "worker": {"provider": "Modal", "app_name": "fixture"},
            }
        )

    def test_request_round_trip_binds_plan_config_and_source_bundle(self) -> None:
        request = self.request()
        self.assertEqual(
            ModalAcceptanceRequest.from_dict(request.to_dict()), request
        )
        self.assertEqual(request.plan_hash, self.plan.fingerprint())
        self.assertEqual(request.derived_config_sha256, self.plan.contract.config_hash)
        self.assertTrue(request.source_hashes)

    def test_request_rejects_tampered_config_plan_and_source_hashes(self) -> None:
        request = self.request().to_dict()
        for field in ("derived_config_b64", "plan_hash", "source_bundle_hash"):
            with self.subTest(field=field):
                tampered = copy.deepcopy(request)
                tampered[field] = (
                    base64.b64encode(b"other").decode("ascii")
                    if field == "derived_config_b64"
                    else "0" * 64
                )
                with self.assertRaises(ModalAcceptanceError):
                    ModalAcceptanceRequest.from_dict(tampered)

    def test_receipt_rejects_tampering_and_wrong_request(self) -> None:
        request = self.request()
        receipt = self.receipt(request)
        payload = base64.b64encode(
            json.dumps(receipt.to_dict()).encode("utf-8")
        ).decode("ascii")
        extracted = ModalAcceptanceTransport._extract_receipt(
            f"noise\n{RESULT_MARKER}{payload}\n".encode(), request
        )
        self.assertEqual(extracted, receipt)
        wrong = copy.deepcopy(receipt.to_dict())
        wrong["request_hash"] = "0" * 64
        wrong_payload = base64.b64encode(json.dumps(wrong).encode()).decode()
        with self.assertRaisesRegex(ModalAcceptanceError, "another request"):
            ModalAcceptanceTransport._extract_receipt(
                f"{RESULT_MARKER}{wrong_payload}\n".encode(), request
            )

    def test_plan_aware_backend_materializes_and_normalizes_receipt(self) -> None:
        request = self.request()
        receipt = self.receipt(request)
        result = D1ExperimentBackend(ReceiptTransport(receipt)).run(
            self.plan, self.authorization
        )
        self.assertEqual(result.status, BackendStatus.COMPLETE, result.to_dict())
        self.assertIsNotNone(result.evidence)
        kinds = {item.kind for item in result.evidence.artifacts}
        self.assertIn("modal-receipt", kinds)
        self.assertTrue(
            Path(self.plan.manifest_path).with_name("modal-receipt.json").is_file()
        )


if __name__ == "__main__":
    unittest.main()
