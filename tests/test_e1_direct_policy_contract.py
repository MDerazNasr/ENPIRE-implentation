import ast
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "scripts/run_g0_e1_checkpoint_evaluation.py"
SITECUSTOMIZE = ROOT / "e1_runtime" / "sitecustomize.py"
LAUNCHER = ROOT / "modal_e1_l40s.py"


class E1DirectPolicyContractTests(unittest.TestCase):
    def test_runner_uses_one_direct_openpi_model(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        ast.parse(text)
        self.assertIn("configure_direct_openpi_policy(cfg)", text)
        self.assertIn("cfg.rollout.rlt_feature_model = None", text)
        self.assertIn('"direct_openpi_policy": True', text)
        self.assertIn('"rlt_feature_model_loaded": False', text)

    def test_frozen_adapter_propagates_to_worker_processes(self) -> None:
        hook = SITECUSTOMIZE.read_text(encoding="utf-8")
        launcher = LAUNCHER.read_text(encoding="utf-8")
        ast.parse(hook)
        ast.parse(launcher)
        self.assertIn('os.environ.get("QUALIA_E1_FROZEN_DEVELOPMENT") == "1"', hook)
        self.assertIn("E1FrozenDevelopmentManiskillRLTEnv", hook)
        self.assertIn('"QUALIA_E1_FROZEN_DEVELOPMENT": "1"', launcher)
        self.assertIn('E1_RUNTIME_ROOT = f"{PROJECT_ROOT}/e1_runtime"', launcher)
        self.assertIn(
            'f"{E1_RUNTIME_ROOT}:{PROJECT_ROOT}:{RLINF_HOME}"',
            launcher,
        )


if __name__ == "__main__":
    unittest.main()
