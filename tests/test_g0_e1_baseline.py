from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from supervisor.g0_e1_baseline import select_e1_baseline


ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 64


def valid_input(success: tuple[float, float, float, float] = (0.03, 0.08, 0.12, 0.11)) -> dict:
    return {
        "schema_version": 1,
        "record_kind": "g0-e1-baseline-input",
        "lineage_id": "stage1-seed-2026",
        "training_seed": 2026,
        "source_commit": "b" * 40,
        "stage1_config_sha256": SHA,
        "actor_parent_sha256": "c" * 64,
        "development_reset_sha256": "d" * 64,
        "evaluator_source_sha256": "e" * 64,
        "evaluator_environment_sha256": "f" * 64,
        "evaluation_set_role": "development",
        "checkpoints": [
            {
                "step": step,
                "checkpoint_sha256": character * 64,
                "success_once": rate,
                "valid_outcomes": 256,
                "ancestry_complete": True,
                "loaded_without_fallback": True,
            }
            for step, rate, character in zip((250, 500, 1000, 2000), success, "1234")
        ],
    }


class G0E1BaselineTests(unittest.TestCase):
    def test_selects_highest_development_success(self) -> None:
        result = select_e1_baseline(valid_input())
        self.assertEqual(result["payload"]["status"], "selected")
        self.assertEqual(result["payload"]["selected_step"], 1000)
        self.assertFalse(result["payload"]["final_evaluation_used"])
        self.assertFalse(result["payload"]["scientific_evaluation_authorized"])
        self.assertFalse(result["payload"]["campaign_activation_authorized"])
        self.assertFalse(result["payload"]["provider_call_authorized"])
        self.assertFalse(result["payload"]["model_egress_authorized"])

    def test_exact_tie_selects_earlier_checkpoint(self) -> None:
        result = select_e1_baseline(valid_input((0.05, 0.10, 0.10, 0.08)))
        self.assertEqual(result["payload"]["selected_step"], 500)

    def test_below_floor_is_inconclusive(self) -> None:
        result = select_e1_baseline(valid_input((0.01, 0.02, 0.04, 0.03)))
        self.assertEqual(result["payload"]["status"], "inconclusive")
        self.assertIsNone(result["payload"]["selected_step"])

    def test_incomplete_checkpoint_grid_fails_closed(self) -> None:
        value = valid_input()
        value["checkpoints"][2]["ancestry_complete"] = False
        result = select_e1_baseline(value)
        self.assertEqual(result["payload"]["status"], "inconclusive")
        self.assertIn("incomplete ancestry", result["payload"]["reason"])

    def test_final_reset_selection_is_rejected(self) -> None:
        value = valid_input()
        value["evaluation_set_role"] = "final"
        with self.assertRaises(ValueError):
            select_e1_baseline(value)

    def test_cli_is_create_only(self) -> None:
        with tempfile.TemporaryDirectory(prefix="enpire-e1-selector-") as temporary:
            root = Path(temporary)
            input_path = root / "input.json"
            output_path = root / "output.json"
            input_path.write_text(json.dumps(valid_input()), encoding="utf-8")
            command = [
                sys.executable,
                "scripts/select_g0_e1_baseline.py",
                "--input",
                str(input_path),
                "--output",
                str(output_path),
            ]
            subprocess.run(command, cwd=ROOT, check=True, capture_output=True, text=True)
            second = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("output already exists", second.stderr)


if __name__ == "__main__":
    unittest.main()
