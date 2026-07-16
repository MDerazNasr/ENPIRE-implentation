import sys
import tempfile
import unittest
from pathlib import Path

from agent.metrics import parse_metrics, summarize_metrics
from agent.policy_improvement import (
    build_command,
    load_phase1_overrides,
    run_experiment,
)
from agent.rules import compare_runs, propose_adjustment


class ConfigTests(unittest.TestCase):
    def test_loads_exactly_four_documented_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "phase1.yaml"
            path.write_text(
                "learning_rate: 0.0001\n"
                "regularization_strength: 1.0\n"
                "training_iterations: 1\n"
                "episode_steps: 20\n"
            )
            config = load_phase1_overrides(path)
            self.assertEqual(config["learning_rate"], 1e-4)
            self.assertEqual(config["episode_steps"], 20)

    def test_rejects_extra_fields(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "phase1.yaml"
            path.write_text(
                "learning_rate: 0.0001\n"
                "regularization_strength: 1.0\n"
                "training_iterations: 1\n"
                "episode_steps: 20\n"
                "simulator: maniskill\n"
            )
            with self.assertRaisesRegex(ValueError, "exactly four fields"):
                load_phase1_overrides(path)


class MetricsTests(unittest.TestCase):
    def test_parses_tqdm_and_evaluation_table(self):
        text = """
train/loss=4.23, train/rlt_loss=4.17, train/vla_loss=0.062
├── Evaluation ──┤
│ episode_len=10.0 │ return=0.0 │ success_once=0.0 │
"""
        metrics = parse_metrics(text)
        self.assertEqual(metrics["train/loss"], [4.23])
        self.assertEqual(metrics["eval/success_once"], [0.0])
        summary = summarize_metrics(metrics)
        self.assertEqual(summary["success"], 0.0)
        self.assertEqual(summary["loss"], 4.23)


class RuleTests(unittest.TestCase):
    def test_below_target_relaxes_regularization(self):
        params = {"learning_rate": 1e-4, "regularization_strength": 1.0}
        metrics = {"eval/success_once": [0.0], "training/bc_loss": [0.5]}
        proposed, reason = propose_adjustment(params, metrics)
        self.assertEqual(proposed["regularization_strength"], 0.8)
        self.assertEqual(proposed["learning_rate"], 1e-4)
        self.assertIn("below target", reason)

    def test_non_finite_loss_reduces_learning_rate(self):
        params = {"learning_rate": 1e-4, "regularization_strength": 1.0}
        proposed, reason = propose_adjustment(
            params, {"train/loss": [float("nan")]}
        )
        self.assertEqual(proposed["learning_rate"], 5e-5)
        self.assertIn("non-finite", reason)

    def test_success_tie_reverts(self):
        action, reason = compare_runs(
            {"success": 0.0, "loss": 1.0},
            {"success": 0.0, "loss": 0.5},
        )
        self.assertEqual(action, "revert")
        self.assertIn("success tied", reason)


class ExecutionTests(unittest.TestCase):
    def test_build_command_substitutes_parameters(self):
        manifest = _fake_manifest(Path("/tmp/fake.py"))
        command, cwd, environment = build_command(
            manifest,
            "run_000_baseline",
            Path("/tmp/out/run_000_baseline"),
            {"learning_rate": 1e-4, "regularization_strength": 1.0},
        )
        self.assertEqual(cwd, Path("/tmp"))
        self.assertIn("actor.optim.lr=0.0001", command)
        self.assertIn("algorithm.bc_weight=1.0", command)
        self.assertEqual(environment["FAKE_RUN_ID"], "run_000_baseline")

    def test_end_to_end_two_run_revert_and_jsonl(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            fake = root / "fake_rlinf.py"
            fake.write_text(
                """import sys
reg = float(next(x.split('=', 1)[1] for x in sys.argv if x.startswith('algorithm.bc_weight=')))
loss = 1.0 if reg == 1.0 else 0.9
print(f'sac/actor_loss={loss}')
print('Evaluation success_once=0.0 episode_len=10.0 return=0.0')
"""
            )
            result = run_experiment(
                _fake_manifest(fake), root / "results", "test-session"
            )
            self.assertEqual(result["status"], "complete")
            self.assertEqual(result["selected_run"], "run_000_baseline")
            self.assertEqual(result["records"][1]["regularization_strength"], 0.8)
            self.assertTrue((root / "results/phase1_runs.jsonl").exists())
            self.assertEqual(
                len((root / "results/phase1_runs.jsonl").read_text().splitlines()),
                2,
            )


def _fake_manifest(script: Path):
    return {
        "working_directory": "/tmp",
        "python": sys.executable,
        "entrypoint": str(script),
        "environment": {"FAKE_RUN_ID": "{run_id}"},
        "base_args": [],
        "logger_path_override": "runner.logger.log_path",
        "parameters": {
            "learning_rate": {"override": "actor.optim.lr", "value": 1e-4},
            "regularization_strength": {
                "override": "algorithm.bc_weight",
                "value": 1.0,
            },
        },
        "timeout_seconds": 30,
    }


if __name__ == "__main__":
    unittest.main()
