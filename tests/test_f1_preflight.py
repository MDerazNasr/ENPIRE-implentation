from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.run_f1_remote_acceptance import DEFAULT_PROFILE, build_preflight


class F1PreflightTests(unittest.TestCase):
    def test_clean_preflight_is_non_authorizing_and_binds_two_probes(self) -> None:
        with patch(
            "scripts.run_f1_remote_acceptance._git",
            side_effect=["", "c08da78a1cddbceac7dfef4af4d509eba7be3396"],
        ):
            payload = build_preflight(DEFAULT_PROFILE)
        self.assertEqual(payload["status"], "ready_for_explicit_approval")
        self.assertFalse(payload["execution_authorized"])
        self.assertFalse(payload["gpu_execution_authorized"])
        self.assertFalse(payload["promotion_authorized"])
        self.assertEqual(len(payload["contracts"]), 2)
        self.assertEqual(payload["deployment"]["app"], "enpire-f1-worker-rpc-v1")

    def test_rejects_runtime_hash_or_endpoint_drift(self) -> None:
        original = json.loads(DEFAULT_PROFILE.read_text())
        for mutation in ("runtime", "endpoint", "approval"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as directory:
                profile = copy.deepcopy(original)
                if mutation == "runtime":
                    profile["runtime_contract_sha256"] = "0" * 64
                elif mutation == "endpoint":
                    profile["app_name"] = "agent-chosen-app"
                else:
                    profile["approval"]["gpu_execution_authorized"] = True
                path = Path(directory) / "profile.json"
                path.write_text(json.dumps(profile))
                with self.assertRaises(ValueError):
                    build_preflight(path)

    def test_rejects_dirty_worktree(self) -> None:
        with patch(
            "scripts.run_f1_remote_acceptance._git",
            return_value=" M agent-controlled-file.py",
        ):
            with self.assertRaisesRegex(ValueError, "clean worktree"):
                build_preflight(DEFAULT_PROFILE)


if __name__ == "__main__":
    unittest.main()
