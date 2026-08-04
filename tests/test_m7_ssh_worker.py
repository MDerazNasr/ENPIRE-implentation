from __future__ import annotations

import base64
import json
import sys
import unittest

from supervisor.ssh_worker import (
    RpcResult,
    SshEndpoint,
    SshExperimentWorker,
    SshWorkerError,
)
from supervisor.workers import RunContract, WorkerSnapshot, WorkerState
from tests.test_supervisor_workers import run_contract, scenario
from supervisor.workers import FakeExperimentWorker


class FixtureRpcExecutor:
    def __init__(self, contract: RunContract, *, worker_id: str = "ssh-worker") -> None:
        self.contract = contract
        self.worker = FakeExperimentWorker(
            worker_id=worker_id,
            scenarios={contract.trial_id: scenario()},
        )
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def run(self, argv, *, timeout_seconds):
        argv = tuple(argv)
        self.calls.append((argv, timeout_seconds))
        action = argv[-2]
        payload = json.loads(base64.urlsafe_b64decode(argv[-1]).decode())
        try:
            if action == "prepare":
                snapshot = self.worker.prepare(RunContract.from_dict(payload["contract"]))
                response = {"snapshot": snapshot.to_dict()}
            elif action == "heartbeat":
                response = {
                    "snapshot": self.worker.heartbeat(payload["trial_id"]).to_dict()
                }
            elif action == "launch":
                response = {"snapshot": self.worker.launch(payload["trial_id"]).to_dict()}
            elif action == "status":
                response = {"snapshot": self.worker.status(payload["trial_id"]).to_dict()}
            elif action == "cancel":
                response = {"snapshot": self.worker.cancel(payload["trial_id"]).to_dict()}
            elif action == "fetch_evidence":
                response = {
                    "evidence": self.worker.fetch_evidence(payload["trial_id"]).to_dict()
                }
            else:
                raise AssertionError(action)
        except Exception as error:
            return RpcResult(7, b"", str(error).encode())
        return RpcResult(0, json.dumps(response).encode(), b"")


class StaticExecutor:
    def __init__(self, result: RpcResult) -> None:
        self.result = result

    def run(self, argv, *, timeout_seconds):
        return self.result


class M7SshWorkerTests(unittest.TestCase):
    def endpoint(self, **overrides) -> SshEndpoint:
        values = {
            "worker_id": "ssh-worker",
            "host": "fixture@example.invalid",
            "remote_helper": "/opt/qualia/bin/m7-worker-rpc",
            "ssh_executable": __import__("pathlib").Path(sys.executable),
            "connect_timeout_seconds": 5,
            "rpc_timeout_seconds": 9,
        }
        values.update(overrides)
        return SshEndpoint.create(**values)

    def test_complete_mocked_ssh_lifecycle_uses_fixed_encoded_rpc(self) -> None:
        contract = run_contract("ssh-trial")
        executor = FixtureRpcExecutor(contract)
        worker = SshExperimentWorker(endpoint=self.endpoint(), executor=executor)
        self.assertEqual(worker.prepare(contract).state, WorkerState.PREPARED)
        self.assertEqual(worker.heartbeat(contract.trial_id).heartbeat_count, 1)
        terminal = worker.launch(contract.trial_id)
        evidence = worker.fetch_evidence(contract.trial_id)
        self.assertEqual(terminal.state, WorkerState.COMPLETED)
        self.assertEqual(terminal.evidence_hash, evidence.fingerprint())
        self.assertEqual(evidence.candidate_commit, contract.candidate_commit)
        self.assertEqual([item[0][-2] for item in executor.calls], [
            "prepare", "heartbeat", "launch", "fetch_evidence"
        ])
        prepare_payload = json.loads(
            base64.urlsafe_b64decode(executor.calls[0][0][-1]).decode()
        )
        self.assertEqual(
            prepare_payload["contract"]["candidate_commit"],
            contract.candidate_commit,
        )
        self.assertTrue(all(item[1] == 9 for item in executor.calls))
        self.assertNotIn("shell", " ".join(executor.calls[0][0]))

    def test_endpoint_rejects_option_injection_and_unsafe_remote_helper(self) -> None:
        cases = (
            {"host": "-oProxyCommand=bad"},
            {"host": "fixture host"},
            {"remote_helper": "relative/helper"},
            {"remote_helper": "/opt/../escape"},
        )
        for values in cases:
            with self.subTest(values=values):
                with self.assertRaises(SshWorkerError):
                    self.endpoint(**values)

    def test_worker_rejects_remote_failure_invalid_json_and_identity_spoof(self) -> None:
        contract = run_contract("ssh-invalid")
        cases = (
            (RpcResult(9, b"", b"remote failed"), "failed with 9"),
            (RpcResult(0, b"not-json", b""), "invalid JSON"),
            (
                RpcResult(
                    0,
                    json.dumps(
                        {
                            "snapshot": WorkerSnapshot(
                                worker_id="spoofed-worker",
                                trial_id=contract.trial_id,
                                state=WorkerState.PREPARED,
                                contract_hash=contract.fingerprint(),
                                heartbeat_count=0,
                                evidence_hash=None,
                            ).to_dict()
                        }
                    ).encode(),
                    b"",
                ),
                "identity mismatch",
            ),
        )
        for result, message in cases:
            with self.subTest(message=message):
                worker = SshExperimentWorker(
                    endpoint=self.endpoint(), executor=StaticExecutor(result)
                )
                with self.assertRaisesRegex(SshWorkerError, message):
                    worker.prepare(contract)

    def test_prepare_rejects_contract_hash_tampering(self) -> None:
        contract = run_contract("ssh-tampered")
        snapshot = WorkerSnapshot(
            worker_id="ssh-worker",
            trial_id=contract.trial_id,
            state=WorkerState.PREPARED,
            contract_hash="f" * 64,
            heartbeat_count=0,
            evidence_hash=None,
        )
        worker = SshExperimentWorker(
            endpoint=self.endpoint(),
            executor=StaticExecutor(
                RpcResult(
                    0,
                    json.dumps({"snapshot": snapshot.to_dict()}).encode(),
                    b"",
                )
            ),
        )
        with self.assertRaisesRegex(SshWorkerError, "does not match"):
            worker.prepare(contract)


if __name__ == "__main__":
    unittest.main()
