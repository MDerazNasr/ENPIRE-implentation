from __future__ import annotations

import base64
import copy
import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from supervisor.canonical import fingerprint
from supervisor.contracts import ArtifactRef, TrialEvidence
from supervisor.modal_worker_rpc import (
    MAX_RPC_OUTPUT_BYTES,
    FixedModalRpcExecutor,
    ModalExperimentWorker,
    ModalRpcResult,
    ModalWorkerRpcError,
    WorkerRpcRequest,
)
from supervisor.workers import RunContract, WorkerSnapshot, WorkerState
from tests.test_supervisor_workers import run_contract


WORKER_ID = "modal-rtx-pro-6000-f1"
RUNTIME_ID = "enpire-matched-scientific-runtime-v1"
RUNTIME_HASH = "a" * 64
ARTIFACT_CONTENT = b'{"gpu_peak_utilization_percent":87}\n'


def evidence(contract: RunContract) -> TrialEvidence:
    artifact = ArtifactRef.from_dict(
        {
            "artifact_id": "gpu-telemetry",
            "kind": "gpu-telemetry",
            "uri": f"worker://{contract.trial_id}/gpu-telemetry",
            "sha256": hashlib.sha256(ARTIFACT_CONTENT).hexdigest(),
            "size_bytes": len(ARTIFACT_CONTENT),
        },
        "fixture artifact",
    )
    return TrialEvidence.from_dict(
        {
            "schema_version": 1,
            "campaign_id": contract.campaign_id,
            "trial_id": contract.trial_id,
            "arm_id": contract.arm_id,
            "parent_commit": contract.parent_commit,
            "candidate_commit": contract.candidate_commit,
            "rlinf_commit": contract.rlinf_commit,
            "config_hash": contract.config_hash,
            "command_hash": contract.command_hash,
            "seed": contract.seed,
            "reset_set_hash": contract.reset_set_hash,
            "evaluator_version": contract.evaluator_version,
            "started_at": "2026-09-03T12:00:00Z",
            "finished_at": "2026-09-03T12:00:15Z",
            "status": "complete",
            "exit_code": 0,
            "elapsed_seconds": 15,
            "gpu_cost_usd": "0.01263",
            "llm_cost_usd": "0",
            "metrics": {"gpu_peak_utilization_percent": 87},
            "metric_errors": [],
            "artifacts": [artifact.to_dict()],
        }
    )


class FixtureModalExecutor:
    def __init__(self, *, worker_id: str = WORKER_ID) -> None:
        self.worker_id = worker_id
        self.contracts: dict[str, RunContract] = {}
        self.states: dict[str, WorkerState] = {}
        self.heartbeats: dict[str, int] = {}
        self.calls: list[WorkerRpcRequest] = []
        self.complete_on_status = True
        self.corrupt_artifact = False
        self.response_request_id: str | None = None

    def snapshot(self, trial_id: str) -> WorkerSnapshot:
        contract = self.contracts[trial_id]
        terminal = self.states[trial_id] == WorkerState.COMPLETED
        return WorkerSnapshot(
            worker_id=self.worker_id,
            trial_id=trial_id,
            state=self.states[trial_id],
            contract_hash=contract.fingerprint(),
            heartbeat_count=self.heartbeats[trial_id],
            evidence_hash=evidence(contract).fingerprint() if terminal else None,
        )

    def run(self, request: WorkerRpcRequest, *, timeout_seconds: int) -> ModalRpcResult:
        self.calls.append(request)
        try:
            parsed = WorkerRpcRequest.from_dict(request.to_dict())
            payload = parsed.payload
            if parsed.action == "prepare":
                contract = RunContract.from_dict(payload["contract"])
                existing = self.contracts.get(contract.trial_id)
                if existing and existing.fingerprint() != contract.fingerprint():
                    raise ValueError("conflicting contract")
                self.contracts[contract.trial_id] = contract
                self.states.setdefault(contract.trial_id, WorkerState.PREPARED)
                self.heartbeats.setdefault(contract.trial_id, 0)
                result = {"snapshot": self.snapshot(contract.trial_id).to_dict()}
            elif parsed.action in {"launch", "status", "heartbeat", "cancel"}:
                trial_id = payload["trial_id"]
                if parsed.action == "launch" and self.states[trial_id] == WorkerState.PREPARED:
                    self.states[trial_id] = WorkerState.RUNNING
                elif (
                    parsed.action == "status"
                    and self.states[trial_id] == WorkerState.RUNNING
                    and self.complete_on_status
                ):
                    self.states[trial_id] = WorkerState.COMPLETED
                elif parsed.action == "heartbeat" and self.states[trial_id] in {
                    WorkerState.PREPARED,
                    WorkerState.RUNNING,
                }:
                    self.heartbeats[trial_id] += 1
                elif parsed.action == "cancel" and self.states[trial_id] in {
                    WorkerState.PREPARED,
                    WorkerState.RUNNING,
                }:
                    self.states[trial_id] = WorkerState.CANCELLED
                result = {"snapshot": self.snapshot(trial_id).to_dict()}
            elif parsed.action == "fetch_evidence":
                if self.states[payload["trial_id"]] not in {
                    WorkerState.COMPLETED,
                    WorkerState.FAILED,
                }:
                    raise ValueError("terminal evidence is unavailable")
                result = {
                    "evidence": evidence(self.contracts[payload["trial_id"]]).to_dict()
                }
            elif parsed.action == "fetch_artifact":
                raw = (
                    bytes([ARTIFACT_CONTENT[0] ^ 1]) + ARTIFACT_CONTENT[1:]
                    if self.corrupt_artifact
                    else ARTIFACT_CONTENT
                )
                offset = payload["offset"]
                length = payload["length"]
                result = {
                    "artifact_chunk": {
                        "artifact_id": payload["artifact_id"],
                        "offset": offset,
                        "total_size_bytes": len(ARTIFACT_CONTENT),
                        "sha256": hashlib.sha256(ARTIFACT_CONTENT).hexdigest(),
                        "data_b64": base64.b64encode(raw[offset : offset + length]).decode(),
                    }
                }
            else:
                raise AssertionError(parsed.action)
            envelope = {
                "schema_version": 1,
                "request_id": self.response_request_id or request.request_id,
                "result": result,
            }
            return ModalRpcResult(0, json.dumps(envelope).encode(), b"")
        except Exception as error:
            return ModalRpcResult(7, b"", str(error).encode())


def worker(executor, *, recovered_contracts=()) -> ModalExperimentWorker:
    return ModalExperimentWorker(
        worker_id=WORKER_ID,
        runtime_contract_id=RUNTIME_ID,
        runtime_contract_sha256=RUNTIME_HASH,
        executor=executor,
        rpc_timeout_seconds=17,
        recovered_contracts=recovered_contracts,
    )


class F1ModalWorkerRpcTests(unittest.TestCase):
    def test_fixed_executor_preserves_virtual_environment_python_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            interpreter = root / "modal-python"
            interpreter.symlink_to("/bin/sh")
            client = root / "client.py"
            client.write_text("pass\n")
            executor = FixedModalRpcExecutor.create(
                python_executable=interpreter,
                client_script=client,
                expected_profile="fixture-profile",
            )
            self.assertEqual(
                executor.python_executable,
                Path(os.path.abspath(os.fspath(interpreter))),
            )
            self.assertNotEqual(executor.python_executable, interpreter.resolve())

    def test_complete_lifecycle_and_verified_artifact_transfer(self) -> None:
        contract = run_contract("f1-live-fixture")
        executor = FixtureModalExecutor()
        client = worker(executor)
        self.assertEqual(client.prepare(contract).state, WorkerState.PREPARED)
        self.assertEqual(client.heartbeat(contract.trial_id).heartbeat_count, 1)
        self.assertEqual(client.launch(contract.trial_id).state, WorkerState.RUNNING)
        self.assertEqual(client.status(contract.trial_id).state, WorkerState.COMPLETED)
        result = client.fetch_evidence(contract.trial_id)
        artifact = result.artifacts[0]
        self.assertEqual(client.fetch_artifact(contract.trial_id, artifact), ARTIFACT_CONTENT)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gpu-telemetry.json"
            self.assertEqual(
                client.materialize_artifact(contract.trial_id, artifact, path),
                path.resolve(),
            )
            self.assertEqual(path.read_bytes(), ARTIFACT_CONTENT)
        self.assertEqual(
            [item.action for item in executor.calls[:6]],
            ["prepare", "heartbeat", "launch", "status", "fetch_evidence", "fetch_artifact"],
        )
        self.assertFalse(
            any(
                key in {"command", "argv", "shell", "host"}
                for request in executor.calls
                for key in request.payload
            )
        )

    def test_active_cancel_is_terminal_and_late_status_stays_cancelled(self) -> None:
        contract = run_contract("f1-cancel-fixture")
        executor = FixtureModalExecutor()
        executor.complete_on_status = False
        client = worker(executor)
        client.prepare(contract)
        client.launch(contract.trial_id)
        self.assertEqual(client.cancel(contract.trial_id).state, WorkerState.CANCELLED)
        self.assertEqual(client.status(contract.trial_id).state, WorkerState.CANCELLED)
        with self.assertRaises(ModalWorkerRpcError):
            client.fetch_evidence(contract.trial_id)

    def test_coordinator_restart_rebinds_exact_durable_contract(self) -> None:
        contract = run_contract("f1-restart-fixture")
        executor = FixtureModalExecutor()
        executor.complete_on_status = False
        original = worker(executor)
        original.prepare(contract)
        original.launch(contract.trial_id)
        restarted = worker(executor, recovered_contracts=(contract,))
        self.assertEqual(restarted.heartbeat(contract.trial_id).state, WorkerState.RUNNING)
        conflicting = copy.deepcopy(contract.to_dict())
        conflicting["candidate_commit"] = "f" * 40
        with self.assertRaises(ModalWorkerRpcError):
            worker(
                executor,
                recovered_contracts=(contract, RunContract.from_dict(conflicting)),
            )

    def test_rejects_unknown_action_and_request_or_worker_spoofing(self) -> None:
        with self.assertRaises(ModalWorkerRpcError):
            WorkerRpcRequest.create(
                worker_id=WORKER_ID,
                runtime_contract_id=RUNTIME_ID,
                runtime_contract_sha256=RUNTIME_HASH,
                action="shell",
                payload={},
            )
        contract = run_contract("f1-spoof-fixture")
        executor = FixtureModalExecutor(worker_id="spoofed-worker")
        with self.assertRaisesRegex(ModalWorkerRpcError, "identity mismatch"):
            worker(executor).prepare(contract)
        executor = FixtureModalExecutor()
        executor.response_request_id = "0" * 64
        with self.assertRaisesRegex(ModalWorkerRpcError, "request identity"):
            worker(executor).prepare(contract)

    def test_rejects_artifact_corruption_and_oversized_rpc_output(self) -> None:
        contract = run_contract("f1-artifact-fixture")
        executor = FixtureModalExecutor()
        client = worker(executor)
        client.prepare(contract)
        client.launch(contract.trial_id)
        client.status(contract.trial_id)
        artifact = client.fetch_evidence(contract.trial_id).artifacts[0]
        executor.corrupt_artifact = True
        with self.assertRaisesRegex(ModalWorkerRpcError, "digest mismatch|size mismatch"):
            client.fetch_artifact(contract.trial_id, artifact)

        class OversizedExecutor:
            def run(self, request, *, timeout_seconds):
                return ModalRpcResult(0, b"x" * (MAX_RPC_OUTPUT_BYTES + 1), b"")

        with self.assertRaisesRegex(ModalWorkerRpcError, "exceeded"):
            worker(OversizedExecutor()).prepare(contract)

    def test_request_hash_binds_runtime_action_and_payload(self) -> None:
        request = WorkerRpcRequest.create(
            worker_id=WORKER_ID,
            runtime_contract_id=RUNTIME_ID,
            runtime_contract_sha256=RUNTIME_HASH,
            action="status",
            payload={"trial_id": "fixture", "contract_hash": "b" * 64},
        )
        tampered = request.to_dict()
        tampered["action"] = "cancel"
        with self.assertRaisesRegex(ModalWorkerRpcError, "hash mismatch"):
            WorkerRpcRequest.from_dict(tampered)
        self.assertEqual(request.request_id, fingerprint({
            "schema_version": 1,
            "worker_id": WORKER_ID,
            "runtime_contract_id": RUNTIME_ID,
            "runtime_contract_sha256": RUNTIME_HASH,
            "action": "status",
            "payload": {"trial_id": "fixture", "contract_hash": "b" * 64},
        }))

    def test_deployed_helper_source_has_no_agent_command_field(self) -> None:
        source = (Path(__file__).resolve().parents[1] / "modal_f1_worker.py").read_text()
        self.assertNotIn('payload["command"]', source)
        self.assertNotIn('payload["argv"]', source)
        self.assertIn("bounded_gpu_probe.spawn", source)
        self.assertIn("terminate_containers=True", source)
        self.assertIn('IMAGE_ENVIRONMENT = {"PYTHONPATH": PROJECT_ROOT}', source)
        self.assertEqual(source.count(".env(IMAGE_ENVIRONMENT)"), 2)
        self.assertIn("def _install_f1_supervisor_namespace()", source)
        self.assertEqual(source.count("_install_f1_supervisor_namespace()"), 3)
        self.assertNotIn('.add_local_dir("agent"', source)


if __name__ == "__main__":
    unittest.main()
