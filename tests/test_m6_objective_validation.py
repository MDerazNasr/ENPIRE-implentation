from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from supervisor.objective_validation import (
    OBJECTIVE_CONTRACT_VERSION,
    OBJECTIVE_RELATIVE_PATH,
    ObjectiveValidationRunner,
    evaluate_objective_plugin,
    validate_actor_objective_source,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT = (
    "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
    "    return actor_loss + bc_weight * bc_loss\n"
)
CHANGED = (
    "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
    "    return actor_loss + bc_weight * bc_loss + 0.1 * bc_loss\n"
)


class M6ObjectiveValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.workspace = Path(self.temp.name)
        self.plugin = self.workspace / OBJECTIVE_RELATIVE_PATH
        self.plugin.parent.mkdir(parents=True)
        self.runner = ObjectiveValidationRunner(
            python_executable=Path(sys.executable),
            validator_script=ROOT / "scripts" / "validate_m6_objective.py",
        )

    def write(self, source: str) -> None:
        self.plugin.write_text(source, encoding="utf-8")

    def test_default_is_equivalent_and_candidate_changes_value_and_gradient(self) -> None:
        self.write(DEFAULT)
        default = evaluate_objective_plugin(
            self.plugin,
            display_path=OBJECTIVE_RELATIVE_PATH,
            require_behavior_change=False,
        )
        self.assertTrue(default.passed)
        self.assertFalse(default.behavior_changed)
        self.assertEqual(default.contract_version, OBJECTIVE_CONTRACT_VERSION)
        self.write(CHANGED)
        candidate = evaluate_objective_plugin(
            self.plugin,
            display_path=OBJECTIVE_RELATIVE_PATH,
            require_behavior_change=True,
        )
        self.assertTrue(candidate.passed)
        self.assertTrue(candidate.behavior_changed)
        self.assertNotEqual(candidate.candidate_values, candidate.reference_values)
        self.assertNotEqual(candidate.candidate_gradient, candidate.reference_gradient)

    def test_isolated_runner_returns_hash_bound_result(self) -> None:
        self.write(CHANGED)
        result = self.runner.validate(
            workspace=self.workspace,
            plugin_relative_path=OBJECTIVE_RELATIVE_PATH,
            require_behavior_change=True,
        )
        self.assertTrue(result.passed)
        self.assertTrue(result.behavior_changed)
        self.assertEqual(len(result.source_sha256), 64)

    def test_noop_wrong_abi_top_level_state_and_runtime_fail_closed(self) -> None:
        cases = {
            "noop": DEFAULT,
            "wrong-abi": "def objective(a, b):\n    return a + b\n",
            "top-level": "state = 1\n" + DEFAULT,
            "nonfinite": (
                "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
                "    return float('inf') + actor_loss * 0\n"
            ),
            "disconnected": (
                "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
                "    return 1.0\n"
            ),
        }
        for name, source in cases.items():
            with self.subTest(name=name):
                self.write(source)
                result = self.runner.validate(
                    workspace=self.workspace,
                    plugin_relative_path=OBJECTIVE_RELATIVE_PATH,
                    require_behavior_change=True,
                )
                self.assertFalse(result.passed)
                self.assertTrue(result.errors)

    def test_static_contract_rejects_decorators_defaults_and_extra_helpers(self) -> None:
        cases = (
            (
                "def combine_actor_objective(actor_loss, bc_loss, bc_weight=1):\n"
                "    return actor_loss + bc_weight * bc_loss\n"
            ),
            "@staticmethod\n" + DEFAULT,
            DEFAULT + "\ndef helper():\n    return 1\n",
        )
        for source in cases:
            with self.subTest(source=source):
                self.assertTrue(validate_actor_objective_source(source.encode()))

    def test_static_contract_rejects_stateful_torch_calls_and_control_flow(self) -> None:
        cases = (
            (
                "import torch\n\n"
                "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
                "    torch.save(actor_loss, 'escape.pt')\n"
                "    return actor_loss + bc_weight * bc_loss\n"
            ),
            (
                "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
                "    while bc_weight:\n"
                "        bc_weight = bc_weight - 1\n"
                "    return actor_loss + bc_weight * bc_loss\n"
            ),
            (
                "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
                "    actor_loss[0] = 0\n"
                "    return actor_loss + bc_weight * bc_loss\n"
            ),
            (
                "from torch import save as abs\n\n"
                "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
                "    abs(actor_loss, 'escape.pt')\n"
                "    return actor_loss + bc_weight * bc_loss\n"
            ),
            (
                "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
                "    import math\n"
                "    return actor_loss + bc_weight * bc_loss\n"
            ),
            (
                "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
                "    def abs(value):\n"
                "        return value\n"
                "    return abs(actor_loss + bc_weight * bc_loss)\n"
            ),
            (
                "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
                "    if bc_weight:\n"
                "        return actor_loss + bc_weight * bc_loss\n"
                "    return actor_loss\n"
            ),
        )
        for source in cases:
            with self.subTest(source=source):
                issues = validate_actor_objective_source(source.encode())
                self.assertTrue(issues)


if __name__ == "__main__":
    unittest.main()
