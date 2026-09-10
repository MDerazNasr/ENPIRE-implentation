from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_f2_rehearsal import (
    DEFAULT_PROFILE,
    ROOT,
    build_preflight,
    validate_profile,
)


class F2RehearsalTests(unittest.TestCase):
    def test_profile_is_non_authorizing_and_exactly_matched(self) -> None:
        profile = validate_profile()["profile"]
        self.assertEqual(profile["resources"]["function_timeout_seconds"], 9000)
        self.assertEqual(profile["billing"]["maximum_runtime_resource_cost_usd"], "11.382480")
        self.assertEqual(profile["billing"]["maximum_total_provider_cost_usd"], "12.00")
        self.assertFalse(profile["approval"]["gpu_execution_authorized"])
        self.assertFalse(profile["approval"]["promotion_authorized"])
        self.assertEqual(
            [item["arm"] for item in profile["fixed_sequence"]],
            ["control", "candidate", "engineering-only"],
        )

    def test_preflight_binds_three_contracts_without_authorizing_run(self) -> None:
        with (
            patch(
                "scripts.run_f2_rehearsal._git",
                side_effect=["", "6b0b9606d50fa562583d733a34bda81b1dd2ac48"],
            ),
            patch("scripts.run_f2_rehearsal._verify_modal_import"),
        ):
            preflight = build_preflight()
        self.assertEqual(preflight["status"], "ready_for_explicit_approval")
        self.assertEqual(len(preflight["contracts"]), 3)
        self.assertFalse(preflight["execution_authorized"])
        self.assertFalse(preflight["gpu_execution_authorized"])
        self.assertFalse(preflight["promotion_authorized"])

    def test_rejects_undeclared_arm_difference(self) -> None:
        profile = json.loads(DEFAULT_PROFILE.read_text())
        candidate_path = ROOT / profile["fixed_sequence"][1]["profile"]
        candidate = json.loads(candidate_path.read_text())
        candidate["scientific_values"]["episode_horizon"] = 499
        candidate["hydra_overrides"] = [
            "env.train.max_episode_steps=499"
            if value == "env.train.max_episode_steps=500"
            else value
            for value in candidate["hydra_overrides"]
        ]
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            mutated_candidate = temporary / "candidate.yaml"
            mutated_candidate.write_text(json.dumps(candidate))
            mutated_profile = copy.deepcopy(profile)
            mutated_profile["fixed_sequence"][1]["profile"] = str(mutated_candidate)
            profile_path = temporary / "profile.json"
            profile_path.write_text(json.dumps(mutated_profile))
            with self.assertRaisesRegex(ValueError, "not the intervention"):
                validate_profile(profile_path)

    def test_modal_entrypoint_has_no_user_selected_target_or_command(self) -> None:
        tree = ast.parse((ROOT / "modal_f2_rehearsal.py").read_text())
        main = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        self.assertEqual(main.args.args, [])
        source = (ROOT / "modal_f2_rehearsal.py").read_text()
        self.assertNotIn("shell=True", source)
        self.assertNotIn("create_if_missing=True", source)

    def test_h100_amendment_and_runner_are_fixed_and_non_promotable(self) -> None:
        amendment = json.loads(
            (
                ROOT
                / "results/runtime-qualification/f0/h100-sxm5-amendment.json"
            ).read_text()
        )
        self.assertEqual(
            amendment["provider"]["gpu_model"], "NVIDIA H100 80GB HBM3"
        )
        self.assertEqual(amendment["provider"]["minimum_gpu_memory_bytes"], 80_000_000_000)
        self.assertFalse(amendment["authorization"]["scientific_runs_authorized"])
        self.assertFalse(amendment["authorization"]["promotion_authorized"])
        self.assertEqual(
            amendment["billing"]["maximum_additional_auto_shutdown_exposure_usd"],
            "25.5255",
        )
        runner_path = ROOT / "scripts/run_f2_h100_rehearsal.py"
        tree = ast.parse(runner_path.read_text())
        main = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "main"
        )
        self.assertEqual(main.args.args, [])
        source = runner_path.read_text()
        self.assertNotIn("shell=True", source)
        self.assertIn("f2-h100-pcie-control-seed2026-attempt6", source)
        self.assertIn("f2-h100-pcie-candidate-seed2026-attempt6", source)
        self.assertNotIn("f2-h100-pcie-control-seed2026-attempt5", source)
        self.assertIn('attempt-6.json', source)
        self.assertIn('NVIDIA H100 PCIe', source)
        self.assertIn('/opt/f2-norm-stats/norm_stats.json', source)
        dockerfile = (ROOT / "Dockerfile.f2-h100").read_text()
        self.assertIn(
            "nvidia/cuda@sha256:6617a625f4090c76c545a0e7d63f2e441718ef9af7f4efe7dd1242a29e289fd7",
            dockerfile,
        )
        pcie = json.loads(
            (ROOT / "results/runtime-qualification/f0/h100-pcie-amendment.json").read_text()
        )
        self.assertEqual(pcie["provider"]["gpu_model"], "NVIDIA H100 PCIe")
        self.assertEqual(pcie["provider"]["instance_id"], "be7f43492c014409ad94d42371ff86d4")
        self.assertEqual(pcie["billing"]["maximum_9000_second_in_container_cost_usd"], "8.2250")
        self.assertFalse(pcie["authorization"]["actor_export_authorized"])
        self.assertFalse(pcie["authorization"]["gpu_retry_execution_authorized"])
        replacement = json.loads(
            (ROOT / "results/runtime-qualification/f0/h100-pcie-instance-2-amendment.json").read_text()
        )
        self.assertEqual(replacement["provider"]["instance_id"], "488738cc7b404e7aa86ad2e02c70acdf")
        self.assertEqual(replacement["provider"]["ip"], "209.20.158.151")
        self.assertFalse(replacement["authorization"]["actor_export_authorized"])
        self.assertFalse(replacement["authorization"]["gpu_retry_execution_authorized"])
        latest = json.loads(
            (ROOT / "results/runtime-qualification/f0/h100-pcie-instance-3-amendment.json").read_text()
        )
        self.assertEqual(latest["provider"]["instance_id"], "e4907a39365a444c8ae47426f0380019")
        self.assertEqual(latest["provider"]["ip"], "209.20.158.134")
        self.assertFalse(latest["authorization"]["actor_export_authorized"])
        self.assertFalse(latest["authorization"]["gpu_retry_execution_authorized"])
        current = json.loads(
            (ROOT / "results/runtime-qualification/f0/h100-pcie-instance-4-amendment.json").read_text()
        )
        self.assertEqual(current["provider"]["instance_id"], "a5f648f727ab499087a54c598e975e97")
        self.assertEqual(current["provider"]["ip"], "209.20.157.182")
        self.assertTrue(current["ssh_qualification"]["completed"])
        self.assertTrue(current["authorization"]["source_sync_authorized"])
        self.assertTrue(
            current["authorization"]["public_image_build_and_probe_authorized"]
        )
        self.assertFalse(current["authorization"]["actor_export_authorized"])
        self.assertFalse(current["authorization"]["gpu_execution_authorized"])
        self.assertNotIn("a5f648f727ab499087a54c598e975e97", source)
        pending = json.loads(
            (ROOT / "results/runtime-qualification/f0/h100-pcie-instance-5-amendment.json").read_text()
        )
        self.assertEqual(pending["provider"]["instance_id"], "0bf25a97ea114ce5b4d87a8733085bf9")
        self.assertEqual(pending["provider"]["ip"], "209.20.157.158")
        self.assertTrue(pending["ssh_qualification"]["completed"])
        self.assertTrue(pending["prior_attempt"]["duplicate_execution_forbidden"])
        self.assertTrue(pending["authorization"]["source_sync_authorized"])
        self.assertTrue(
            pending["authorization"]["public_image_build_and_probe_authorized"]
        )
        self.assertFalse(pending["authorization"]["actor_export_authorized"])
        self.assertFalse(pending["authorization"]["gpu_execution_authorized"])
        self.assertNotIn("0bf25a97ea114ce5b4d87a8733085bf9", source)
        preflight = json.loads(
            (
                ROOT
                / "results/runtime-qualification/f2/h100-pcie-instance-5-preflight.json"
            ).read_text()
        )
        self.assertEqual(preflight["source_commit"], "2c0b482f495c36d66e3891f573fa12a6ccb51450")
        self.assertEqual(
            preflight["execution"]["image_id"],
            "sha256:5d7928a2acfe008f75044fd016699bc44943cffd9d14f4ddbfbf8313d3871bc0",
        )
        self.assertEqual(preflight["qualification"]["source_hashes_verified"], 15)
        self.assertEqual(preflight["qualification"]["source_hash_mismatches"], 0)
        self.assertFalse(preflight["actor_export"]["authorized"])
        self.assertFalse(preflight["authorization"]["gpu_retry_execution_authorized"])
        self.assertFalse(preflight["prior_execution"]["duplicate_execution_authorized"])
        approval = json.loads(
            (
                ROOT
                / "results/runtime-qualification/f2/h100-pcie-instance-5-approval-attempt-5.json"
            ).read_text()
        )
        self.assertTrue(
            approval["prior_attempt"]["possible_duplicate_execution_acknowledged"]
        )
        self.assertTrue(approval["actor_export"]["authorized"])
        self.assertFalse(approval["actor_export"]["completed"])
        self.assertFalse(
            approval["actor_export"]["transfer_observation"]["ordered_reassembly_started"]
        )
        self.assertTrue(approval["execution_authorized"])
        self.assertFalse(approval["execution_started"])
        self.assertTrue(approval["host_recovery"]["dashboard_status_reconfirmation_required"])
        self.assertFalse(approval["scientific_runs_authorized"])
        self.assertFalse(approval["evaluation_authorized"])
        self.assertFalse(approval["promotion_authorized"])
        replacement = json.loads(
            (ROOT / "results/runtime-qualification/f0/h100-pcie-instance-6-amendment.json").read_text()
        )
        self.assertEqual(replacement["provider"]["instance_id"], "268cdf9dce05458fadcf8f6c748f6d85")
        self.assertEqual(replacement["provider"]["ip"], "209.20.158.196")
        self.assertTrue(replacement["ssh_qualification"]["completed"])
        self.assertFalse(replacement["host_probe"]["attempt_5_storage_present"])
        self.assertFalse(replacement["prior_attempt"]["storage_reuse_assumed"])
        self.assertTrue(replacement["authorization"]["source_sync_authorized"])
        self.assertTrue(replacement["authorization"]["public_image_build_and_probe_authorized"])
        self.assertFalse(replacement["authorization"]["actor_export_authorized"])
        self.assertFalse(replacement["authorization"]["gpu_execution_authorized"])
        self.assertIn("268cdf9dce05458fadcf8f6c748f6d85", source)
        preprovision = json.loads(
            (
                ROOT
                / "results/runtime-qualification/f2/h100-pcie-instance-6-preprovision.json"
            ).read_text()
        )
        self.assertEqual(preprovision["source_commit"], "4a49b6c598bf3d21f88e4412d22bded872ba2914")
        self.assertEqual(len(preprovision["source_hashes"]), 15)
        self.assertFalse(preprovision["authorization"]["actor_export_authorized"])
        self.assertFalse(preprovision["authorization"]["gpu_execution_authorized"])
        attempt6_preflight = json.loads(
            (
                ROOT
                / "results/runtime-qualification/f2/h100-pcie-instance-6-preflight.json"
            ).read_text()
        )
        self.assertEqual(
            attempt6_preflight["source_commit"],
            "4a49b6c598bf3d21f88e4412d22bded872ba2914",
        )
        self.assertEqual(
            attempt6_preflight["execution"]["image_id"],
            "sha256:fe90510acb55441836d6e126a130f96fb925d0e825dbf750bf76df5b63f9cf22",
        )
        self.assertEqual(attempt6_preflight["qualification"]["source_hashes_verified"], 15)
        self.assertEqual(attempt6_preflight["qualification"]["source_hash_mismatches"], 0)
        self.assertFalse(attempt6_preflight["actor_export"]["authorized"])
        self.assertFalse(
            attempt6_preflight["authorization"]["gpu_retry_execution_authorized"]
        )

    def test_h100_runner_bootstraps_project_imports_under_direct_file_launch(self) -> None:
        runner = ROOT / "scripts/run_f2_h100_rehearsal.py"
        with tempfile.TemporaryDirectory() as directory:
            project = Path(directory) / "qualia"
            package = project / "agent"
            package.mkdir(parents=True)
            (package / "__init__.py").write_text("")
            (package / "metrics.py").write_text(
                "def parse_metrics(value):\n    return {'loaded': value}\n"
            )
            (package / "rlt_resume_state.py").write_text(
                "def audit_state_file(*args, **kwargs):\n    return 'loaded'\n"
            )
            probe = textwrap.dedent(
                f"""
                import importlib.util
                from pathlib import Path

                spec = importlib.util.spec_from_file_location("isolated_f2_runner", {str(runner)!r})
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                module.PROJECT_ROOT = Path({str(project)!r})
                loaded = module._project_modules()
                assert loaded["agent.metrics"].parse_metrics("direct") == {{"loaded": "direct"}}
                assert loaded["agent.rlt_resume_state"].audit_state_file() == "loaded"
                print("DIRECT_FILE_IMPORT_GATE=PASS")
                """
            )
            completed = subprocess.run(
                [sys.executable, "-I", "-c", probe],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(completed.stdout.strip(), "DIRECT_FILE_IMPORT_GATE=PASS")


if __name__ == "__main__":
    unittest.main()
