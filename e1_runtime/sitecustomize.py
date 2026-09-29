"""E1-only startup hook for Ray worker processes.

This module is placed first on ``PYTHONPATH`` only by the bounded E1
evaluation launchers. Keeping it separate preserves the hash-pinned global
runtime hook used by the historical F0 qualification evidence.
"""

from __future__ import annotations

import os


if os.environ.get("QUALIA_E1_FROZEN_DEVELOPMENT") == "1":
    import rlinf.envs as _rlinf_envs

    _original_get_env_cls = _rlinf_envs.get_env_cls

    def _qualia_e1_get_env_cls(env_type: str, env_cfg=None):
        if env_type == "maniskill_rlt":
            from envs.e1_frozen_development_env import (
                E1FrozenDevelopmentManiskillRLTEnv,
            )

            return E1FrozenDevelopmentManiskillRLTEnv
        return _original_get_env_cls(env_type, env_cfg)

    _rlinf_envs.get_env_cls = _qualia_e1_get_env_cls
