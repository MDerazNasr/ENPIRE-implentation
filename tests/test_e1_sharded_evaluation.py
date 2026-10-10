import copy
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from supervisor.e1_sharded_evaluation import (
    E1ShardError,
    aggregate_shard_receipts,
    evaluator_contract_sha256,
    parse_final_eval_metrics,
    shard_spec,
)
from e1_staged_checkpoint_runtime import (
    E1CheckpointStageError,
    load_valid_stage_receipt,
    sha256_file,
)


ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs/d1/e1_checkpoint_evaluation_shard.yaml"
LAUNCHER = ROOT / "modal_e1_l40s_sharded.py"
STAGER = ROOT / "modal_e1_checkpoint_stage_v3.py"
V9_LAUNCHER = ROOT / "modal_e1_l40s_sharded_v9.py"
STAGE_WRAPPER = ROOT / "scripts/launch_g0_e1_checkpoint_stage_v3.py"
RUNNER = ROOT / "scripts/run_g0_e1_checkpoint_evaluation.py"
APPROVAL = (
    ROOT
    / "results/agent-supervisor/g0/"
    "e1-modal-l40s-step-2000-v6-sharded-approval-v1.json"
)
INTERRUPTION = (
    ROOT
    / "results/agent-supervisor/g0/"
    "e1-modal-l40s-step-2000-v6-interrupted-v1.json"
)


def metric_line(successes: int, trajectories: int = 64, episode_len: float = 300.0) -> str:
    rate = successes / trajectories
    return (
        "[INFO RLinf] {'eval/reward': array(0.005, dtype=float32), "
        f"'eval/success_once': array({rate}, dtype=float32), "
        f"'eval/episode_len': array({episode_len}, dtype=float32), "
        f"'eval/return': array({rate}, dtype=float32), "
        f"'eval/num_trajectories': {trajectories}}}"
    )


def receipt(index: int, successes: int) -> dict:
    return {
        "authority": {
            "additional_shard_authorized": False,
            "checkpoint_retry_authorized": False,
            "e2_authorized": False,
            "policy_promotion_authorized": False,
        },
        "checkpoint": {
            "sha256": "a" * 64,
            "step": 2000,
            "version_id": "version-2000",
        },
        "evaluator_source_sha256": "b" * 64,
        "metric": parse_final_eval_metrics(metric_line(successes)),
        "reset_set_sha256": "c" * 64,
        "shard": shard_spec(index).to_dict(),
        "status": "complete_valid_development_shard",
    }


class E1ShardedEvaluationTests(unittest.TestCase):
    def test_staged_checkpoint_receipt_rehashes_exact_bytes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            checkpoint = root / "full_weights.pt"
            checkpoint.write_bytes(b"verified-checkpoint")
            expected = {
                "sha256": sha256_file(checkpoint),
                "size_bytes": checkpoint.stat().st_size,
                "step": 2000,
                "version_id": "fixed-version",
            }
            receipt_path = root / "receipt.json"
            valid = {
                "authority": {"evaluation_authorized": False},
                "checkpoint": expected,
                "checkpoint_path": str(checkpoint),
                "schema_version": 1,
                "status": "complete_valid_checkpoint_stage",
            }
            receipt_path.write_text(json.dumps(valid), encoding="utf-8")
            self.assertEqual(
                load_valid_stage_receipt(
                    receipt_path,
                    checkpoint,
                    expected_checkpoint=expected,
                ),
                valid,
            )
            for mutate in ("status", "authority", "checkpoint", "bytes"):
                candidate = copy.deepcopy(valid)
                checkpoint.write_bytes(b"verified-checkpoint")
                if mutate == "status":
                    candidate["status"] = "failed_checkpoint_stage"
                elif mutate == "authority":
                    candidate["authority"]["evaluation_authorized"] = True
                elif mutate == "checkpoint":
                    candidate["checkpoint"]["version_id"] = "drift"
                else:
                    checkpoint.write_bytes(b"tampered-checkpoint")
                receipt_path.write_text(json.dumps(candidate), encoding="utf-8")
                with self.subTest(mutate=mutate):
                    with self.assertRaises(E1CheckpointStageError):
                        load_valid_stage_receipt(
                            receipt_path,
                            checkpoint,
                            expected_checkpoint=expected,
                        )

    def test_v9_staging_and_evaluation_are_separated_and_fail_closed(self) -> None:
        stager = STAGER.read_text(encoding="utf-8")
        evaluator = V9_LAUNCHER.read_text(encoding="utf-8")
        wrapper = STAGE_WRAPPER.read_text(encoding="utf-8")
        self.assertIn("MINIMUM_CREDENTIAL_TTL_SECONDS = 3300", stager)
        self.assertIn('MAXIMUM_STAGE_COST_USD = "1.000000"', stager)
        self.assertIn("failed_checkpoint_stage", stager)
        self.assertIn("retries=0", stager)
        self.assertIn("single_use_containers=True", stager)
        self.assertIn('"/root/e1_staged_checkpoint_runtime.py"', stager)
        self.assertNotIn("from supervisor", stager)
        self.assertNotIn("gpu=", stager)
        self.assertIn('ALLOWED_SHARDS = (1, 2, 3)', evaluator)
        self.assertIn("load_valid_stage_receipt", evaluator)
        self.assertIn("finally:", evaluator)
        self.assertNotIn("AWS_ACCESS_KEY_ID", evaluator)
        self.assertNotIn("boto3", evaluator)
        self.assertNotIn("_download(", evaluator)
        self.assertIn('"sts",\n            "assume-role"', wrapper)
        self.assertIn("MINIMUM_MINTED_TTL_SECONDS = 3500", wrapper)
        self.assertIn("--acknowledge-checkpoint-access", wrapper)

    def test_stage_runtime_imports_in_isolation_without_project_packages(self) -> None:
        runtime = ROOT / "e1_staged_checkpoint_runtime.py"
        code = (
            "import importlib.util; "
            f"s=importlib.util.spec_from_file_location('stage_runtime', {str(runtime)!r}); "
            "m=importlib.util.module_from_spec(s); s.loader.exec_module(m); "
            "assert m.STAGE_SCHEMA_VERSION == 1"
        )
        completed = subprocess.run(
            [sys.executable, "-I", "-c", code],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_stage_wrapper_defaults_to_no_cloud_dry_run(self) -> None:
        from scripts.launch_g0_e1_checkpoint_stage_v3 import main
        from unittest.mock import patch

        with patch("sys.argv", ["launch-stage"]), redirect_stdout(io.StringIO()) as out:
            self.assertEqual(main(), 0)
        payload = json.loads(out.getvalue())
        self.assertEqual(payload["status"], "dry_run")
        self.assertFalse(payload["gpu_used"])
        self.assertIn("--detach", payload["command"])

    def test_stage_wrapper_mints_and_validates_a_fresh_target_session(self) -> None:
        from datetime import datetime, timedelta, timezone
        from scripts import launch_g0_e1_checkpoint_stage_v3 as launcher
        from unittest.mock import patch

        expiration = (datetime.now(timezone.utc) + timedelta(seconds=3590)).isoformat()
        source_arn = (
            "arn:aws:sts::960946312280:assumed-role/"
            "AWSReservedSSO_ENPIREG0VerifierAccess_fixture/verifier"
        )
        responses = [
            {"Account": launcher.ACCOUNT, "Arn": source_arn},
            {
                "AssumedRoleUser": {"Arn": launcher.EXPECTED_TARGET_ARN},
                "Credentials": {
                    "AccessKeyId": "access",
                    "SecretAccessKey": "secret",
                    "SessionToken": "token",
                    "Expiration": expiration,
                },
            },
        ]
        with patch.object(launcher, "_run_json", side_effect=responses) as run_json:
            environment, observed_source = launcher._fresh_target_credentials()
        self.assertEqual(observed_source, source_arn)
        self.assertEqual(environment["AWS_CREDENTIAL_EXPIRATION"], expiration)
        self.assertEqual(
            set(environment),
            {
                "AWS_ACCESS_KEY_ID",
                "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN",
                "AWS_CREDENTIAL_EXPIRATION",
            },
        )
        assume_argv = run_json.call_args_list[1].args[0]
        self.assertIn("assume-role", assume_argv)
        self.assertIn("3600", assume_argv)

    def test_checked_in_interruption_stops_after_failed_shard(self) -> None:
        from supervisor.canonical import fingerprint

        envelope = json.loads(INTERRUPTION.read_text(encoding="utf-8"))
        payload = envelope["payload"]
        self.assertEqual(envelope["sha256"], fingerprint(payload))
        self.assertEqual(
            payload["shard_0"]["status"], "complete_valid_development_shard"
        )
        self.assertEqual(payload["shard_0"]["metric"]["num_trajectories"], 64)
        self.assertEqual(
            payload["shard_1"]["status"], "failed_before_checkpoint_download"
        )
        self.assertFalse(payload["shard_1"]["metric_produced"])
        self.assertFalse(payload["shards_2_and_3"]["function_calls_created"])
        self.assertFalse(any(payload["authority"].values()))

    def test_checked_in_approval_is_exactly_bounded(self) -> None:
        from supervisor.canonical import fingerprint

        envelope = json.loads(APPROVAL.read_text(encoding="utf-8"))
        payload = envelope["payload"]
        self.assertEqual(envelope["sha256"], fingerprint(payload))
        self.assertTrue(payload["authority"]["checkpoint_2000_v6_shards_authorized"])
        self.assertFalse(payload["authority"]["automatic_retry_authorized"])
        self.assertFalse(payload["authority"]["replacement_shard_authorized"])
        self.assertTrue(payload["execution"]["sequential"])
        self.assertEqual(payload["execution"]["modal_retries"], 0)
        self.assertEqual(
            [shard["index"] for shard in payload["execution"]["shards"]],
            [0, 1, 2, 3],
        )
        self.assertLessEqual(
            payload["budget"]["projected_maximum_cumulative_d1_cost_usd"],
            payload["budget"]["maximum_cumulative_d1_cost_usd"],
        )

    def test_metric_parser_requires_one_exact_complete_shard(self) -> None:
        metric = parse_final_eval_metrics(metric_line(27, episode_len=321.5))
        self.assertEqual(metric["num_successes"], 27)
        self.assertEqual(metric["num_trajectories"], 64)
        self.assertEqual(metric["success_once"], 27 / 64)
        self.assertEqual(metric["episode_len_mean"], 321.5)
        for invalid in (
            "no metric",
            metric_line(1, trajectories=63),
            metric_line(1) + "\n" + metric_line(2),
            metric_line(65),
        ):
            with self.subTest(invalid=invalid[:30]):
                with self.assertRaises(E1ShardError):
                    parse_final_eval_metrics(invalid)

    def test_four_exact_shards_aggregate_to_one_256_trajectory_metric(self) -> None:
        receipts = [receipt(index, successes) for index, successes in enumerate((8, 16, 24, 32))]
        result = aggregate_shard_receipts(receipts)
        self.assertEqual(result["metric"]["num_successes"], 80)
        self.assertEqual(result["metric"]["num_trajectories"], 256)
        self.assertEqual(result["metric"]["success_once"], 80 / 256)
        self.assertEqual(result["shard_indices"], [0, 1, 2, 3])
        self.assertEqual(result["status"], "complete_valid_development_baseline")

    def test_missing_duplicate_failed_or_identity_drift_shards_fail_closed(self) -> None:
        valid = [receipt(index, 10 + index) for index in range(4)]
        cases = []
        cases.append(valid[:3])
        duplicate = copy.deepcopy(valid)
        duplicate[3]["shard"] = shard_spec(2).to_dict()
        cases.append(duplicate)
        failed = copy.deepcopy(valid)
        failed[1]["status"] = "failed_no_metric"
        cases.append(failed)
        drift = copy.deepcopy(valid)
        drift[2]["checkpoint"]["sha256"] = "d" * 64
        cases.append(drift)
        authorizing = copy.deepcopy(valid)
        authorizing[0]["authority"]["additional_shard_authorized"] = True
        cases.append(authorizing)
        boundary = copy.deepcopy(valid)
        boundary[0]["shard"]["offset"] = 16
        cases.append(boundary)
        for candidate in cases:
            with self.subTest(case=len(candidate)):
                with self.assertRaises(E1ShardError):
                    aggregate_shard_receipts(candidate)

    def test_aggregator_output_is_create_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = []
            for index in range(4):
                path = root / f"shard-{index}.json"
                path.write_text(json.dumps(receipt(index, index + 1)), encoding="utf-8")
                paths.append(path)
            output = root / "aggregate.json"
            from scripts.aggregate_g0_e1_shards import main
            from unittest.mock import patch

            argv = ["aggregate"]
            for path in paths:
                argv.extend(("--receipt", str(path)))
            argv.extend(("--output", str(output)))
            with patch("sys.argv", argv), redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 0)
            with patch("sys.argv", argv):
                with self.assertRaises(FileExistsError):
                    main()

    def test_launcher_and_config_are_bounded_non_authorizing_shards(self) -> None:
        text = LAUNCHER.read_text(encoding="utf-8")
        config = json.loads(CONFIG.read_text(encoding="utf-8"))
        runner = RUNNER.read_text(encoding="utf-8")
        self.assertIn("FUNCTION_TIMEOUT_SECONDS = 3600", text)
        self.assertIn('MAX_FOUR_SHARD_GPU_RUNTIME_COST_USD = "7.804800"', text)
        self.assertIn("retries=0", text)
        self.assertIn("single_use_containers=True", text)
        self.assertIn("evaluate_shard.spawn(shard.index)", text)
        self.assertNotIn("aggregate_shard_receipts", text)
        self.assertEqual(config["evaluation"]["num_trajectories"], 64)
        self.assertEqual(config["evaluation"]["shard_count"], 4)
        self.assertIn("env.eval.rollout_epoch=4", config["hydra_overrides"])
        self.assertIn("E1 shard must be one frozen contiguous 64-reset slice", runner)
        self.assertEqual(
            evaluator_contract_sha256(ROOT),
            "ee979edef79b84440bfac0b6f0a787315af71b69252be64cfea06465935dd256",
        )


if __name__ == "__main__":
    unittest.main()
