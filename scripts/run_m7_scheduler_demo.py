#!/usr/bin/env python3
"""Run the synthetic M7 two-worker loss/retry/evaluation demonstration."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.canonical import canonical_json, fingerprint  # noqa: E402
from supervisor.contracts import CampaignSpec, TrialEvidence  # noqa: E402
from supervisor.evaluation import ArmIncumbentStore, OfflineD1Evaluator  # noqa: E402
from supervisor.scheduler import (  # noqa: E402
    DispatchState,
    DurableScheduler,
    SchedulerError,
    SchedulerStateStore,
    WorkerCapabilities,
    execute_assignments,
)
from supervisor.workers import (  # noqa: E402
    FakeExperimentWorker,
    RunContract,
    WorkerScenario,
    WorkerState,
)


NOTICE = "SYNTHETIC M7 ORCHESTRATION DEMO — NOT RLT PERFORMANCE EVIDENCE"
NOW = datetime(2026, 8, 4, 12, tzinfo=timezone.utc)


class Probe:
    def __init__(self) -> None:
        self.barrier = threading.Barrier(2)
        self.lock = threading.Lock()
        self.active = 0
        self.maximum = 0

    def enter(self) -> None:
        with self.lock:
            self.active += 1
            self.maximum = max(self.maximum, self.active)
        try:
            self.barrier.wait(timeout=5)
        finally:
            with self.lock:
                self.active -= 1


class ProbedWorker:
    def __init__(self, delegate: FakeExperimentWorker, probe: Probe) -> None:
        self.delegate = delegate
        self.worker_id = delegate.worker_id
        self.probe = probe

    def prepare(self, contract):
        return self.delegate.prepare(contract)

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


def git_head(repository: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), "rev-parse", "HEAD"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def build_campaign() -> CampaignSpec:
    raw = json.loads((ROOT / "examples" / "supervisor" / "campaign.json").read_text())
    raw["campaign_id"] = "m7-two-worker-demo"
    raw["research_question"] = (
        "Synthetic only: can two independent arms be scheduled with loss recovery?"
    )
    raw["budget"].update(
        {
            "max_trials": 8,
            "max_wall_time_seconds": 1000,
            "max_gpu_cost_usd": "2",
        }
    )
    return CampaignSpec.from_dict(raw)


def run_contract(
    campaign: CampaignSpec,
    *,
    arm_id: str,
    seed: int,
    candidate_commit: str,
) -> RunContract:
    return RunContract.create(
        campaign_id=campaign.campaign_id,
        trial_id=f"{arm_id}.s{seed}",
        arm_id=arm_id,
        parent_commit=campaign.baseline_commit,
        candidate_commit=candidate_commit,
        rlinf_commit=campaign.rlinf_commit,
        config_hash=fingerprint({"arm": arm_id}),
        command_hash=fingerprint({"arm": arm_id, "seed": seed}),
        seed=seed,
        reset_set_hash=campaign.reset_set_hash,
        evaluator_version=campaign.evaluator_version,
        max_wall_time_seconds=100,
        max_gpu_cost_usd="0.2",
    )


def scenario(success: float, state: WorkerState = WorkerState.COMPLETED) -> WorkerScenario:
    return WorkerScenario.create(
        terminal_state=state,
        started_at="2026-08-04T12:00:00Z",
        finished_at="2026-08-04T12:01:00Z",
        elapsed_seconds=60,
        metrics={"success_rate": success, "successful_episode_length": 40},
        exit_code=0 if state == WorkerState.COMPLETED else 7,
        gpu_cost_usd="0.1",
    )


def control_evidence(campaign: CampaignSpec) -> tuple[TrialEvidence, ...]:
    return tuple(
        TrialEvidence.from_dict(
            {
                "schema_version": 1,
                "campaign_id": campaign.campaign_id,
                "trial_id": f"control.s{seed}",
                "arm_id": "control",
                "parent_commit": campaign.baseline_commit,
                "candidate_commit": campaign.baseline_commit,
                "rlinf_commit": campaign.rlinf_commit,
                "config_hash": "a" * 64,
                "command_hash": "b" * 64,
                "seed": seed,
                "reset_set_hash": campaign.reset_set_hash,
                "evaluator_version": campaign.evaluator_version,
                "started_at": "2026-08-04T11:00:00Z",
                "finished_at": "2026-08-04T11:01:00Z",
                "status": "complete",
                "exit_code": 0,
                "elapsed_seconds": 60,
                "gpu_cost_usd": "0.1",
                "llm_cost_usd": "0",
                "metrics": {
                    "success_rate": 0.4,
                    "successful_episode_length": 45,
                },
                "metric_errors": [],
                "artifacts": [],
            }
        )
        for seed in campaign.seeds
    )


def capabilities(worker_id: str) -> WorkerCapabilities:
    return WorkerCapabilities.create(
        worker_id=worker_id,
        transport="local_fixture",
        gpu_name="synthetic-24gb",
        gpu_memory_gb=24,
        supported_modes=("fixture",),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=ROOT)
    arguments = parser.parse_args()
    repository = arguments.repository.resolve()
    head_before = git_head(repository)
    output = arguments.output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    campaign = build_campaign()
    candidates = {"config-arm": "b" * 40, "code-arm": "c" * 40}
    rates = {"config-arm": 0.5, "code-arm": 0.3}
    contracts = {
        f"{arm}.s{seed}": run_contract(
            campaign,
            arm_id=arm,
            seed=seed,
            candidate_commit=commit,
        )
        for arm, commit in candidates.items()
        for seed in campaign.seeds
    }
    lost_trial = f"code-arm.s{campaign.seeds[1]}"
    scenarios_a = {
        trial_id: scenario(rates[item.arm_id]) for trial_id, item in contracts.items()
    }
    scenarios_b = dict(scenarios_a)
    scenarios_b[lost_trial] = scenario(
        rates[contracts[lost_trial].arm_id], WorkerState.LOST
    )
    worker_a = FakeExperimentWorker(worker_id="worker-a", scenarios=scenarios_a)
    worker_b = FakeExperimentWorker(worker_id="worker-b", scenarios=scenarios_b)
    worker_c = FakeExperimentWorker(worker_id="worker-c", scenarios=scenarios_a)

    scheduler = DurableScheduler(
        campaign=campaign,
        store=SchedulerStateStore(output / "scheduler-state.json"),
    )
    scheduler.register_worker(capabilities("worker-a"), at=NOW)
    scheduler.register_worker(capabilities("worker-b"), at=NOW)
    for item in contracts.values():
        scheduler.enqueue(
            item,
            required_mode="fixture",
            required_gpu_memory_gb=24,
            at=NOW,
        )

    probe = Probe()
    first_batch = scheduler.dispatch(at=NOW, lease_ttl_seconds=120).assignments
    first_completions = execute_assignments(
        first_batch,
        workers={
            "worker-a": ProbedWorker(worker_a, probe),
            "worker-b": ProbedWorker(worker_b, probe),
        },
        max_workers=2,
    )
    stale_completion = None
    clock = NOW + timedelta(seconds=5)
    for completion in first_completions:
        outcome = scheduler.reconcile(completion, at=clock)
        if outcome.requeued:
            stale_completion = completion
    scheduler.register_worker(capabilities("worker-c"), at=clock)

    workers = {"worker-a": worker_a, "worker-c": worker_c}
    batches: list[list[str]] = [
        [item.contract.trial_id for item in first_batch]
    ]
    while any(
        item.state in {DispatchState.QUEUED, DispatchState.LEASED}
        for item in scheduler.snapshot().trials
    ):
        clock += timedelta(seconds=5)
        dispatch = scheduler.dispatch(at=clock, lease_ttl_seconds=120)
        if not dispatch.assignments:
            raise RuntimeError(f"synthetic scheduler deadlocked: {dispatch.blocked}")
        batches.append([item.contract.trial_id for item in dispatch.assignments])
        for completion in execute_assignments(
            dispatch.assignments, workers=workers, max_workers=2
        ):
            scheduler.reconcile(completion, at=clock + timedelta(seconds=1))

    stale_rejected = False
    if stale_completion is not None:
        try:
            scheduler.reconcile(stale_completion, at=clock + timedelta(seconds=2))
        except SchedulerError:
            stale_rejected = True

    state = scheduler.snapshot()
    evidence_by_arm = {
        arm: tuple(
            item.evidence
            for item in state.trials
            if item.contract.arm_id == arm and item.evidence is not None
        )
        for arm in candidates
    }
    evaluator = OfflineD1Evaluator()
    incumbents = ArmIncumbentStore(
        output / "incumbents.json",
        campaign_id=campaign.campaign_id,
        initial_incumbents={arm: campaign.baseline_commit for arm in candidates},
    )
    decisions = {}
    controls = control_evidence(campaign)
    for arm, candidate in candidates.items():
        evaluation = evaluator.evaluate(
            campaign=campaign,
            decision_id=f"m7-{arm}-decision",
            arm_id=arm,
            incumbent_commit=campaign.baseline_commit,
            candidate_commit=candidate,
            control_evidence=controls,
            candidate_evidence=evidence_by_arm[arm],
            decided_at=clock + timedelta(seconds=3),
        )
        incumbents.apply(arm, evaluation)
        decisions[arm] = evaluation.to_dict()

    head_after = git_head(repository)
    payload = {
        "notice": NOTICE,
        "campaign_hash": campaign.fingerprint(),
        "scheduler_version": "m7-scheduler-v1",
        "first_batch_parallelism": probe.maximum,
        "batches": batches,
        "lost_trial": lost_trial,
        "lost_trial_attempts": next(
            item.attempt_count for item in state.trials if item.contract.trial_id == lost_trial
        ),
        "stale_completion_rejected": stale_rejected,
        "final_trial_states": {
            item.contract.trial_id: item.state.value for item in state.trials
        },
        "decisions": decisions,
        "incumbents": incumbents.snapshot(),
        "stable_head_before": head_before,
        "stable_head_after": head_after,
        "stable_head_unchanged": head_before == head_after,
        "external_calls": [],
        "limitations": [
            "all metrics and workers are synthetic fixtures",
            "no SSH, GPU, W&B, provider, paid, or RLinf process was called",
            "live cancellation and utilization require the D1/remote-worker handoff",
        ],
    }
    artifact = output / "m7-demo.json"
    artifact.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
