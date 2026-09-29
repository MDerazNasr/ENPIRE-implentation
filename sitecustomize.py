"""Strictly opt-in runtime hooks around the immutable RLinf checkout."""

from __future__ import annotations

import os


if os.environ.get("QUALIA_MODAL_MULTIPROCESS") == "1":
    import rlinf.envs as _rlinf_envs

    _original_get_env_cls = _rlinf_envs.get_env_cls

    def _qualia_get_env_cls(env_type: str, env_cfg=None):
        if env_type == "maniskill_rlt":
            if os.environ.get("QUALIA_E1_FROZEN_DEVELOPMENT") == "1":
                from envs.e1_frozen_development_env import (
                    E1FrozenDevelopmentManiskillRLTEnv,
                )

                return E1FrozenDevelopmentManiskillRLTEnv
            from envs.modal_multiprocess_rlt_env import (
                ModalMultiprocessManiskillRLTEnv,
            )

            return ModalMultiprocessManiskillRLTEnv
        return _original_get_env_cls(env_type, env_cfg)

    _rlinf_envs.get_env_cls = _qualia_get_env_cls


if os.environ.get("QUALIA_RLT_RESUME_STATE") == "1":
    from agent.rlt_resume_state import install_patch

    install_patch()


if os.environ.get("QUALIA_RLT_OBJECTIVE") == "1":
    from agent.rlt_objective_attachment import install_patch

    install_patch()
