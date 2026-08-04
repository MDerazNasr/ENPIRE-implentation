from __future__ import annotations

import json
import tempfile
import threading
import unittest
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from supervisor.contracts import CampaignSpec
from supervisor.scheduler import (
    CompletionEnvelope,
    DispatchState,
    DurableScheduler,
    SchedulerError,
    SchedulerStateStore,
    WorkerAvailability,
    WorkerCapabilities,
    cancel_assignment,
    execute_assignments,
    recover_active_assignments,
)
from supervisor.workers import (
    FakeExperimentWorker,
    RunContract,
    WorkerScenario,
    WorkerState,
)
from tests.test_supervisor_proposals import config_campaign_data


NOW = datetime(2026, 8, 4, 12, tzinfo=timezone.utc)


def campaign(*, max_trials: int = 8, max_concurrency: int = 2) -> CampaignSpec:
    raw = config_campaign_data()
    raw["campaign_id"] = "m7-scheduler-fixture"
    raw["max_concurrency"] = max_concurrency
    raw["budget"].update(
        {
            "max_trials": max_trials,
            "max_wall_time_seconds": 2000,
            "max_gpu_cost_usd": "10",
        }
    )
    return CampaignSpec.from_dict(raw)


def contract(spec: CampaignSpec, trial_id: str, *, seed: int) -> RunContract:
    return RunContract.create(
        campaign_id=spec.campaign_id,
        trial_id=trial_id,
        arm_id="config-arm",
        parent_commit="a" * 40,
        candidate_commit=("b" if seed % 2 else "c") * 40,
        rlinf_commit=spec.rlinf_commit,
        config_hash="d" * 64,
        command_hash=("e" if seed % 2 else "f") * 64,
        seed=seed,
        reset_set_hash=spec.reset_set_hash,
        evaluator_version=spec.evaluator_version,
        max_wall_time_seconds=100,
        max_gpu_cost_usd="0.2",
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


class ConcurrencyProbe:
    def __init__(self, parties: int) -> None:
        self.barrier = threading.Barrier(parties)
        self.lock = threading.Lock()
        self.active = 0
        self.maximum = 0

    def enter(self) -> None:
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
        try:
            self.barrier.wait(timeout=3)
        finally:
            with self.lock:
                self.active -= 1


class ProbedWorker:
    def __init__(self, delegate: FakeExperimentWorker, probe: ConcurrencyProbe) -> None:
        self.delegate = delegate
        self.probe = probe
        self.worker_id = delegate.worker_id

    def prepare(self, item):
        return self.delegate.prepare(item)

    def heartbeat(self, trial_id):
        return self.delegate.heartbeat(trial_id)

    def launch(self, trial_id):
        self.probe.enter()
        return self.delegate.launch(trial_id)

    def status(self, trial_id):
        return self.delegate.status(trial_id)

    def cancel(self, trial_id):
        return self.delegate.cancel(trial_id)

    def fetch_evidence(self, trial_id):
        return self.delegate.fetch_evidence(trial_id)


class RecoverableWorker:
    def __init__(self, delegate: FakeExperimentWorker) -> None:
        self.delegate = delegate
        self.worker_id = delegate.worker_id
        self.contract = None
        self.state = WorkerState.NEW
        self.heartbeat_count = 0
        self.terminal = None

    def prepare(self, item):
        self.contract = item
        self.delegate.prepare(item)
        self.state = WorkerState.PREPARED
        return self.status(item.trial_id)

    def start(self):
        self.state = WorkerState.RUNNING

    def finish(self):
        self.terminal = self.delegate.launch(self.contract.trial_id)
        self.state = self.terminal.state

    def status(self, trial_id):
        if self.terminal is not None:
            return self.terminal
        from supervisor.workers import WorkerSnapshot

        return WorkerSnapshot(
            worker_id=self.worker_id,
            trial_id=trial_id,
            state=self.state,
            contract_hash=self.contract.fingerprint(),
            heartbeat_count=self.heartbeat_count,
            evidence_hash=None,
        )

    def heartbeat(self, trial_id):
        self.heartbeat_count += 1
        return self.status(trial_id)

    def launch(self, trial_id):
        self.start()
        return self.status(trial_id)

    def cancel(self, trial_id):
        self.state = WorkerState.CANCELLED
        return self.status(trial_id)

    def fetch_evidence(self, trial_id):
        return self.delegate.fetch_evidence(trial_id)


class M7SchedulerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.campaign = campaign()
        self.store = SchedulerStateStore(self.root / "scheduler.json")
        self.scheduler = DurableScheduler(campaign=self.campaign, store=self.store)

    @staticmethod
    def capabilities(worker_id: str, *, memory: int = 24) -> WorkerCapabilities:
        return WorkerCapabilities.create(
            worker_id=worker_id,
            transport="local_fixture",
            gpu_name="fixture-gpu",
            gpu_memory_gb=memory,
            supported_modes=("fixture",),
        )

    def register_pair(self) -> None:
        self.scheduler.register_worker(self.capabilities("worker-a"), at=NOW)
        self.scheduler.register_worker(self.capabilities("worker-b"), at=NOW)

    def enqueue(self, trial_id: str, seed: int, *, memory: int = 0) -> RunContract:
        item = contract(self.campaign, trial_id, seed=seed)
        self.scheduler.enqueue(
            item,
            required_mode="fixture",
            required_gpu_memory_gb=memory,
            at=NOW,
        )
        return item

    def test_deterministic_two_worker_dispatch_survives_restart_without_duplicates(self) -> None:
        self.register_pair()
        first = self.enqueue("trial-alpha", 1)
        second = self.enqueue("trial-beta", 2)
        dispatched = self.scheduler.dispatch(at=NOW, lease_ttl_seconds=60)
        self.assertEqual(
            [(item.contract.trial_id, item.lease.worker_id) for item in dispatched.assignments],
            [(first.trial_id, "worker-a"), (second.trial_id, "worker-b")],
        )
        restarted = DurableScheduler(campaign=self.campaign, store=self.store)
        self.assertEqual(
            [item.lease.lease_id for item in restarted.active_assignments()],
            [item.lease.lease_id for item in dispatched.assignments],
        )
        replay = restarted.dispatch(at=NOW + timedelta(seconds=1), lease_ttl_seconds=60)
        self.assertFalse(replay.assignments)
        self.assertEqual(len(restarted.snapshot().leases), 2)

    def test_assignments_actually_execute_concurrently_and_reconcile_idempotently(self) -> None:
        self.register_pair()
        first = self.enqueue("trial-alpha", 1)
        second = self.enqueue("trial-beta", 2)
        assignments = self.scheduler.dispatch(
            at=NOW, lease_ttl_seconds=60
        ).assignments
        probe = ConcurrencyProbe(2)
        workers = {
            "worker-a": ProbedWorker(
                FakeExperimentWorker(
                    worker_id="worker-a", scenarios={first.trial_id: scenario()}
                ),
                probe,
            ),
            "worker-b": ProbedWorker(
                FakeExperimentWorker(
                    worker_id="worker-b", scenarios={second.trial_id: scenario()}
                ),
                probe,
            ),
        }
        completions = execute_assignments(
            assignments, workers=workers, max_workers=2
        )
        self.assertEqual(probe.maximum, 2)
        for item in completions:
            result = self.scheduler.reconcile(
                item, at=NOW + timedelta(seconds=10)
            )
            self.assertEqual(result.state, DispatchState.COMPLETED)
        generation = self.scheduler.snapshot().generation
        duplicate = self.scheduler.reconcile(
            completions[0], at=NOW + timedelta(seconds=11)
        )
        self.assertTrue(duplicate.accepted)
        self.assertEqual(self.scheduler.snapshot().generation, generation)
        self.assertTrue(
            all(
                item.state == DispatchState.COMPLETED
                for item in self.scheduler.snapshot().trials
            )
        )

    def test_lost_worker_requeues_on_restart_and_late_completion_is_rejected(self) -> None:
        self.register_pair()
        run = self.enqueue("trial-retry", 1)
        first = self.scheduler.dispatch(at=NOW, lease_ttl_seconds=60).assignments[0]
        lost_worker = FakeExperimentWorker(
            worker_id="worker-a",
            scenarios={run.trial_id: scenario(WorkerState.LOST)},
        )
        lost = execute_assignments(
            (first,), workers={"worker-a": lost_worker}, max_workers=1
        )[0]
        result = self.scheduler.reconcile(lost, at=NOW + timedelta(seconds=5))
        self.assertTrue(result.requeued)
        self.assertEqual(result.state, DispatchState.QUEUED)

        restarted = DurableScheduler(campaign=self.campaign, store=self.store)
        second = restarted.dispatch(
            at=NOW + timedelta(seconds=6), lease_ttl_seconds=60
        ).assignments[0]
        self.assertEqual(second.lease.worker_id, "worker-b")
        self.assertEqual(second.lease.attempt, 2)
        replacement = FakeExperimentWorker(
            worker_id="worker-b", scenarios={run.trial_id: scenario()}
        )
        completed = execute_assignments(
            (second,), workers={"worker-b": replacement}, max_workers=1
        )[0]
        restarted.reconcile(completed, at=NOW + timedelta(seconds=10))
        stale = replace(
            completed,
            lease_id=first.lease.lease_id,
            lease_token=first.lease.authorization_token(),
            worker_id="worker-a",
        )
        with self.assertRaisesRegex(SchedulerError, "stale lease"):
            restarted.reconcile(stale, at=NOW + timedelta(seconds=11))
        trial = restarted.snapshot().trials[0]
        self.assertEqual(trial.state, DispatchState.COMPLETED)
        self.assertEqual(trial.evidence.candidate_commit, run.candidate_commit)

    def test_restart_recovery_renews_live_lease_then_reconciles_terminal_worker(self) -> None:
        self.register_pair()
        run = self.enqueue("trial-recover", 1)
        assignment = self.scheduler.dispatch(at=NOW, lease_ttl_seconds=20).assignments[0]
        worker = RecoverableWorker(
            FakeExperimentWorker(
                worker_id=assignment.lease.worker_id,
                scenarios={run.trial_id: scenario()},
            )
        )
        worker.prepare(run)
        worker.start()
        restarted = DurableScheduler(campaign=self.campaign, store=self.store)
        live = recover_active_assignments(
            restarted,
            workers={worker.worker_id: worker},
            at=NOW + timedelta(seconds=5),
            lease_ttl_seconds=30,
        )
        self.assertEqual(live.renewed_lease_ids, (assignment.lease.lease_id,))
        self.assertFalse(live.reconciled)
        renewed = restarted.active_assignments()[0].lease
        self.assertEqual(renewed.expires_at, "2026-08-04T12:00:35Z")
        worker.finish()
        terminal = recover_active_assignments(
            restarted,
            workers={worker.worker_id: worker},
            at=NOW + timedelta(seconds=10),
            lease_ttl_seconds=30,
        )
        self.assertEqual(terminal.reconciled[0].state, DispatchState.COMPLETED)
        self.assertFalse(restarted.active_assignments())

    def test_lease_expiration_requeues_and_offlines_worker(self) -> None:
        self.register_pair()
        self.enqueue("trial-expiry", 1)
        assignment = self.scheduler.dispatch(at=NOW, lease_ttl_seconds=5).assignments[0]
        expired = self.scheduler.expire_leases(at=NOW + timedelta(seconds=5))
        self.assertEqual(expired, (assignment.lease.lease_id,))
        state = self.scheduler.snapshot()
        self.assertEqual(state.trials[0].state, DispatchState.QUEUED)
        worker = next(
            item
            for item in state.workers
            if item.capabilities.worker_id == assignment.lease.worker_id
        )
        self.assertEqual(worker.availability, WorkerAvailability.OFFLINE)
        self.scheduler.heartbeat_worker(worker.capabilities.worker_id, at=NOW + timedelta(seconds=6))
        retry = self.scheduler.dispatch(
            at=NOW + timedelta(seconds=7), lease_ttl_seconds=5
        ).assignments[0]
        self.assertEqual(retry.lease.attempt, 2)

    def test_cancellation_revokes_authority_before_transport_cancel(self) -> None:
        self.register_pair()
        run = self.enqueue("trial-cancel", 1)
        assignment = self.scheduler.dispatch(at=NOW, lease_ttl_seconds=60).assignments[0]
        worker = FakeExperimentWorker(
            worker_id=assignment.lease.worker_id,
            scenarios={run.trial_id: scenario()},
        )
        worker.prepare(run)
        order = self.scheduler.cancel_trial(
            run.trial_id, at=NOW + timedelta(seconds=2)
        )
        self.assertEqual(order, assignment)
        snapshot = cancel_assignment(order, workers={worker.worker_id: worker})
        self.assertEqual(snapshot.state, WorkerState.CANCELLED)
        self.assertEqual(
            self.scheduler.snapshot().trials[0].state, DispatchState.CANCELLED
        )
        late = CompletionEnvelope(
            lease_id=assignment.lease.lease_id,
            lease_token=assignment.lease.authorization_token(),
            worker_id=worker.worker_id,
            trial_id=run.trial_id,
            contract_hash=run.fingerprint(),
            terminal_state=WorkerState.CANCELLED,
            snapshot=snapshot,
            evidence=None,
        )
        with self.assertRaisesRegex(SchedulerError, "stale lease"):
            self.scheduler.reconcile(late, at=NOW + timedelta(seconds=3))

    def test_capability_and_budget_limits_leave_work_queued(self) -> None:
        limited_campaign = campaign(max_trials=1)
        scheduler = DurableScheduler(
            campaign=limited_campaign,
            store=SchedulerStateStore(self.root / "limited.json"),
        )
        scheduler.register_worker(self.capabilities("worker-a"), at=NOW)
        for index, memory in ((1, 0), (2, 48)):
            scheduler.enqueue(
                contract(limited_campaign, f"trial-{index}", seed=index),
                required_mode="fixture",
                required_gpu_memory_gb=memory,
                at=NOW,
            )
        result = scheduler.dispatch(at=NOW, lease_ttl_seconds=30)
        self.assertEqual(len(result.assignments), 1)
        self.assertTrue(any("budget exhausted" in item for item in result.blocked))
        self.assertEqual(
            [item.state for item in scheduler.snapshot().trials].count(
                DispatchState.QUEUED
            ),
            1,
        )

    def test_tampered_evidence_cannot_cross_contaminate_a_trial(self) -> None:
        self.register_pair()
        run = self.enqueue("trial-bound", 1)
        assignment = self.scheduler.dispatch(at=NOW, lease_ttl_seconds=60).assignments[0]
        worker = FakeExperimentWorker(
            worker_id=assignment.lease.worker_id,
            scenarios={run.trial_id: scenario()},
        )
        completion = execute_assignments(
            (assignment,), workers={worker.worker_id: worker}, max_workers=1
        )[0]
        raw = completion.evidence.to_dict()
        raw["candidate_commit"] = "9" * 40
        forged_evidence = type(completion.evidence).from_dict(raw)
        forged_snapshot = replace(
            completion.snapshot, evidence_hash=forged_evidence.fingerprint()
        )
        forged = replace(
            completion, evidence=forged_evidence, snapshot=forged_snapshot
        )
        with self.assertRaisesRegex(SchedulerError, "candidate_commit mismatch"):
            self.scheduler.reconcile(forged, at=NOW + timedelta(seconds=5))
        for field, value, message in (
            ("gpu_cost_usd", "0.3", "GPU-cost cap"),
            ("elapsed_seconds", 101, "wall-time cap"),
        ):
            with self.subTest(field=field):
                over_cap = completion.evidence.to_dict()
                over_cap[field] = value
                invalid = type(completion.evidence).from_dict(over_cap)
                invalid_completion = replace(
                    completion,
                    evidence=invalid,
                    snapshot=replace(
                        completion.snapshot, evidence_hash=invalid.fingerprint()
                    ),
                )
                with self.assertRaisesRegex(SchedulerError, message):
                    self.scheduler.reconcile(
                        invalid_completion, at=NOW + timedelta(seconds=5)
                    )
        self.assertEqual(
            self.scheduler.snapshot().trials[0].state, DispatchState.LEASED
        )

    def test_state_hash_tampering_and_worker_capability_rebinding_fail_closed(self) -> None:
        capabilities = self.capabilities("worker-a")
        self.scheduler.register_worker(capabilities, at=NOW)
        with self.assertRaisesRegex(SchedulerError, "different capabilities"):
            self.scheduler.register_worker(
                self.capabilities("worker-a", memory=48), at=NOW
            )
        envelope = json.loads(self.store.path.read_text())
        envelope["payload"]["generation"] += 1
        self.store.path.write_text(json.dumps(envelope), encoding="utf-8")
        with self.assertRaisesRegex(SchedulerError, "hash mismatch"):
            self.scheduler.snapshot()


if __name__ == "__main__":
    unittest.main()
