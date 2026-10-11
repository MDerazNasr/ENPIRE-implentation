import json
import unittest
from pathlib import Path

from supervisor.canonical import fingerprint
from supervisor.g0_e1_baseline import select_e1_baseline


ROOT = Path(__file__).resolve().parents[1]
G0 = ROOT / "results/agent-supervisor/g0"


class AgentExperimentReadinessTests(unittest.TestCase):
    def _envelope(self, name: str) -> dict:
        value = json.loads((G0 / name).read_text(encoding="utf-8"))
        self.assertEqual(value["sha256"], fingerprint(value["payload"]))
        return value

    def test_selected_baseline_replays_exactly(self) -> None:
        source = json.loads(
            (G0 / "e1-baseline-selection-input-v1.json").read_text(encoding="utf-8")
        )
        expected = self._envelope("e1-baseline-selection-v1.json")
        self.assertEqual(select_e1_baseline(source), expected)
        self.assertEqual(expected["payload"]["selected_step"], 2000)
        self.assertEqual(expected["payload"]["selected_success_once"], 125 / 256)

    def test_environment_completion_and_pilot_are_hash_bound(self) -> None:
        environment = self._envelope("e1-evaluator-environment-v1.json")
        completion = self._envelope("e1-step-2000-completion-v1.json")
        pilot = self._envelope("agent-config-pilot-preregistration-v1.json")
        self.assertEqual(
            completion["payload"]["evaluator_environment_sha256"],
            environment["sha256"],
        )
        self.assertEqual(completion["payload"]["aggregate"]["successes"], 125)
        self.assertEqual(pilot["payload"]["baseline"]["step"], 2000)
        self.assertEqual(pilot["payload"]["evolution"]["children_per_generation"], 3)
        self.assertEqual(pilot["payload"]["evolution"]["generations"], 2)
        activation = pilot["payload"]["activation"]
        self.assertTrue(activation["explicit_activation_receipt_required"])
        for field in (
            "agent_provider_call_authorized",
            "final_evaluation_authorized",
            "gpu_execution_authorized",
            "model_egress_authorized",
            "promotion_authorized",
        ):
            self.assertFalse(activation[field])


if __name__ == "__main__":
    unittest.main()
