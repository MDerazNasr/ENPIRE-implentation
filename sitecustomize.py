"""Opt-in runtime hook for the provisional Modal multiprocess environment."""

from __future__ import annotations

import os


if os.environ.get("QUALIA_MODAL_MULTIPROCESS") == "1":
    import rlinf.envs as _rlinf_envs

    _original_get_env_cls = _rlinf_envs.get_env_cls

    def _qualia_get_env_cls(env_type: str, env_cfg=None):
        if env_type == "maniskill_rlt":
            from envs.modal_multiprocess_rlt_env import (
                ModalMultiprocessManiskillRLTEnv,
            )

            return ModalMultiprocessManiskillRLTEnv
        return _original_get_env_cls(env_type, env_cfg)

    _rlinf_envs.get_env_cls = _qualia_get_env_cls
