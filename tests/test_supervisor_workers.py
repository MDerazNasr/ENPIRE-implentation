from __future__ import annotations

import unittest

from supervisor.canonical import fingerprint
from supervisor.workers import (
    FakeExperimentWorker,
    RunContract,
    WorkerError,
    WorkerScenario,
    WorkerState,
)


def run_contract(
    trial_id: str = "trial-2026",
    *,
    candidate_commit: str = "b" * 40,
    seed: int = 2026,
) -> RunContract:
    return RunContract.create(
        campaign_id="offline-campaign",
        trial_id=trial_id,
        arm_id="config-arm",
        parent_commit="a" * 40,
        candidate_commit=candidate_commit,
        rlinf_commit="c" * 40,
        config_hash="d" * 64,
        command_hash="e" * 64,
        seed=seed,
        reset_set_hash="f" * 64,
        evaluator_version="d1-rule-v1",
        max_wall_time_seconds=120,
        max_gpu_cost_usd="1.25",
    )


def scenario(state: WorkerState = WorkerState.COMPLETED) -> WorkerScenario:
    return WorkerScenario.create(
        terminal_state=state,
        started_at="2026-08-04T12:00:00Z",
        finished_at="2026-08-04T12:01:00Z",
        elapsed_seconds=60,
        metrics={"success_rate": 0.5, "successful_episode_length": 40},
        exit_code=0 if state == WorkerState.COMPLETED else 7,
        gpu_cost_usd="0.1",
    )


class FakeWorkerTests(unittest.TestCase):
    def test_run_contract_is_canonical_and_bounded(self) -> None:
        contract = run_contract()
        self.assertEqual(contract.max_gpu_cost_usd, "1.25")
        self.assertEqual(contract.fingerprint(), fingerprint(contract.to_dict()))
        with self.assertRaisesRegex(WorkerError, "seed"):
            run_contract(seed=-1)

    def test_successful_lifecycle_returns_strict_evidence(self) -> None:
        contract = run_contract()
        worker = FakeExperimentWorker(
            worker_id="fake-1", scenarios={contract.trial_id: scenario()}
        )
        prepared = worker.prepare(contract)
        self.assertEqual(prepared.state, WorkerState.PREPARED)
        self.assertEqual(worker.heartbeat(contract.trial_id).heartbeat_count, 1)
        terminal = worker.launch(contract.trial_id)
        evidence = worker.fetch_evidence(contract.trial_id)
        self.assertEqual(terminal.state, WorkerState.COMPLETED)
        self.assertEqual(terminal.evidence_hash, evidence.fingerprint())
        self.assertEqual(evidence.candidate_commit, contract.candidate_commit)

    def test_duplicate_prepare_launch_and_fetch_are_idempotent(self) -> None:
        contract = run_contract()
        worker = FakeExperimentWorker(
            worker_id="fake-1", scenarios={contract.trial_id: scenario()}
        )
        self.assertEqual(worker.prepare(contract), worker.prepare(contract))
        first = worker.launch(contract.trial_id)
        second = worker.launch(contract.trial_id)
        self.assertEqual(first, second)
        self.assertEqual(
            worker.fetch_evidence(contract.trial_id),
            worker.fetch_evidence(contract.trial_id),
        )

    def test_trial_id_cannot_be_rebound(self) -> None:
        contract = run_contract()
        worker = FakeExperimentWorker(
            worker_id="fake-1", scenarios={contract.trial_id: scenario()}
        )
        worker.prepare(contract)
        changed = run_contract(candidate_commit="9" * 40)
        with self.assertRaisesRegex(WorkerError, "different run contract"):
            worker.prepare(changed)

    def test_failed_lost_and_cancelled_runs_cannot_claim_success(self) -> None:
        failed = run_contract("failed-2026")
        lost = run_contract("lost-2026")
        cancelled = run_contract("cancelled-2026")
        worker = FakeExperimentWorker(
            worker_id="fake-1",
            scenarios={
                failed.trial_id: scenario(WorkerState.FAILED),
                lost.trial_id: scenario(WorkerState.LOST),
                cancelled.trial_id: scenario(),
            },
        )
        worker.prepare(failed)
        self.assertEqual(worker.launch(failed.trial_id).state, WorkerState.FAILED)
        self.assertEqual(worker.fetch_evidence(failed.trial_id).status.value, "failed")
        worker.prepare(lost)
        self.assertEqual(worker.launch(lost.trial_id).state, WorkerState.LOST)
        with self.assertRaisesRegex(WorkerError, "unavailable"):
            worker.fetch_evidence(lost.trial_id)
        worker.prepare(cancelled)
        self.assertEqual(worker.cancel(cancelled.trial_id).state, WorkerState.CANCELLED)
        with self.assertRaisesRegex(WorkerError, "unavailable"):
            worker.fetch_evidence(cancelled.trial_id)


if __name__ == "__main__":
    unittest.main()
