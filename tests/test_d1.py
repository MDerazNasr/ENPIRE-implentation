import json
import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from agent.d1_config import (
    D1ConfigError,
    build_d1_command,
    load_d1_config,
    resolve_d1_config,
    scientific_diff,
    validate_d1_config,
    validate_rlinf_layout,
    validate_required_paths,
)
from agent.d1_launcher import main, prepare_run
from agent.d1_rules import decide_d1_candidate
from agent.provenance import create_manifest
from agent.resources import CostTracker, resource_snapshot


ROOT = Path(__file__).resolve().parents[1]
CONFIG_ROOT = ROOT / "configs/d1"


def environment(root: Path) -> dict[str, str]:
    rlinf = root / "RLinf"
    model = root / "model"
    dataset = root / "dataset"
    checkpoint = root / "checkpoint/actor"
    for path in (rlinf, model, dataset, checkpoint):
        path.mkdir(parents=True, exist_ok=True)
    (dataset / "norm_stats.json").write_text("{}\n")
    return {
        "RLINF_HOME": str(rlinf),
        "MODEL_PATH": str(model),
        "DATASET_PATH": str(dataset),
        "NORM_STATS_PATH": str(dataset / "norm_stats.json"),
        "STAGE1_CHECKPOINT": str(checkpoint),
        "WANDB_PROJECT": "qualia-d1-test",
        "WANDB_MODE": "offline",
        "WANDB_DIR": str(root / "wandb"),
        "HF_HOME": str(root / "hf-home"),
        "HF_DATASETS_CACHE": str(root / "hf-datasets"),
        "D1_SEED": "2026",
    }


class D1ConfigTests(unittest.TestCase):
    def test_all_profiles_load_and_resolve(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = environment(Path(temporary))
            for path in sorted(CONFIG_ROOT.glob("*.yaml")):
                with self.subTest(path=path.name):
                    config = resolve_d1_config(load_d1_config(path), env)
                    validate_required_paths(config)

    def test_missing_environment_is_rejected(self):
        config = load_d1_config(CONFIG_ROOT / "control.yaml")
        with self.assertRaisesRegex(D1ConfigError, "RLINF_HOME"):
            resolve_d1_config(config, {})

    def test_missing_required_path_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = environment(Path(temporary))
            config = resolve_d1_config(load_d1_config(CONFIG_ROOT / "control.yaml"), env)
            Path(env["NORM_STATS_PATH"]).unlink()
            with self.assertRaisesRegex(D1ConfigError, "norm_stats"):
                validate_required_paths(config)

    def test_placeholder_and_expert_takeover_are_rejected(self):
        config = load_d1_config(CONFIG_ROOT / "control.yaml")
        broken = json.loads(json.dumps(config))
        broken["hydra_overrides"].append("rollout.expert_model=placeholder.ckpt")
        with self.assertRaisesRegex(D1ConfigError, "placeholder"):
            validate_d1_config(broken)
        broken = json.loads(json.dumps(config))
        broken["hydra_overrides"].append(
            "env.eval.rlt_policy_switch.expert_takeover.enable=true"
        )
        with self.assertRaisesRegex(D1ConfigError, "expert takeover"):
            validate_d1_config(broken)

    def test_candidate_changes_only_scheduled_bc_weights(self):
        control = load_d1_config(CONFIG_ROOT / "control.yaml")
        candidate = load_d1_config(CONFIG_ROOT / "candidate_bc_080.yaml")
        self.assertEqual(
            scientific_diff(control, candidate),
            {
                "online_bc_weight": (2.5, 2.0),
                "warmup_bc_weight": (7, 5.6),
            },
        )
        def override_map(config):
            return {
                value.split("=", 1)[0]: value.split("=", 1)[1]
                for value in config["hydra_overrides"]
            }

        control_overrides = override_map(control)
        candidate_overrides = override_map(candidate)
        changed = {
            key
            for key in control_overrides
            if control_overrides[key] != candidate_overrides[key]
        }
        self.assertEqual(
            changed,
            {
                "algorithm.actor_weight_schedule.warmup_bc_weight",
                "algorithm.actor_weight_schedule.online_bc_weight",
            },
        )

    def test_command_uses_external_rlinf_entrypoint(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = environment(Path(temporary))
            config = resolve_d1_config(load_d1_config(CONFIG_ROOT / "control.yaml"), env)
            command, cwd = build_d1_command(config, Path(temporary) / "run")
            self.assertEqual(cwd, Path(env["RLINF_HOME"]))
            self.assertIn("--config-name", command)
            self.assertIn("maniskill_rlt_stage2_ac_mlp", command)
            self.assertIn(
                "algorithm.actor_weight_schedule.warmup_bc_weight=7", command
            )
            self.assertIn("env.eval.use_fixed_reset_state_ids=true", command)

    def test_batched_eval_preserves_declared_trajectory_count(self):
        profiles = {
            "stage2_batched_eval_probe.yaml": (64, 4),
            "stage2_batched_eval_probe_32.yaml": (32, 8),
            "stage2_l40s_cpu_transport_probe.yaml": (16, 16),
            "stage2_5d_transition_calibration.yaml": (16, 16),
            "reference.yaml": (16, 16),
            "control.yaml": (16, 16),
            "candidate_bc_080.yaml": (16, 16),
        }
        for name, (parallel_envs, rollout_epochs) in profiles.items():
            with self.subTest(profile=name):
                config = load_d1_config(CONFIG_ROOT / name)
                self.assertIn(
                    f"env.eval.total_num_envs={parallel_envs}",
                    config["hydra_overrides"],
                )
                self.assertIn(
                    f"env.eval.rollout_epoch={rollout_epochs}",
                    config["hydra_overrides"],
                )
                self.assertEqual(config["evaluation"]["num_trajectories"], 256)

    def test_l40s_batching_preserves_train_and_eval_trajectory_counts(self):
        config = load_d1_config(
            CONFIG_ROOT / "stage2_l40s_cpu_transport_probe.yaml"
        )

        self.assertIn("env.train.total_num_envs=16", config["hydra_overrides"])
        self.assertIn("env.train.rollout_epoch=4", config["hydra_overrides"])
        self.assertEqual(
            config["scientific_values"]["train_trajectories_per_step"], 64
        )
        self.assertEqual(config["evaluation"]["num_trajectories"], 256)
        self.assertIn("actor.enable_offload=true", config["hydra_overrides"])
        self.assertIn(
            "+weight_syncer.patch.transport_device=cpu",
            config["hydra_overrides"],
        )
        self.assertEqual(
            config["runtime_environment"]["PYTORCH_CUDA_ALLOC_CONF"],
            "expandable_segments:True",
        )

    def test_stage5d_calibration_preserves_upstream_warmup(self):
        config = load_d1_config(
            CONFIG_ROOT / "stage2_5d_transition_calibration.yaml"
        )
        overrides = {
            value.split("=", 1)[0]: value.split("=", 1)[1]
            for value in config["hydra_overrides"]
        }

        self.assertEqual(overrides["runner.max_steps"], "3")
        self.assertEqual(overrides["runner.val_check_interval"], "-1")
        self.assertEqual(overrides["runner.save_interval"], "-1")
        self.assertNotIn("algorithm.rlt_schedule.warmup_min_size", overrides)
        self.assertNotIn(
            "algorithm.rlt_schedule.warmup_post_collect_updates", overrides
        )
        self.assertNotIn(
            "algorithm.rlt_schedule.max_updates_per_train_step", overrides
        )
        self.assertNotIn("env.train.rlt_policy_switch.enable", overrides)
        self.assertEqual(
            config["scientific_values"]["upstream_warmup_min_size"], 10000
        )
        self.assertEqual(
            config["scientific_values"]["upstream_warmup_post_collect_updates"],
            30000,
        )

    def test_mismatched_batched_eval_count_is_rejected(self):
        config = load_d1_config(CONFIG_ROOT / "stage2_batched_eval_probe.yaml")
        broken = json.loads(json.dumps(config))
        broken["evaluation"]["num_trajectories"] = 255
        with self.assertRaisesRegex(D1ConfigError, "trajectories must equal"):
            validate_d1_config(broken)

    def test_stage1_and_stage2_use_their_upstream_launchers(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = environment(Path(temporary))
            stage1 = resolve_d1_config(
                load_d1_config(CONFIG_ROOT / "stage1_pilot.yaml"), env
            )
            stage2 = resolve_d1_config(
                load_d1_config(CONFIG_ROOT / "control.yaml"), env
            )
            self.assertEqual(stage1["entrypoint"], "examples/sft/train_vla_sft.py")
            self.assertEqual(stage1["config_path"], "examples/sft/config")
            self.assertEqual(
                stage2["entrypoint"],
                "examples/embodiment/train_embodied_agent.py",
            )
            self.assertEqual(stage2["config_path"], "examples/embodiment/config")

    def test_l40s_recovery_changes_only_micro_batch_and_horizon(self):
        original = load_d1_config(CONFIG_ROOT / "stage1_reduced_250.yaml")
        recovery = load_d1_config(CONFIG_ROOT / "stage1_l40s_recovery_250.yaml")

        def override_map(config):
            return {
                value.split("=", 1)[0]: value.split("=", 1)[1]
                for value in config["hydra_overrides"]
            }

        original_overrides = override_map(original)
        recovery_overrides = override_map(recovery)
        changed = {
            key
            for key in original_overrides
            if original_overrides[key] != recovery_overrides[key]
        }
        self.assertEqual(changed, {"actor.micro_batch_size"})
        self.assertEqual(recovery_overrides["actor.global_batch_size"], "256")
        self.assertEqual(recovery["scientific_values"]["learning_rate"], 0.000025)

    def test_rlinf_layout_requires_entrypoint_config_and_python(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = environment(root)
            config = resolve_d1_config(
                load_d1_config(CONFIG_ROOT / "stage1_pilot.yaml"), env
            )
            with self.assertRaisesRegex(D1ConfigError, "entrypoint"):
                validate_rlinf_layout(config)


class D1ProvenanceTests(unittest.TestCase):
    def test_run_id_cannot_escape_results_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = environment(Path(temporary))
            with patch.dict(os.environ, env, clear=True):
                with self.assertRaisesRegex(D1ConfigError, "run ID"):
                    prepare_run(
                        CONFIG_ROOT / "control.yaml",
                        Path(temporary) / "results",
                        "../../escape",
                        ROOT,
                        None,
                    )

    def test_cli_dry_run_tolerates_unprovisioned_paths(self):
        env = {
            "RLINF_HOME": "/not-provisioned/rlinf",
            "MODEL_PATH": "/not-provisioned/model",
            "DATASET_PATH": "/not-provisioned/dataset",
            "NORM_STATS_PATH": "/not-provisioned/dataset/norm_stats.json",
            "STAGE1_CHECKPOINT": "/not-provisioned/checkpoint/actor",
            "WANDB_PROJECT": "qualia-d1-test",
            "D1_SEED": "2026",
        }
        with patch.dict(os.environ, env, clear=True):
            with redirect_stdout(io.StringIO()):
                code = main(
                    [
                        "--config",
                        str(CONFIG_ROOT / "control.yaml"),
                        "--run-id",
                        "unprovisioned-dry-run",
                    ]
                )
        self.assertEqual(code, 0)

    def test_manifest_contains_config_hash_and_commits(self):
        with tempfile.TemporaryDirectory() as temporary:
            env = environment(Path(temporary))
            config_path = CONFIG_ROOT / "control.yaml"
            config = resolve_d1_config(load_d1_config(config_path), env)
            command, cwd = build_d1_command(config, Path(temporary) / "run")
            manifest = create_manifest(
                config=config,
                config_path=config_path,
                command=command,
                cwd=cwd,
                run_dir=Path(temporary) / "run",
                project_root=ROOT,
                hourly_price_usd=None,
            )
            self.assertEqual(len(manifest["config_sha256"]), 64)
            self.assertEqual(manifest["status"], "planned")
            self.assertEqual(manifest["rlinf_commit_expected"], config["expected_rlinf_commit"])

    def test_dry_run_does_not_create_run_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            env = environment(root)
            with patch.dict(os.environ, env, clear=True):
                _, _, _, run_dir, manifest = prepare_run(
                    CONFIG_ROOT / "stage1_pilot.yaml",
                    root / "results",
                    "dry-run",
                    ROOT,
                    None,
                )
            self.assertFalse(run_dir.exists())
            self.assertEqual(manifest["status"], "planned")

    def test_execute_requires_paid_acknowledgement(self):
        with self.assertRaises(SystemExit) as raised:
            main(
                [
                    "--config",
                    str(CONFIG_ROOT / "control.yaml"),
                    "--run-id",
                    "blocked",
                    "--execute",
                ]
            )
        self.assertEqual(raised.exception.code, 2)


class ResourceAndCostTests(unittest.TestCase):
    def test_cost_thresholds_are_emitted_once_and_cap_stops(self):
        tracker = CostTracker(
            hourly_price_usd=10,
            max_cost_usd=15,
            thresholds_usd=[5, 10, 15],
            initial_cost_usd=4,
            started_monotonic=0,
        )
        self.assertEqual(tracker.crossed_thresholds(now=3600), [5, 10])
        self.assertEqual(tracker.crossed_thresholds(now=3600), [])
        self.assertTrue(tracker.cap_reached(now=3960))
        self.assertEqual(tracker.run_cost(now=3600), 10)

    def test_resource_snapshot_works_without_requiring_a_gpu(self):
        with tempfile.TemporaryDirectory() as temporary:
            snapshot = resource_snapshot(Path(temporary))
            self.assertIn("gpus", snapshot)
            self.assertIn("system_memory", snapshot)
            self.assertIn("total_bytes", snapshot["system_memory"])
            self.assertGreater(snapshot["disk_total_bytes"], 0)


class ScientificDecisionTests(unittest.TestCase):
    def test_below_ceiling_keep_requires_effect_and_interval(self):
        result = decide_d1_candidate(
            [0.50, 0.51, 0.49],
            [0.57, 0.58, 0.56],
        )
        self.assertEqual(result.decision, "keep")
        self.assertGreater(result.success_delta_ci95[0], 0)

    def test_below_ceiling_small_gain_reverts(self):
        result = decide_d1_candidate(
            [0.50, 0.51, 0.49],
            [0.52, 0.53, 0.51],
        )
        self.assertEqual(result.decision, "revert")

    def test_ceiling_case_needs_efficiency_and_non_inferiority(self):
        result = decide_d1_candidate(
            [0.94, 0.95, 0.96],
            [0.93, 0.94, 0.95],
            control_successful_episode_length=[100, 100, 100],
            candidate_successful_episode_length=[88, 89, 89],
        )
        self.assertEqual(result.decision, "keep")

    def test_missing_seed_is_inconclusive(self):
        result = decide_d1_candidate([0.5, 0.6], [0.6, 0.7])
        self.assertEqual(result.decision, "inconclusive")


if __name__ == "__main__":
    unittest.main()
