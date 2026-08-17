import os
import runpy
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np

from envs.modal_multiprocess_rlt_env import (
    ModalMultiprocessEnvError,
    _merge_worker_values,
    _slice_batch,
    expand_maniskill_seed,
)


ROOT = Path(__file__).resolve().parents[1]


class ModalAdapterUnitTests(unittest.TestCase):
    def test_scalar_seed_expansion_matches_maniskill_contract(self):
        expected = [2026] + np.random.RandomState(2026).randint(
            2**31, size=15
        ).tolist()
        self.assertEqual(expand_maniskill_seed(2026, 16), expected)
        self.assertEqual(expand_maniskill_seed(2026, 1), [2026])
        with self.assertRaises(ValueError):
            expand_maniskill_seed(2026, 0)

    def test_nested_worker_results_merge_on_batch_axis(self):
        workers = [
            {
                "images": np.full((1, 2, 2, 3), worker, dtype=np.uint8),
                "states": np.array([[worker, worker + 1]], dtype=np.float32),
                "task_descriptions": [f"task-{worker}"],
                "optional": None,
                "episode": {"success_once": np.array([worker % 2 == 0])},
            }
            for worker in range(3)
        ]
        merged = _merge_worker_values(workers)
        self.assertEqual(tuple(merged["images"].shape), (3, 2, 2, 3))
        self.assertEqual(tuple(merged["states"].shape), (3, 2))
        self.assertEqual(
            merged["task_descriptions"], ["task-0", "task-1", "task-2"]
        )
        self.assertIsNone(merged["optional"])
        self.assertEqual(
            merged["episode"]["success_once"].tolist(), [True, False, True]
        )

    def test_worker_schema_disagreement_is_rejected(self):
        with self.assertRaisesRegex(ModalMultiprocessEnvError, "mapping keys"):
            _merge_worker_values([{"a": np.array([1])}, {"b": np.array([2])}])
        with self.assertRaisesRegex(ModalMultiprocessEnvError, "None-valued"):
            _merge_worker_values([None, np.array([1])])

    def test_mapping_order_is_not_treated_as_schema_disagreement(self):
        merged = _merge_worker_values(
            [
                {"a": np.array([1]), "b": np.array([2])},
                {"b": np.array([3]), "a": np.array([4])},
            ]
        )
        self.assertEqual(merged["a"].tolist(), [1, 4])
        self.assertEqual(merged["b"].tolist(), [2, 3])

    def test_only_native_sparse_rlt_episode_fields_may_be_omitted(self):
        values = [
            {
                "episode": {
                    "return": np.array([1.0]),
                    "entered_actor_phase_once": np.array([True]),
                }
            },
            {"episode": {"return": np.array([2.0])}},
        ]
        merged = _merge_worker_values(values, allow_sparse_rlt_episode=True)
        self.assertEqual(merged["episode"]["return"].tolist(), [1.0, 2.0])
        self.assertNotIn("entered_actor_phase_once", merged["episode"])

        with self.assertRaisesRegex(ModalMultiprocessEnvError, r"at \$\.episode"):
            _merge_worker_values(
                [
                    {"episode": {"return": np.array([1.0]), "unexpected": 1}},
                    {"episode": {"return": np.array([2.0])}},
                ],
                allow_sparse_rlt_episode=True,
            )

    def test_batch_slice_preserves_one_environment_dimension(self):
        value = {
            "tensor_like": np.arange(12).reshape(3, 4),
            "labels": ["a", "b", "c"],
        }
        sliced = _slice_batch(value, 1)
        self.assertEqual(sliced["tensor_like"].tolist(), [[4, 5, 6, 7]])
        self.assertEqual(sliced["labels"], ["b"])

    def test_sitecustomize_hook_is_strictly_opt_in(self):
        fake_envs = types.ModuleType("rlinf.envs")
        original = lambda env_type, env_cfg=None: (env_type, env_cfg)
        fake_envs.get_env_cls = original
        fake_rlinf = types.ModuleType("rlinf")
        fake_rlinf.__path__ = []
        fake_rlinf.envs = fake_envs

        modules = {"rlinf": fake_rlinf, "rlinf.envs": fake_envs}
        with patch.dict(sys.modules, modules), patch.dict(os.environ, {}, clear=True):
            runpy.run_path(str(ROOT / "sitecustomize.py"))
            self.assertIs(fake_envs.get_env_cls, original)

        fake_envs.get_env_cls = original
        with patch.dict(sys.modules, modules), patch.dict(
            os.environ, {"QUALIA_MODAL_MULTIPROCESS": "1"}, clear=True
        ):
            runpy.run_path(str(ROOT / "sitecustomize.py"))
            adapter = fake_envs.get_env_cls("maniskill_rlt")
            self.assertEqual(adapter.__name__, "ModalMultiprocessManiskillRLTEnv")
            self.assertEqual(fake_envs.get_env_cls("libero", "cfg"), ("libero", "cfg"))


if __name__ == "__main__":
    unittest.main()
