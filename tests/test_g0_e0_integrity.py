from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.build_g0_evaluator_bundle import build_bundle, verify_bundle
from scripts.export_g0_reset_sets import EXTRACTOR_ID, materialize, validate_capture
from scripts.run_g0_evaluator_isolation_rehearsal import run_rehearsal
from scripts.run_g0_readiness_gate import REQUIRED_EXTERNAL_INPUTS, build_readiness
from supervisor.evaluator_deployment import (
    EvaluatorDeploymentError,
    build_local_isolation_receipt,
    validate_production_custody_record,
    validate_production_deployment_record,
    verify_local_isolation_receipt,
)
from supervisor.canonical import fingerprint
from supervisor.evaluator_integrity import (
    EpisodeBatch,
    EvaluatorIntegrityError,
    ResetSetArtifact,
    assert_final_inputs_excluded,
    evaluate_episode_batches,
    validate_reset_pair,
)
from supervisor.g0_decision import decide_g0_candidate


INCUMBENT = "a" * 40
CANDIDATE = "b" * 40
SOURCE_HASH = "c" * 64
ENV_HASH = "d" * 64
SIM_HASH = "e" * 64
GEN_HASH = "f" * 64
SEEDS = (2026, 2027, 2028)
ROOT = Path(__file__).resolve().parents[1]


def reset_payload(role: str, seed: int, offset: int) -> dict:
    return {
        "schema_version": 1,
        "set_id": f"g0-{role}-v1",
        "role": role,
        "task_id": "peg-insertion-side",
        "simulator_hash": SIM_HASH,
        "generator_hash": GEN_HASH,
        "generator_seed": seed,
        "reset_ids": list(range(offset, offset + 256)),
    }


def batches(reset_set: ResetSetArtifact) -> list[EpisodeBatch]:
    values = []
    for condition, commit, successes in (
        ("control", INCUMBENT, (20, 22, 24)),
        ("candidate", CANDIDATE, (40, 42, 44)),
    ):
        for seed, count in zip(SEEDS, successes):
            values.append(
                EpisodeBatch.create(
                    trial_id=f"{condition}-{seed}",
                    condition=condition,
                    seed=seed,
                    candidate_commit=commit,
                    reset_set_hash=reset_set.fingerprint(),
                    reset_ids=reset_set.reset_ids,
                    success_once=[True] * count + [False] * (256 - count),
                )
            )
    return values


def evaluator_input(reset_set: ResetSetArtifact) -> dict:
    return {
        "schema_version": 1,
        "reset_set": reset_set.to_dict(),
        "expected_seeds": list(SEEDS),
        "incumbent_commit": INCUMBENT,
        "candidate_commit": CANDIDATE,
        "batches": [batch.to_dict() for batch in batches(reset_set)],
        "evaluator_version": "g0-e0-fixture-v1",
        "evaluator_source_hash": SOURCE_HASH,
        "evaluator_environment_hash": ENV_HASH,
    }


class G0E0IntegrityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.development = ResetSetArtifact.from_dict(reset_payload("development", 2026, 0))
        self.final = ResetSetArtifact.from_dict(reset_payload("final", 2027, 1000))

    def evaluate(self, values=None):
        return evaluate_episode_batches(
            reset_set=self.development,
            expected_seeds=SEEDS,
            incumbent_commit=INCUMBENT,
            candidate_commit=CANDIDATE,
            batches=values or batches(self.development),
            evaluator_version="g0-e0-fixture-v1",
            evaluator_source_hash=SOURCE_HASH,
            evaluator_environment_hash=ENV_HASH,
        )

    def test_reset_pair_is_unique_disjoint_and_hash_bound(self) -> None:
        report = validate_reset_pair(self.development, self.final)
        self.assertEqual(report["overlap_count"], 0)
        self.assertEqual(report["development_count"], 256)
        self.assertEqual(report["final_count"], 256)

    def test_duplicate_partial_and_overlapping_reset_sets_fail_closed(self) -> None:
        duplicate = reset_payload("development", 2026, 0)
        duplicate["reset_ids"][-1] = duplicate["reset_ids"][0]
        with self.assertRaises(EvaluatorIntegrityError):
            ResetSetArtifact.from_dict(duplicate)
        partial = reset_payload("development", 2026, 0)
        partial["reset_ids"].pop()
        with self.assertRaises(EvaluatorIntegrityError):
            ResetSetArtifact.from_dict(partial)
        overlap = ResetSetArtifact.from_dict(reset_payload("final", 2027, 255))
        with self.assertRaises(EvaluatorIntegrityError):
            validate_reset_pair(self.development, overlap)

    def test_replay_is_byte_stable_and_agent_prose_is_not_an_input(self) -> None:
        first = self.evaluate()
        second = self.evaluate()
        self.assertEqual(first, second)
        self.assertEqual(first["payload"]["decision"], "keep")
        self.assertNotIn("agent", str(first).lower())

    def test_g0_rule_keeps_reverts_and_preserves_uncertainty(self) -> None:
        keep = decide_g0_candidate([0.10, 0.20, 0.30], [0.20, 0.30, 0.40])
        self.assertEqual(keep.decision, "keep")
        revert = decide_g0_candidate([0.40, 0.50, 0.60], [0.30, 0.40, 0.50])
        self.assertEqual(revert.decision, "revert")
        uncertain = decide_g0_candidate([0.40, 0.50, 0.60], [0.44, 0.54, 0.64])
        self.assertEqual(uncertain.decision, "inconclusive")
        noisy = decide_g0_candidate([0.30, 0.50, 0.70], [0.40, 0.49, 0.81])
        self.assertEqual(noisy.decision, "inconclusive")

    def test_g0_rule_ceiling_has_no_secondary_metric_escape_hatch(self) -> None:
        result = decide_g0_candidate([0.95, 0.96, 0.97], [0.96, 0.97, 0.98])
        self.assertEqual(result.decision, "inconclusive")

    def test_missing_or_duplicate_seed_batch_fails_closed(self) -> None:
        values = batches(self.development)
        with self.assertRaises(EvaluatorIntegrityError):
            self.evaluate(values[:-1])
        with self.assertRaises(EvaluatorIntegrityError):
            self.evaluate(values + [values[0]])

    def test_reset_substitution_reordering_and_commit_drift_fail_closed(self) -> None:
        values = batches(self.development)
        raw = values[0].to_dict()
        raw["reset_ids"] = list(reversed(raw["reset_ids"]))
        changed = EpisodeBatch.create(**raw)
        with self.assertRaises(EvaluatorIntegrityError):
            self.evaluate([changed, *values[1:]])
        raw = values[0].to_dict()
        raw["candidate_commit"] = CANDIDATE
        changed = EpisodeBatch.create(**raw)
        with self.assertRaises(EvaluatorIntegrityError):
            self.evaluate([changed, *values[1:]])

    def test_non_boolean_and_mismatched_trajectory_evidence_fails_closed(self) -> None:
        kwargs = {
            "trial_id": "bad-batch",
            "condition": "control",
            "seed": 2026,
            "candidate_commit": INCUMBENT,
            "reset_set_hash": self.development.fingerprint(),
            "reset_ids": self.development.reset_ids,
        }
        with self.assertRaises(EvaluatorIntegrityError):
            EpisodeBatch.create(**kwargs, success_once=[1] * 256)
        with self.assertRaises(EvaluatorIntegrityError):
            EpisodeBatch.create(**kwargs, success_once=[True] * 255)

    def test_final_evaluator_material_is_rejected_from_agent_context(self) -> None:
        assert_final_inputs_excluded({"metrics": {"success_rate": "development only"}})
        for key in ("final_reset_ids", "final_trajectories", "evaluator_source"):
            with self.assertRaises(EvaluatorIntegrityError):
                assert_final_inputs_excluded({"nested": {key: [1, 2, 3]}})

    def test_documented_preflight_command_is_directly_executable_and_non_authorizing(self) -> None:
        completed = subprocess.run(
            [sys.executable, "scripts/run_g0_e0_integrity_preflight.py"],
            cwd=ROOT,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        payload = json.loads(completed.stdout)["payload"]
        self.assertEqual(
            payload["reset_artifacts"]["status"],
            "runtime_confirmed_final_custody_pending",
        )
        self.assertTrue(payload["reset_artifacts"]["simulator_runtime_reset_confirmed"])
        self.assertEqual(
            payload["evaluator_isolation"]["status"], "pass_local_isolation_rehearsal"
        )
        self.assertFalse(payload["evaluator_isolation"]["production_custody_accepted"])
        self.assertFalse(payload["evaluator_isolation"]["production_deployment_accepted"])
        self.assertFalse(
            payload["runtime_cost_candidates"]["canonical_runtime_identity_accepted"]
        )
        self.assertFalse(
            payload["runtime_cost_candidates"]["canonical_cost_retention_accepted"]
        )
        for field in (
            "evaluation_executed",
            "promotion_executed",
            "gpu_execution_authorized",
            "paid_execution_authorized",
            "provider_call_authorized",
            "model_egress_authorized",
            "campaign_activation_authorized",
        ):
            self.assertFalse(payload[field])

    def test_g0_readiness_gate_lists_every_external_blocker_and_grants_no_authority(self) -> None:
        result = build_readiness(ROOT)
        payload = result["payload"]
        self.assertEqual(payload["status"], "blocked_missing_external_inputs")
        resolved = {
            "development_reset_artifact", "repeat_export_receipt"
        }
        self.assertEqual(
            set(payload["missing_external_inputs"]), set(REQUIRED_EXTERNAL_INPUTS) - resolved
        )
        self.assertFalse(payload["ready_transition_implemented"])
        for field in (
            "scientific_evaluation_authorized", "campaign_activation_authorized",
            "gpu_execution_authorized", "paid_execution_authorized",
            "provider_call_authorized", "model_egress_authorized", "promotion_authorized",
        ):
            self.assertFalse(payload[field])

    def test_g0_readiness_cli_is_direct_and_output_is_create_only(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix="enpire-g0-readiness-test-"))
        try:
            output = temporary / "readiness.json"
            command = [sys.executable, "scripts/run_g0_readiness_gate.py", "--output", str(output)]
            completed = subprocess.run(
                command, cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            self.assertEqual(json.loads(completed.stdout), json.loads(output.read_text(encoding="utf-8")))
            repeated = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertNotEqual(repeated.returncode, 0)
            self.assertIn("output already exists", repeated.stderr)
        finally:
            shutil.rmtree(temporary)

    def test_bundle_is_external_read_only_manifested_and_replay_stable(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix="enpire-g0-bundle-test-"))
        bundle = temporary / "bundle"
        try:
            manifest = build_bundle(bundle, ROOT)
            self.assertEqual(verify_bundle(bundle), manifest)
            self.assertFalse(os.stat(bundle / "run_evaluator.py").st_mode & 0o222)
            self.assertFalse(os.stat(bundle).st_mode & 0o222)
            input_path = temporary / "input.json"
            input_path.write_text(json.dumps(evaluator_input(self.development)), encoding="utf-8")
            command = [sys.executable, str(bundle / "run_evaluator.py"), "--input", str(input_path)]
            first = subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True).stdout
            second = subprocess.run(command, check=True, stdout=subprocess.PIPE, text=True).stdout
            self.assertEqual(first, second)
            self.assertEqual(json.loads(first)["payload"]["decision"], "keep")
        finally:
            if bundle.exists():
                for path in bundle.rglob("*"):
                    if path.is_dir():
                        path.chmod(0o755)
                bundle.chmod(0o755)
            shutil.rmtree(temporary)

    def test_bundle_rejects_in_repo_destination_and_detects_tampering(self) -> None:
        with self.assertRaises(ValueError):
            build_bundle(ROOT / "should-not-exist", ROOT)
        temporary = Path(tempfile.mkdtemp(prefix="enpire-g0-bundle-tamper-"))
        bundle = temporary / "bundle"
        try:
            build_bundle(bundle, ROOT)
            target = bundle / "run_evaluator.py"
            target.chmod(0o644)
            target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                verify_bundle(bundle)
        finally:
            if bundle.exists():
                for path in bundle.rglob("*"):
                    if path.is_dir():
                        path.chmod(0o755)
                bundle.chmod(0o755)
            shutil.rmtree(temporary)

    def test_local_isolation_rehearsal_is_hash_bound_and_non_authorizing(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix="enpire-g0-isolation-test-"))
        private = temporary / "private"
        final_path = private / "final.json"
        bundle = temporary / "bundle"
        ledger = temporary / "ledger"
        anchor = temporary / "anchor"
        try:
            private.mkdir(mode=0o700)
            final_path.write_text(json.dumps(self.final.to_dict()), encoding="utf-8")
            final_path.chmod(0o400)
            private.chmod(0o500)
            receipt = run_rehearsal(
                private_final=final_path,
                bundle_output=bundle,
                ledger_root=ledger,
                anchor_root=anchor,
                repository=ROOT,
            )
            self.assertEqual(
                verify_local_isolation_receipt(receipt, self.final.fingerprint()), receipt
            )
            payload = receipt["payload"]
            self.assertFalse(payload["production_custody_accepted"])
            self.assertFalse(payload["production_deployment_accepted"])
            self.assertFalse(payload["storage_separation"]["independent_os_principal"])
            self.assertNotIn("reset_ids", json.dumps(receipt))
            self.assertNotIn(str(final_path), json.dumps(receipt))
        finally:
            if private.exists():
                private.chmod(0o700)
            if bundle.exists():
                for path in bundle.rglob("*"):
                    if path.is_dir():
                        path.chmod(0o755)
                bundle.chmod(0o755)
            shutil.rmtree(temporary)

    def test_local_isolation_rejects_permissive_private_artifact(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix="enpire-g0-custody-mode-test-"))
        private = temporary / "private"
        final_path = private / "final.json"
        bundle = temporary / "bundle"
        ledger = temporary / "ledger"
        anchor = temporary / "anchor"
        try:
            private.mkdir(mode=0o700)
            final_path.write_text(json.dumps(self.final.to_dict()), encoding="utf-8")
            final_path.chmod(0o644)
            ledger.mkdir()
            anchor.mkdir()
            manifest = build_bundle(bundle, ROOT)
            with self.assertRaises(EvaluatorDeploymentError):
                build_local_isolation_receipt(
                    repository=ROOT,
                    private_final=final_path,
                    bundle_root=bundle,
                    bundle_manifest=manifest,
                    ledger_root=ledger,
                    anchor_root=anchor,
                )
        finally:
            if bundle.exists():
                for path in bundle.rglob("*"):
                    if path.is_dir():
                        path.chmod(0o755)
                bundle.chmod(0o755)
            shutil.rmtree(temporary)

    def test_local_isolation_receipt_tampering_fails_closed(self) -> None:
        receipt = {
            "payload": {
                "status": "pass_local_isolation_rehearsal",
                "claim_boundary": "same-user-mode-bits-only-not-production-custody",
                "final_reset_artifact": {
                    "artifact_sha256": self.final.fingerprint(),
                    "ordered_ids_emitted": False,
                },
                "evaluation_executed": False,
                "scientific_evaluation_authorized": False,
                "campaign_activation_authorized": False,
                "gpu_execution_authorized": False,
                "paid_execution_authorized": False,
                "provider_call_authorized": False,
                "model_egress_authorized": False,
                "promotion_authorized": False,
                "production_custody_accepted": False,
                "production_deployment_accepted": False,
            },
        }
        receipt["sha256"] = fingerprint(receipt["payload"])
        verify_local_isolation_receipt(receipt, self.final.fingerprint())
        receipt["payload"]["production_custody_accepted"] = True
        with self.assertRaises(EvaluatorDeploymentError):
            verify_local_isolation_receipt(receipt, self.final.fingerprint())

    def test_production_custody_and_deployment_schemas_fail_closed(self) -> None:
        custody_payload = {
            "schema_version": 1,
            "record_kind": "g0-final-reset-custody",
            "custody_class": "production-independent",
            "artifact_sha256": self.final.fingerprint(),
            "artifact_count": 256,
            "custodian_principal": "evaluator-operator",
            "storage_identity_sha256": "1" * 64,
            "independent_os_principal": True,
            "independent_failure_domain": True,
            "immutable_or_evaluator_only_storage": True,
            "candidate_access": False,
            "proposer_access": False,
            "worker_access": False,
            "ordered_ids_emitted": False,
            "independent_verifier": "protocol-reviewer",
            "verification_timestamp_utc": "2026-09-11T00:00:00Z",
            "evaluation_authorized": False,
            "gpu_execution_authorized": False,
            "promotion_authorized": False,
        }
        custody = {"payload": custody_payload, "sha256": fingerprint(custody_payload)}
        self.assertEqual(
            validate_production_custody_record(custody, self.final.fingerprint()), custody
        )
        deployment_payload = {
            "schema_version": 1,
            "record_kind": "g0-production-evaluator",
            "deployment_class": "production-independent",
            "bundle_manifest_sha256": "2" * 64,
            "environment_identity_sha256": "3" * 64,
            "custody_record_sha256": custody["sha256"],
            "evaluator_principal": "evaluator-operator",
            "source_read_only": True,
            "final_input_read_only": True,
            "candidate_can_modify_evaluator": False,
            "candidate_can_read_final_inputs": False,
            "ledger_identity_sha256": "4" * 64,
            "anchor_identity_sha256": "5" * 64,
            "ledger_anchor_independent_failure_domains": True,
            "independent_verifier": "protocol-reviewer",
            "verification_timestamp_utc": "2026-09-11T00:00:00Z",
            "evaluation_authorized": False,
            "gpu_execution_authorized": False,
            "promotion_authorized": False,
        }
        deployment = {
            "payload": deployment_payload,
            "sha256": fingerprint(deployment_payload),
        }
        self.assertEqual(
            validate_production_deployment_record(
                deployment,
                expected_bundle_sha256="2" * 64,
                expected_custody_record_sha256=custody["sha256"],
            ),
            deployment,
        )
        bad_custody = json.loads(json.dumps(custody))
        bad_custody["payload"]["candidate_access"] = True
        bad_custody["sha256"] = fingerprint(bad_custody["payload"])
        with self.assertRaises(EvaluatorDeploymentError):
            validate_production_custody_record(bad_custody, self.final.fingerprint())
        bad_deployment = json.loads(json.dumps(deployment))
        bad_deployment["payload"]["anchor_identity_sha256"] = "4" * 64
        bad_deployment["sha256"] = fingerprint(bad_deployment["payload"])
        with self.assertRaises(EvaluatorDeploymentError):
            validate_production_deployment_record(
                bad_deployment,
                expected_bundle_sha256="2" * 64,
                expected_custody_record_sha256=custody["sha256"],
            )

    def test_ledger_anchor_detects_edit_truncation_and_missing_anchor(self) -> None:
        temporary = Path(tempfile.mkdtemp(prefix="enpire-g0-ledger-test-"))
        bundle = temporary / "bundle"
        try:
            build_bundle(bundle, ROOT)
            input_path = temporary / "input.json"
            ledger = temporary / "evaluation.jsonl"
            anchor = temporary / "anchor.json"
            input_path.write_text(json.dumps(evaluator_input(self.development)), encoding="utf-8")
            command = [
                sys.executable, str(bundle / "run_evaluator.py"), "--input", str(input_path),
                "--ledger", str(ledger), "--anchor", str(anchor),
            ]
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            subprocess.run(command, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(len(ledger.read_text(encoding="utf-8").splitlines()), 2)
            trusted_anchor = anchor.read_text(encoding="utf-8")
            anchor.unlink()
            failed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("presence mismatch", failed.stderr)
            anchor.write_text(trusted_anchor, encoding="utf-8")
            records = ledger.read_text(encoding="utf-8").splitlines()
            first_record = json.loads(records[0])
            first_record["result"]["payload"]["decision"] = "revert"
            records[0] = json.dumps(first_record, sort_keys=True, separators=(",", ":"))
            ledger.write_text("\n".join(records) + "\n", encoding="utf-8")
            failed = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertNotEqual(failed.returncode, 0)
            self.assertIn("chain is invalid", failed.stderr)
        finally:
            if bundle.exists():
                for path in bundle.rglob("*"):
                    if path.is_dir():
                        path.chmod(0o755)
                bundle.chmod(0o755)
            shutil.rmtree(temporary)

    def test_reset_capture_is_fail_closed_and_materializes_without_evaluation(self) -> None:
        capture = {
            "schema_version": 1,
            "extractor_id": EXTRACTOR_ID,
            "rlinf_commit": INCUMBENT,
            "maniskill_commit": CANDIDATE,
            "numpy_version": "1.26.4",
            "source_hashes": {
                "rlinf_environment": "1" * 64,
                "rlinf_config": "2" * 64,
                "rlinf_task_variant": "3" * 64,
                "maniskill_base_env": "4" * 64,
                "maniskill_task": "5" * 64,
                "project_multiprocess_adapter": "6" * 64,
            },
            "development": self.development.to_dict(),
            "final": self.final.to_dict(),
        }
        _, _, receipt = validate_capture(capture, INCUMBENT, CANDIDATE)
        self.assertFalse(receipt["payload"]["evaluation_executed"])
        wrong = dict(capture)
        wrong["rlinf_commit"] = CANDIDATE
        with self.assertRaises(ValueError):
            validate_capture(wrong, INCUMBENT, CANDIDATE)
        temporary = Path(tempfile.mkdtemp(prefix="enpire-g0-reset-test-"))
        try:
            source = temporary / "capture.json"
            output = temporary / "artifacts"
            final_output = temporary / "private" / "final.json"
            source.write_text(json.dumps(capture), encoding="utf-8")
            created = materialize(source, output, final_output, INCUMBENT, CANDIDATE)
            self.assertEqual(created, receipt)
            self.assertEqual(
                ResetSetArtifact.from_dict(json.loads((output / "development.json").read_text())),
                self.development,
            )
            with self.assertRaises(ValueError):
                materialize(source, output, final_output, INCUMBENT, CANDIDATE)
        finally:
            shutil.rmtree(temporary)


if __name__ == "__main__":
    unittest.main()
