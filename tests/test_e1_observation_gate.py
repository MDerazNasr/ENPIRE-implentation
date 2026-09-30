import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LAUNCHER = ROOT / "modal_e1_adapter_gate.py"
GATE = ROOT / "scripts/e1_observation_contract_gate.py"


class E1ObservationGateContractTests(unittest.TestCase):
    def test_gate_is_policy_and_checkpoint_free(self) -> None:
        text = GATE.read_text(encoding="utf-8")
        ast.parse(text)
        self.assertIn('"simulator_steps": 0', text)
        self.assertIn('"policy_loaded": False', text)
        self.assertIn('"checkpoint_accessed": False', text)
        self.assertNotIn("predict_action", text)
        self.assertNotIn("model_state_dict", text)

    def test_gate_requires_exact_observation_contract(self) -> None:
        text = GATE.read_text(encoding="utf-8")
        for key in ("main_images", "wrist_images", "states", "task_descriptions"):
            self.assertIn(f'"{key}"', text)
        self.assertIn("E1FrozenDevelopmentManiskillRLTEnv", text)
        self.assertIn('get_env_cls("maniskill_rlt", cfg.env.eval)', text)
        self.assertIn("configure_direct_openpi_policy(cfg)", text)
        self.assertIn('"direct_openpi_policy": True', text)
        self.assertIn('"rlt_feature_model_loaded": False', text)
        self.assertIn('"d1_worker_startup_hook": True', text)
        self.assertIn('"action_preparation_contract": True', text)
        self.assertIn("direct evaluation dropped the action policy setup", text)
        self.assertIn("direct evaluation action preparation shape mismatch", text)
        self.assertIn("resolved D1 runtime dropped the E1 startup hook", text)
        self.assertIn("D1 worker subprocess did not select the frozen E1 adapter", text)
        self.assertIn('"states": (16, 9)', text)

    def test_modal_launcher_has_no_gpu_or_aws_secret(self) -> None:
        text = LAUNCHER.read_text(encoding="utf-8")
        ast.parse(text)
        self.assertIn("retries=0", text)
        self.assertIn("single_use_containers=True", text)
        self.assertNotIn("gpu=", text)
        self.assertNotIn("modal.Secret", text)
        self.assertNotIn("boto3", text)
        self.assertIn('"EMBODIED_PATH": f"{RLINF_HOME}/examples/embodiment"', text)
        self.assertIn('"QUALIA_E1_FROZEN_DEVELOPMENT": "1"', text)
        self.assertIn('"QUALIA_MODAL_MULTIPROCESS": "1"', text)
        self.assertIn('.add_local_dir("agent"', text)
        self.assertIn('.add_local_dir("configs"', text)
        self.assertIn('.add_local_dir("e1_runtime"', text)
        self.assertIn('.add_local_dir("supervisor"', text)


if __name__ == "__main__":
    unittest.main()
