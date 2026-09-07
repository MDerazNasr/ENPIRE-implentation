from __future__ import annotations

import ast
import copy
import json
import tempfile
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
        self.assertIn("f2-h100-pcie-control-seed2026-attempt2", source)
        self.assertIn("f2-h100-pcie-candidate-seed2026-attempt2", source)
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


if __name__ == "__main__":
    unittest.main()
