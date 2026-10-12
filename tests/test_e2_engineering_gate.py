from __future__ import annotations

import ast
import json
import unittest
from decimal import Decimal
from pathlib import Path

from scripts.validate_e2_engineering_activation import validate


ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "modal_e2_engineering_gate.py"
CONTROL_CONFIG_PATH = ROOT / "configs/d1/e2_engineering_control_seed2026.yaml"
CANDIDATE_CONFIG_PATH = ROOT / "configs/d1/e2_engineering_candidate_seed2026.yaml"


def constants() -> dict[str, object]:
    tree = ast.parse(APP_PATH.read_text())
    values: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    values[target.id] = ast.literal_eval(node.value)
                except (ValueError, TypeError):
                    pass
    return values


class E2EngineeringGateTests(unittest.TestCase):
    def test_exact_two_arms_one_seed_and_two_segments(self) -> None:
        source = APP_PATH.read_text()
        values = constants()
        self.assertEqual(set(values["ARMS"]), {"control", "candidate"})
        self.assertEqual(set(values["SEGMENTS"]), {1, 2})
        self.assertEqual(values["SEGMENTS"][1]["max_steps"], 50)
        self.assertEqual(values["SEGMENTS"][2]["max_steps"], 100)
        self.assertIn('"seed": 2026', source)
        self.assertNotIn("ANTHROPIC", source)
        self.assertNotIn("OPENAI", source)

    def test_resource_ceiling_is_below_approved_cap(self) -> None:
        train_rate = Decimal("0.000842") + 16 * Decimal("0.0000131") + 128 * Decimal("0.00000222")
        eval_rate = Decimal("1.9512") / 3600 + 16 * Decimal("0.0000131") + 96 * Decimal("0.00000222")
        cpu_only_rate = 2 * Decimal("0.0000131") + 4 * Decimal("0.00000222")
        maximum = 4 * 59_400 * train_rate + 8 * 2_700 * eval_rate + 2_400 * cpu_only_rate
        self.assertEqual(maximum.quantize(Decimal("0.000001")), Decimal("338.298720"))
        self.assertLess(maximum, Decimal("350"))

    def test_modal_functions_disable_application_retries(self) -> None:
        source = APP_PATH.read_text()
        self.assertGreaterEqual(source.count("retries=0"), 4)
        self.assertGreaterEqual(source.count("single_use_containers=True"), 4)
        self.assertNotIn("create_if_missing=True", source)
        self.assertNotIn("shell=True", source)
        self.assertNotIn("FINAL_RESET", source)
        self.assertIn('.pip_install("modal==1.5.4")', source)
        self.assertIn("pyarrow==25.0.1", source)
        self.assertIn('{"numpy": "1.26.4", "pyarrow": "25.0.1"}', source)
        self.assertIn('e2-engineering-gate-v2', source)

    def test_selected_actor_and_evaluator_are_frozen(self) -> None:
        source = APP_PATH.read_text()
        self.assertIn("4f80c4a68a9e1118b1750fb11b9092d5592d3082160b983329b2f12bd067a146", source)
        self.assertIn("e5466ff22121cf1429a1f710639cc31ed14b67430e3c84f3760fd184a3a6e161", source)
        self.assertIn("c99cf14c7a7d926df5f502d9e5ca00d33c62487bb1ffeea1eae4f15ce47ed489", source)
        self.assertIn("ee979edef79b84440bfac0b6f0a787315af71b69252be64cfea06465935dd256", source)
        self.assertIn("for i in range(4)", source)

    def test_profile_exposes_only_the_intervention_weights(self) -> None:
        control = json.loads(CONTROL_CONFIG_PATH.read_text())
        candidate = json.loads(CANDIDATE_CONFIG_PATH.read_text())
        control_overrides = set(control["hydra_overrides"])
        candidate_overrides = set(candidate["hydra_overrides"])
        self.assertEqual(
            control_overrides - candidate_overrides,
            {
                "algorithm.actor_weight_schedule.warmup_bc_weight=7",
                "algorithm.actor_weight_schedule.online_bc_weight=2.5",
            },
        )
        self.assertEqual(
            candidate_overrides - control_overrides,
            {
                "algorithm.actor_weight_schedule.warmup_bc_weight=5.6",
                "algorithm.actor_weight_schedule.online_bc_weight=2",
            },
        )
        for config in (control, candidate):
            self.assertIn("actor.seed=2026", config["hydra_overrides"])
            self.assertIn("runner.val_check_interval=-1", config["hydra_overrides"])
            self.assertFalse(config["evaluation"]["executed_during_training"])

    def test_aggregate_is_non_promoting_and_single_seed_inconclusive(self) -> None:
        source = APP_PATH.read_text()
        self.assertIn("inconclusive_single_seed_no_promotion", source)
        self.assertIn('"policy_promotion_authorized": False', source)
        self.assertIn('"rollout_video_recorded": False', source)

    def test_preflight_is_cpu_only_and_non_authorizing(self) -> None:
        source = APP_PATH.read_text()
        start = source.index("def preflight()")
        end = source.index("def train_segment(")
        preflight = source[start:end]
        self.assertIn('"gpu_execution_authorized_by_this_receipt": False', preflight)
        self.assertIn("100 * 1024**3", preflight)

    def test_v1_approval_does_not_authorize_v2_remediation(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "approved E2 source mismatch"):
            validate()

    def test_failed_control_segment_stops_without_retry(self) -> None:
        path = ROOT / "results/agent-supervisor/g0/e2-control-segment1-failure-v1.json"
        record = json.loads(path.read_text())
        self.assertEqual(record["status"], "failed_before_first_training_step")
        self.assertEqual(record["failure"]["training_updates_completed"], 0)
        self.assertTrue(record["campaign_effect"]["gate_stopped"])
        self.assertFalse(record["campaign_effect"]["automatic_retry_launched"])
        self.assertFalse(record["authority"]["replacement_attempt_authorized"])


if __name__ == "__main__":
    unittest.main()
