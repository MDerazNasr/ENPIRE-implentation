"""Process-batched ManiSkill RLT adapter for Modal's CPU Vulkan renderer.

Modal GPU containers do not expose the DRM/modeset devices required by
SAPIEN's NVIDIA Vulkan renderer.  The Mesa CPU renderer works, but ManiSkill's
CPU simulation backend intentionally supports one environment per process.
This adapter preserves the upstream :class:`ManiskillRLTEnv` implementation by
placing one unmodified instance in each child process and presenting their
concatenated outputs as one batched environment to RLinf.

This is a provisional runtime protocol.  It is activated only through the
``QUALIA_MODAL_MULTIPROCESS`` opt-in in the repository's ``sitecustomize.py``.
"""

from __future__ import annotations

import atexit
import multiprocessing
import os
import traceback
from collections.abc import Mapping, Sequence
from typing import Any


DEFAULT_RENDER_DEVICE = "pci:0000:00:00.0"
DEFAULT_VULKAN_ICD = "/usr/share/vulkan/icd.d/lvp_icd.x86_64.json"
DEFAULT_RESET_STATE_COUNT = 127
_SPARSE_RLT_EPISODE_KEYS = {
    "entered_actor_phase_once",
    "actor_switch_step",
    "actor_switch_step_nonzero",
}


class ModalMultiprocessEnvError(RuntimeError):
    """Raised when a child environment fails or violates the adapter contract."""


def expand_maniskill_seed(seed: int, num_envs: int) -> list[int]:
    """Match ManiSkill's scalar-to-vector seed expansion exactly."""

    if num_envs <= 0:
        raise ValueError("num_envs must be positive")
    import numpy as np

    return [int(seed)] + np.random.RandomState(int(seed)).randint(
        2**31, size=num_envs - 1
    ).tolist()


def _to_transport(value: Any) -> Any:
    """Convert tensors to ordinary NumPy payloads before crossing a pipe."""

    try:
        import torch
    except ImportError:  # pragma: no cover - only used in provisioned runtime
        torch = None
    if torch is not None and isinstance(value, torch.Tensor):
        return value.detach().cpu().numpy()
    if isinstance(value, dict):
        return {key: _to_transport(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_transport(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_to_transport(item) for item in value)
    return value


def _merge_worker_values(
    values: Sequence[Any],
    *,
    allow_sparse_rlt_episode: bool = False,
    _path: str = "$",
) -> Any:
    """Concatenate one-environment worker values along their batch axis."""

    if not values:
        raise ValueError("cannot merge an empty worker result")
    first = values[0]
    if all(value is None for value in values):
        return None
    if any(value is None for value in values):
        raise ModalMultiprocessEnvError("workers disagreed on None-valued output")
    if isinstance(first, Mapping):
        keys = tuple(first.keys())
        key_sets = [set(value.keys()) for value in values]
        common_keys = set.intersection(*key_sets)
        differing_keys = set.union(*key_sets) - common_keys
        sparse_episode_difference = (
            allow_sparse_rlt_episode
            and _path == "$.episode"
            and differing_keys <= _SPARSE_RLT_EPISODE_KEYS
        )
        if differing_keys and not sparse_episode_difference:
            schemas = [sorted(key_set) for key_set in key_sets]
            raise ModalMultiprocessEnvError(
                f"workers returned different mapping keys at {_path}: {schemas}"
            )
        return {
            key: _merge_worker_values(
                [value[key] for value in values],
                allow_sparse_rlt_episode=allow_sparse_rlt_episode,
                _path=f"{_path}.{key}",
            )
            for key in keys
            if key in common_keys
        }

    import numpy as np

    if isinstance(first, np.ndarray):
        arrays = [np.asarray(value) for value in values]
        if first.ndim == 0:
            merged = np.stack(arrays, axis=0)
        else:
            merged = np.concatenate(arrays, axis=0)
        try:
            import torch
        except ImportError:  # pragma: no cover - runtime always has torch
            return merged
        return torch.from_numpy(merged)
    if isinstance(first, list):
        merged_list: list[Any] = []
        for value in values:
            merged_list.extend(value)
        return merged_list
    if isinstance(first, tuple):
        if any(len(value) != len(first) for value in values):
            raise ModalMultiprocessEnvError("workers returned different tuple lengths")
        return tuple(
            _merge_worker_values(
                [value[index] for value in values],
                allow_sparse_rlt_episode=allow_sparse_rlt_episode,
                _path=f"{_path}[{index}]",
            )
            for index in range(len(first))
        )
    if isinstance(first, (str, bytes)):
        return list(values)
    if isinstance(first, (bool, int, float, np.generic)):
        try:
            import torch
        except ImportError:  # pragma: no cover
            return np.asarray(values)
        return torch.as_tensor(values)
    if all(value == first for value in values):
        return first
    raise ModalMultiprocessEnvError(
        f"unsupported or inconsistent worker output type: {type(first).__name__}"
    )


def _slice_batch(value: Any, index: int) -> Any:
    if isinstance(value, dict):
        return {key: _slice_batch(item, index) for key, item in value.items()}
    if isinstance(value, list):
        return [value[index]]
    if isinstance(value, tuple):
        return tuple(_slice_batch(item, index) for item in value)
    try:
        return value[index : index + 1]
    except (TypeError, IndexError) as error:
        raise ModalMultiprocessEnvError(
            f"cannot slice batched value of type {type(value).__name__}"
        ) from error


def _patch_maniskill_pci_parser() -> None:
    """Work around the v3.0.0b22 parser's split-on-every-colon bug."""

    import mani_skill.envs.utils.system.backend as backend_utils

    original = backend_utils.parse_backend_device_id
    if getattr(original, "_qualia_accepts_pci", False):
        return

    def parse_backend_device_id(backend: str):
        if isinstance(backend, str) and backend.startswith("pci:"):
            return backend, None
        return original(backend)

    parse_backend_device_id._qualia_accepts_pci = True
    backend_utils.parse_backend_device_id = parse_backend_device_id


def _child_main(
    connection,
    cfg_container: dict[str, Any],
    worker_id: int,
    seed_offset: int,
    total_num_processes: int,
    record_metrics: bool,
) -> None:
    os.environ["VK_ICD_FILENAMES"] = os.environ.get(
        "QUALIA_MODAL_VULKAN_ICD", DEFAULT_VULKAN_ICD
    )
    os.environ.setdefault("XDG_RUNTIME_DIR", "/tmp")
    os.environ["LP_NUM_THREADS"] = os.environ.get(
        "QUALIA_MODAL_THREADS_PER_WORKER", "1"
    )
    os.environ["OMP_NUM_THREADS"] = "1"
    try:
        _patch_maniskill_pci_parser()
        import torch
        from omegaconf import OmegaConf
        from rlinf.envs.maniskill.maniskill_rlt_env import ManiskillRLTEnv

        torch.set_num_threads(1)
        cfg = OmegaConf.create(cfg_container)
        env = ManiskillRLTEnv(
            cfg=cfg,
            num_envs=1,
            seed_offset=seed_offset + worker_id,
            total_num_processes=total_num_processes,
            worker_info={"modal_adapter_worker": worker_id},
            record_metrics=record_metrics,
        )
        connection.send(
            (
                "ok",
                {
                    "total_num_group_envs": int(env.total_num_group_envs),
                    "action_shape": tuple(env.env.unwrapped.single_action_space.shape),
                },
            )
        )
        while True:
            command, payload = connection.recv()
            if command == "close":
                if hasattr(env.env, "close"):
                    env.env.close()
                connection.send(("ok", None))
                return
            if command == "reset":
                result = env.reset(**payload)
            elif command == "chunk_step":
                result = env.chunk_step(torch.from_numpy(payload))
            elif command == "update_reset_state_ids":
                env.update_reset_state_ids()
                result = None
            elif command == "set_is_start":
                env.is_start = bool(payload)
                result = None
            else:
                raise ModalMultiprocessEnvError(f"unknown child command: {command}")
            connection.send(("ok", _to_transport(result)))
    except BaseException as error:  # child must return its traceback to the parent
        try:
            connection.send(
                (
                    "error",
                    {
                        "type": type(error).__name__,
                        "message": str(error),
                        "traceback": traceback.format_exc(),
                    },
                )
            )
        except BaseException:
            pass
    finally:
        connection.close()


class ModalMultiprocessManiskillRLTEnv:
    """Batched facade over one upstream RLT environment per child process."""

    def __init__(
        self,
        cfg,
        num_envs,
        seed_offset,
        total_num_processes,
        worker_info,
        record_metrics=True,
    ):
        del worker_info
        import torch
        from omegaconf import OmegaConf

        self._num_envs = int(num_envs)
        if self._num_envs <= 0:
            raise ValueError("Modal multiprocess adapter requires num_envs > 0")
        group_size = int(cfg.group_size)
        if self._num_envs % group_size:
            raise ValueError("num_envs must be divisible by cfg.group_size")
        self.seed = int(cfg.seed) + int(seed_offset)
        self.num_group = self._num_envs // group_size
        self.group_size = group_size
        self.use_fixed_reset_state_ids = bool(cfg.use_fixed_reset_state_ids)
        self.auto_reset = bool(cfg.auto_reset)
        self._has_seeded_reset = False
        self._is_start = True
        self._closed = False
        self._device = torch.device("cpu")
        self._generator = torch.Generator().manual_seed(self.seed)

        cfg_container = OmegaConf.to_container(cfg, resolve=True)
        init_params = cfg_container.setdefault("init_params", {})
        configured_sim = init_params.get("sim_backend", "cpu")
        if configured_sim != "cpu":
            raise ModalMultiprocessEnvError(
                f"Modal adapter requires init_params.sim_backend=cpu, got {configured_sim!r}"
            )
        render_device = os.environ.get(
            "QUALIA_MODAL_RENDER_DEVICE", DEFAULT_RENDER_DEVICE
        )
        configured_render = init_params.get("render_backend", render_device)
        if configured_render != render_device:
            raise ModalMultiprocessEnvError(
                "Modal adapter render backend must match QUALIA_MODAL_RENDER_DEVICE"
            )
        init_params["render_backend"] = render_device
        init_params["num_envs"] = 1

        context_name = os.environ.get("QUALIA_MODAL_MP_START_METHOD", "spawn")
        self._context = multiprocessing.get_context(context_name)
        self._connections = []
        self._processes = []
        for worker_id in range(self._num_envs):
            parent, child = self._context.Pipe()
            process = self._context.Process(
                target=_child_main,
                args=(
                    child,
                    cfg_container,
                    worker_id,
                    int(seed_offset),
                    int(total_num_processes),
                    bool(record_metrics),
                ),
                name=f"modal-maniskill-rlt-{worker_id}",
                daemon=True,
            )
            process.start()
            child.close()
            self._connections.append(parent)
            self._processes.append(process)

        try:
            init_results = self._receive_all("initialize")
            counts = {result["total_num_group_envs"] for result in init_results}
            action_shapes = {tuple(result["action_shape"]) for result in init_results}
            if len(counts) != 1 or len(action_shapes) != 1:
                raise ModalMultiprocessEnvError(
                    "child environments disagree on reset-state or action-space metadata"
                )
            self.total_num_group_envs = counts.pop()
            self.single_action_shape = action_shapes.pop()
            self.update_reset_state_ids(propagate=False)
        except BaseException:
            self.close(force=True)
            raise
        atexit.register(self.close)

    @property
    def num_envs(self):
        return self._num_envs

    @property
    def device(self):
        return self._device

    @property
    def is_start(self):
        return self._is_start

    @is_start.setter
    def is_start(self, value):
        self._is_start = bool(value)
        if getattr(self, "_connections", None) and not self._closed:
            self._send_all("set_is_start", self._is_start)
            self._receive_all("set_is_start")

    def _send_all(self, command: str, payload: Any) -> None:
        for connection in self._connections:
            connection.send((command, payload))

    def _receive_all(self, operation: str) -> list[Any]:
        results = []
        for worker_id, connection in enumerate(self._connections):
            try:
                status, payload = connection.recv()
            except EOFError as error:
                raise ModalMultiprocessEnvError(
                    f"worker {worker_id} exited during {operation}"
                ) from error
            if status != "ok":
                raise ModalMultiprocessEnvError(
                    f"worker {worker_id} failed during {operation}: "
                    f"{payload['type']}: {payload['message']}\n{payload['traceback']}"
                )
            results.append(payload)
        return results

    def update_reset_state_ids(self, *, propagate: bool = True):
        import torch

        ids = torch.randint(
            low=0,
            high=self.total_num_group_envs,
            size=(self.num_group,),
            generator=self._generator,
        )
        self.reset_state_ids = ids.repeat_interleave(self.group_size).to(self.device)
        if propagate:
            self._send_all("update_reset_state_ids", None)
            self._receive_all("update_reset_state_ids")

    def reset(self, *, seed=None, options=None):
        import numpy as np
        import torch

        if options is not None and "env_idx" in options:
            raise ModalMultiprocessEnvError(
                "partial reset is not supported; D1 requires auto_reset=false"
            )
        if self.auto_reset:
            raise ModalMultiprocessEnvError(
                "auto_reset=true is outside the validated Modal adapter protocol"
            )

        if options is None:
            options = {}
            if self.use_fixed_reset_state_ids:
                options["episode_id"] = self.reset_state_ids
            if seed is None and (
                self.use_fixed_reset_state_ids or not self._has_seeded_reset
            ):
                seed = self.seed

        if seed is None:
            worker_seeds = [None] * self.num_envs
        elif isinstance(seed, int):
            worker_seeds = expand_maniskill_seed(seed, self.num_envs)
        else:
            worker_seeds = [int(value) for value in seed]
            if len(worker_seeds) != self.num_envs:
                raise ValueError("seed list length must equal num_envs")
        if seed is not None:
            self._has_seeded_reset = True

        for worker_id, connection in enumerate(self._connections):
            worker_options = {}
            for key, value in options.items():
                selected = _slice_batch(value, worker_id)
                if isinstance(selected, np.ndarray):
                    selected = torch.from_numpy(selected)
                worker_options[key] = selected
            connection.send(
                (
                    "reset",
                    {"seed": worker_seeds[worker_id], "options": worker_options},
                )
            )
        results = self._receive_all("reset")
        observations = _merge_worker_values([result[0] for result in results])
        infos = _merge_worker_values([result[1] for result in results])
        return observations, infos

    def chunk_step(self, chunk_actions):
        import numpy as np
        import torch

        if not hasattr(chunk_actions, "shape") or len(chunk_actions.shape) != 3:
            raise ValueError("chunk_actions must have shape [num_envs, chunk, action_dim]")
        if int(chunk_actions.shape[0]) != self.num_envs:
            raise ValueError(
                f"chunk action batch mismatch: expected {self.num_envs}, "
                f"got {int(chunk_actions.shape[0])}"
            )
        if int(chunk_actions.shape[2]) != int(self.single_action_shape[-1]):
            raise ValueError(
                f"action dimension mismatch: expected {self.single_action_shape[-1]}, "
                f"got {int(chunk_actions.shape[2])}"
            )
        if isinstance(chunk_actions, torch.Tensor):
            actions = chunk_actions.detach().cpu().numpy()
        else:
            actions = np.asarray(chunk_actions)
        for worker_id, connection in enumerate(self._connections):
            connection.send(("chunk_step", actions[worker_id : worker_id + 1]))
        results = self._receive_all("chunk_step")
        chunk_lengths = {len(result[0]) for result in results}
        info_lengths = {len(result[4]) for result in results}
        if len(chunk_lengths) != 1 or chunk_lengths != info_lengths:
            raise ModalMultiprocessEnvError("workers returned inconsistent chunk lengths")
        chunk_length = chunk_lengths.pop()
        obs_list = [
            _merge_worker_values([result[0][index] for result in results])
            for index in range(chunk_length)
        ]
        infos_list = [
            _merge_worker_values(
                [result[4][index] for result in results],
                allow_sparse_rlt_episode=True,
            )
            for index in range(chunk_length)
        ]
        return (
            obs_list,
            _merge_worker_values([result[1] for result in results]),
            _merge_worker_values([result[2] for result in results]),
            _merge_worker_values([result[3] for result in results]),
            infos_list,
        )

    def flush_video(self):
        return None

    def close(self, *, force: bool = False):
        if getattr(self, "_closed", True):
            return
        self._closed = True
        for connection in self._connections:
            try:
                connection.send(("close", None))
            except (BrokenPipeError, EOFError, OSError):
                pass
        if not force:
            for connection in self._connections:
                try:
                    if connection.poll(5):
                        connection.recv()
                except (BrokenPipeError, EOFError, OSError):
                    pass
        for process in self._processes:
            process.join(timeout=5)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
        for connection in self._connections:
            connection.close()
