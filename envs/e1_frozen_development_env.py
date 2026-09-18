"""E1-only adapter that consumes the frozen development seeds exactly once."""

from __future__ import annotations

import json
import os

from envs.frozen_development_resets import FrozenDevelopmentResetSchedule
from envs.modal_multiprocess_rlt_env import (
    ModalMultiprocessEnvError,
    ModalMultiprocessManiskillRLTEnv,
)


DEVELOPMENT_RESET_PATH_ENV = "QUALIA_DEVELOPMENT_RESET_PATH"
DEVELOPMENT_RESET_SHA256_ENV = "QUALIA_DEVELOPMENT_RESET_SHA256"


class E1FrozenDevelopmentManiskillRLTEnv(ModalMultiprocessManiskillRLTEnv):
    """Run each ordered development episode seed once and then fail closed."""

    def __init__(self, cfg, num_envs, *args, **kwargs):
        if not bool(cfg.use_fixed_reset_state_ids):
            raise ModalMultiprocessEnvError(
                "frozen development resets require use_fixed_reset_state_ids=true"
            )
        reset_path = os.environ.get(DEVELOPMENT_RESET_PATH_ENV)
        reset_sha256 = os.environ.get(DEVELOPMENT_RESET_SHA256_ENV)
        if not reset_path or not reset_sha256:
            raise ModalMultiprocessEnvError(
                "both frozen development reset path and fingerprint are required"
            )
        self._development_resets = FrozenDevelopmentResetSchedule.load(
            reset_path,
            expected_sha256=reset_sha256,
            batch_size=int(num_envs),
        )
        self._development_seed_batch: list[int] | None = None
        super().__init__(cfg, num_envs, *args, **kwargs)

    def update_reset_state_ids(self, *, propagate: bool = True):
        super().update_reset_state_ids(propagate=propagate)
        if self._development_resets.complete:
            self._development_seed_batch = None
            print(
                "QUALIA_DEVELOPMENT_RESET_COMPLETE="
                + json.dumps(
                    {
                        "count": self._development_resets.consumed,
                        "reset_set_sha256": self._development_resets.fingerprint,
                    },
                    sort_keys=True,
                ),
                flush=True,
            )
        else:
            self._development_seed_batch = self._development_resets.next_batch()

    def reset(self, *, seed=None, options=None):
        if seed is not None or options is not None:
            raise ModalMultiprocessEnvError(
                "external reset overrides are forbidden with frozen development resets"
            )
        if self._development_seed_batch is None:
            raise ModalMultiprocessEnvError(
                "frozen development reset schedule is exhausted"
            )
        return super().reset(
            seed=list(self._development_seed_batch),
            options={"episode_id": self.reset_state_ids},
        )


def install_e1_frozen_development_adapter() -> None:
    """Replace only the active ManiSkill RLT lookup for this evaluator process."""

    import rlinf.envs as rlinf_envs

    previous_get_env_cls = rlinf_envs.get_env_cls

    def get_env_cls(env_type: str, env_cfg=None):
        if env_type == "maniskill_rlt":
            return E1FrozenDevelopmentManiskillRLTEnv
        return previous_get_env_cls(env_type, env_cfg)

    rlinf_envs.get_env_cls = get_env_cls
