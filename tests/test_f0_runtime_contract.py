from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_f0_runtime_contract import DEFAULT_CONTRACT, verify


class F0RuntimeContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.contract = json.loads(DEFAULT_CONTRACT.read_text())

    def _verify_mutation(self, mutate) -> None:
        payload = copy.deepcopy(self.contract)
        mutate(payload)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "runtime-contract.json"
            path.write_text(json.dumps(payload))
            with self.assertRaises(ValueError):
                verify(path)

    def test_selected_contract_passes(self) -> None:
        result = verify()
        self.assertTrue(result["passed"])
        self.assertFalse(result["paid_execution_authorized"])

    def test_rejects_runtime_drift(self) -> None:
        self._verify_mutation(lambda value: value["container"].update(torch="2.9.0+cu128"))

    def test_rejects_control_candidate_runtime_split(self) -> None:
        self._verify_mutation(
            lambda value: value["gate"].update(candidate_runtime_contract_id="other-runtime")
        )

    def test_rejects_resume_without_sidecar(self) -> None:
        self._verify_mutation(
            lambda value: value["resume"].update(sidecar_required_for_any_resumed_run=False)
        )

    def test_rejects_input_hash_drift(self) -> None:
        self._verify_mutation(
            lambda value: value["inputs"]["stage1_actor"].update(sha256="0" * 64)
        )

    def test_rejects_paid_authorization(self) -> None:
        self._verify_mutation(
            lambda value: value["provider_lifecycle"].update(paid_execution_authorized=True)
        )


if __name__ == "__main__":
    unittest.main()
