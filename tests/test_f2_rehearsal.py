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


if __name__ == "__main__":
    unittest.main()
