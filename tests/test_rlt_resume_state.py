import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.rlt_resume_state import (
    COUNTER_FIELDS,
    RLTResumeStateError,
    audit_state_file,
    capture_state,
    restore_worker_state,
    save_worker_state,
    schedule_fingerprint,
    sidecar_path,
    validate_state,
)


class _Generator:
    def __init__(self):
        self.restored = None

    def get_state(self):
        import numpy as np

        class _State:
            def cpu(self):
                return self

            def numpy(self):
                return np.array([1, 2, 3, 4], dtype=np.uint8)

        return _State()

    def set_state(self, state):
        self.restored = state


class _Worker:
    def __init__(self):
        self._rank = 0
        self._world_size = 1
        self.cfg = types.SimpleNamespace(
            algorithm={
                "loss_type": "rlt_ac",
                "update_epoch": 1,
                "critic_actor_ratio": 1,
                "rlt_schedule": {
                    "enable": True,
                    "warmup_min_size": 1,
                    "warmup_post_collect_updates": 1,
                },
                "actor_weight_schedule": {
                    "enable": True,
                    "warmup_updates": 1,
                    "online_bc_weight": 2.0,
                },
            }
        )
        self.replay_buffer = types.SimpleNamespace(random_generator=_Generator())
        values = [1, 0, 0, 20, 1, 20, 1, 0]
        for name, value in zip(COUNTER_FIELDS, values):
            setattr(self, name, value)


class RLTResumeStateTests(unittest.TestCase):
    def test_exact_round_trip_restores_all_counters(self):
        worker = _Worker()
        worker.replay_buffer.random_generator = None
        with tempfile.TemporaryDirectory() as directory:
            actor = Path(directory) / "global_step_1/actor"
            save_worker_state(worker, actor, 1)
            for name in COUNTER_FIELDS:
                setattr(worker, name, None if name.startswith("_warmup") else 0)
            marker = restore_worker_state(worker, actor)
        self.assertEqual(marker["restored_update_step"], 1)
        self.assertEqual(worker.total_transitions_added, 20)
        self.assertEqual(worker._warmup_ready_total_transitions, 20)

    def test_replay_generator_state_is_restored(self):
        worker = _Worker()

        class _Tensor:
            def clone(self):
                return self

        fake_torch = types.SimpleNamespace(
            uint8="uint8",
            frombuffer=lambda value, dtype: _Tensor(),
        )
        with tempfile.TemporaryDirectory() as directory:
            actor = Path(directory) / "global_step_1/actor"
            save_worker_state(worker, actor, 1)
            with patch.dict(sys.modules, {"torch": fake_torch}):
                restore_worker_state(worker, actor)
        self.assertIsNotNone(worker.replay_buffer.random_generator.restored)

    def test_nullable_warmup_anchors_are_valid(self):
        worker = _Worker()
        worker._warmup_ready_total_transitions = None
        worker._warmup_ready_total_episodes = None
        state = capture_state(worker, 1)
        counters = validate_state(state, worker=worker, expected_step=1)
        self.assertIsNone(counters["_warmup_ready_total_transitions"])

    def test_schedule_mismatch_fails_closed(self):
        worker = _Worker()
        state = capture_state(worker, 1)
        worker.cfg.algorithm["actor_weight_schedule"]["online_bc_weight"] = 3.0
        with self.assertRaisesRegex(RLTResumeStateError, "fingerprint"):
            validate_state(state, worker=worker, expected_step=1)

    def test_step_and_rank_mismatch_fail_closed(self):
        worker = _Worker()
        state = capture_state(worker, 1)
        with self.assertRaisesRegex(RLTResumeStateError, "checkpoint_step"):
            validate_state(state, worker=worker, expected_step=2)
        worker._rank = 1
        with self.assertRaisesRegex(RLTResumeStateError, "rank"):
            validate_state(state, worker=worker, expected_step=1)

    def test_missing_or_malformed_sidecar_fails_closed(self):
        worker = _Worker()
        with tempfile.TemporaryDirectory() as directory:
            actor = Path(directory) / "global_step_1/actor"
            with self.assertRaisesRegex(RLTResumeStateError, "missing"):
                restore_worker_state(worker, actor)
            path = sidecar_path(actor, 0)
            path.parent.mkdir(parents=True)
            path.write_text("not-json")
            with self.assertRaisesRegex(RLTResumeStateError, "invalid"):
                restore_worker_state(worker, actor)

    def test_state_file_contains_contract_and_fingerprint(self):
        worker = _Worker()
        with tempfile.TemporaryDirectory() as directory:
            actor = Path(directory) / "global_step_1/actor"
            path = save_worker_state(worker, actor, 1)
            state = json.loads(path.read_text())
        self.assertEqual(state["schedule_fingerprint"], schedule_fingerprint(worker.cfg))
        self.assertEqual(set(state["counters"]), set(COUNTER_FIELDS))

    def test_saved_sidecar_passes_worker_free_deep_audit(self):
        worker = _Worker()
        with tempfile.TemporaryDirectory() as directory:
            actor = Path(directory) / "global_step_1/actor"
            path = save_worker_state(worker, actor, 1)
            audit = audit_state_file(path, expected_step=1)
        self.assertEqual(audit["counters"]["update_step"], 1)
        self.assertTrue(audit["replay_generator_state_present"])

    def test_deep_audit_rejects_fingerprint_and_rng_corruption(self):
        worker = _Worker()
        with tempfile.TemporaryDirectory() as directory:
            actor = Path(directory) / "global_step_1/actor"
            path = save_worker_state(worker, actor, 1)
            state = json.loads(path.read_text())
            state["schedule_fingerprint"] = "0" * 64
            path.write_text(json.dumps(state))
            with self.assertRaisesRegex(RLTResumeStateError, "self-consistent"):
                audit_state_file(path, expected_step=1)

            state["schedule_fingerprint"] = schedule_fingerprint(worker.cfg)
            state["replay_generator_state_b64"] = "not-base64!"
            path.write_text(json.dumps(state))
            with self.assertRaisesRegex(RLTResumeStateError, "base64"):
                audit_state_file(path, expected_step=1)

    def test_patch_installation_is_idempotent(self):
        class FakePolicy:
            def save_checkpoint(self, path, step):
                return "saved"

            def load_checkpoint(self, path):
                return "loaded"

        fake_module = types.ModuleType(
            "rlinf.workers.actor.fsdp_rlt_ac_policy_worker"
        )
        fake_module.RLTACFSDPPolicy = FakePolicy
        modules = {
            "rlinf": types.ModuleType("rlinf"),
            "rlinf.workers": types.ModuleType("rlinf.workers"),
            "rlinf.workers.actor": types.ModuleType("rlinf.workers.actor"),
            "rlinf.workers.actor.fsdp_rlt_ac_policy_worker": fake_module,
        }
        from agent.rlt_resume_state import install_patch

        with patch.dict(sys.modules, modules):
            self.assertTrue(install_patch())
            self.assertFalse(install_patch())


if __name__ == "__main__":
    unittest.main()
