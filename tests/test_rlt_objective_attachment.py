import hashlib
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.d1_config import RLINF_COMMIT
from agent.rlt_objective_attachment import (
    ATTACHMENT_MODE,
    RLTObjectiveAttachmentError,
    install_patch,
)
from supervisor.objective_validation import OBJECTIVE_CONTRACT_VERSION


DEFAULT_PLUGIN = (
    '"""Default objective."""\n\n'
    "def combine_actor_objective(actor_loss, bc_loss, bc_weight):\n"
    "    return actor_loss + bc_weight * bc_loss\n"
)


class RLTObjectiveAttachmentTests(unittest.TestCase):
    @staticmethod
    def _fake_rlinf_modules():
        class FakeForwardType:
            SAC = "sac"
            SAC_Q = "sac_q"
            CROSSQ_Q = "crossq_q"

        class FakeWorker:
            @staticmethod
            def timer(_label):
                return lambda function: function

        class FakeMixin:
            def forward_actor(self, batch):
                return batch

        modules = {}
        for name in (
            "rlinf",
            "rlinf.models",
            "rlinf.models.embodiment",
            "rlinf.workers",
            "rlinf.workers.actor",
        ):
            module = types.ModuleType(name)
            module.__path__ = []
            modules[name] = module
        base_policy = types.ModuleType("rlinf.models.embodiment.base_policy")
        base_policy.ForwardType = FakeForwardType
        scheduler = types.ModuleType("rlinf.scheduler")
        scheduler.Worker = FakeWorker
        worker_module = types.ModuleType(
            "rlinf.workers.actor.fsdp_rlt_ac_policy_worker"
        )
        worker_module.RLTACLossMixin = FakeMixin
        modules.update(
            {
                "rlinf.models.embodiment.base_policy": base_policy,
                "rlinf.scheduler": scheduler,
                "rlinf.workers.actor.fsdp_rlt_ac_policy_worker": worker_module,
            }
        )
        return modules, FakeMixin

    def test_missing_configuration_fails_before_importing_rlinf(self):
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(RLTObjectiveAttachmentError, "RLINF_HOME"):
                install_patch()

    def test_installer_is_verified_explicit_and_idempotent(self):
        modules, mixin = self._fake_rlinf_modules()
        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory) / "actor_objective.py"
            plugin.write_text(DEFAULT_PLUGIN)
            objective_hash = hashlib.sha256(plugin.read_bytes()).hexdigest()
            seam = {"rlinf_commit": RLINF_COMMIT}
            with patch.dict(sys.modules, modules), patch(
                "agent.rlt_objective_attachment.audit_rlinf_objective_seam",
                return_value=seam,
            ):
                first = install_patch(
                    rlinf_root=directory,
                    plugin_path=plugin,
                    objective_sha256=objective_hash,
                    contract_version=OBJECTIVE_CONTRACT_VERSION,
                )
                second = install_patch(
                    rlinf_root=directory,
                    plugin_path=plugin,
                    objective_sha256=objective_hash,
                    contract_version=OBJECTIVE_CONTRACT_VERSION,
                )
        self.assertTrue(first)
        self.assertFalse(second)
        marker = mixin._qualia_objective_attachment
        self.assertEqual(marker["attachment_mode"], ATTACHMENT_MODE)
        self.assertEqual(marker["objective_sha256"], objective_hash)
        self.assertEqual(marker["installed_target"], "RLTACLossMixin.forward_actor")

    def test_plugin_hash_and_contract_drift_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            plugin = Path(directory) / "actor_objective.py"
            plugin.write_text(DEFAULT_PLUGIN)
            seam = {"rlinf_commit": RLINF_COMMIT}
            with patch(
                "agent.rlt_objective_attachment.audit_rlinf_objective_seam",
                return_value=seam,
            ):
                with self.assertRaisesRegex(RLTObjectiveAttachmentError, "unsupported"):
                    install_patch(
                        rlinf_root=directory,
                        plugin_path=plugin,
                        objective_sha256="0" * 64,
                        contract_version="wrong-contract",
                    )
                with self.assertRaisesRegex(RLTObjectiveAttachmentError, "hash mismatch"):
                    install_patch(
                        rlinf_root=directory,
                        plugin_path=plugin,
                        objective_sha256="0" * 64,
                        contract_version=OBJECTIVE_CONTRACT_VERSION,
                    )


if __name__ == "__main__":
    unittest.main()
