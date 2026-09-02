from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from supervisor.contracts import CampaignSpec, Decision, TrialEvidence
from supervisor.evaluation import ArmIncumbentStore, EvaluationError, OfflineD1Evaluator
from tests.test_supervisor_contracts import campaign_data


INCUMBENT = "a" * 40
CANDIDATE = "b" * 40


def campaign() -> CampaignSpec:
    raw = campaign_data()
    raw["campaign_id"] = "offline-eval"
    raw["baseline_commit"] = INCUMBENT
    return CampaignSpec.from_dict(raw)


def evidence(
    *,
    seed: int,
    success: float | None,
    candidate: bool,
    length: float = 40,
    status: str = "complete",
    metric_errors: list[str] | None = None,
) -> TrialEvidence:
    metrics = {"successful_episode_length": length}
    if success is not None:
        metrics["success_rate"] = success
    return TrialEvidence.from_dict(
        {
            "schema_version": 1,
            "campaign_id": "offline-eval",
            "trial_id": f"{'candidate' if candidate else 'control'}-{seed}",
            "arm_id": "config-arm" if candidate else "control-arm",
            "parent_commit": INCUMBENT,
            "candidate_commit": CANDIDATE if candidate else INCUMBENT,
            "rlinf_commit": campaign().rlinf_commit,
            "config_hash": "c" * 64,
            "command_hash": "d" * 64,
            "seed": seed,
            "reset_set_hash": campaign().reset_set_hash,
            "evaluator_version": campaign().evaluator_version,
            "started_at": "2026-08-04T12:00:00Z",
            "finished_at": "2026-08-04T12:01:00Z",
            "status": status,
            "exit_code": 0 if status == "complete" else 7,
            "elapsed_seconds": 60,
            "gpu_cost_usd": "0.1",
            "llm_cost_usd": "0",
            "metrics": metrics,
            "metric_errors": metric_errors or [],
            "artifacts": [],
        }
    )


def evaluate(control_rates, candidate_rates, *, decision_id="decision-1"):
    spec = campaign()
    return OfflineD1Evaluator().evaluate(
        campaign=spec,
        decision_id=decision_id,
        arm_id="config-arm",
        incumbent_commit=INCUMBENT,
        candidate_commit=CANDIDATE,
        control_evidence=[
            evidence(seed=seed, success=rate, candidate=False)
            for seed, rate in zip(spec.seeds, control_rates)
        ],
        candidate_evidence=[
            evidence(seed=seed, success=rate, candidate=True)
            for seed, rate in zip(spec.seeds, candidate_rates)
        ],
    )


class OfflineEvaluatorTests(unittest.TestCase):
    def test_keep_and_revert_follow_frozen_numeric_rule(self) -> None:
        kept = evaluate([0.4, 0.4, 0.4], [0.5, 0.5, 0.5])
        reverted = evaluate(
            [0.4, 0.4, 0.4], [0.35, 0.35, 0.35], decision_id="decision-2"
        )
        self.assertEqual(kept.decision_record.decision, Decision.KEEP)
        self.assertEqual(kept.decision_record.incumbent_after, CANDIDATE)
        self.assertEqual(reverted.decision_record.decision, Decision.REVERT)
        self.assertEqual(reverted.decision_record.incumbent_after, INCUMBENT)

    def test_decision_is_independent_of_agent_prose(self) -> None:
        first = evaluate([0.4] * 3, [0.5] * 3, decision_id="prose-free-1")
        second = evaluate([0.4] * 3, [0.5] * 3, decision_id="prose-free-2")
        self.assertEqual(
            first.decision_record.decision, second.decision_record.decision
        )
        self.assertEqual(first.decision_record.reason, second.decision_record.reason)
        self.assertEqual(first.mean_success_delta, second.mean_success_delta)

    def test_missing_seed_or_required_metric_is_inconclusive(self) -> None:
        spec = campaign()
        controls = [evidence(seed=s, success=0.4, candidate=False) for s in spec.seeds]
        candidates = [
            evidence(seed=s, success=0.5, candidate=True) for s in spec.seeds[:-1]
        ]
        missing_seed = OfflineD1Evaluator().evaluate(
            campaign=spec,
            decision_id="missing-seed",
            arm_id="config-arm",
            incumbent_commit=INCUMBENT,
            candidate_commit=CANDIDATE,
            control_evidence=controls,
            candidate_evidence=candidates,
        )
        candidates = [
            evidence(seed=s, success=None if s == spec.seeds[0] else 0.5, candidate=True)
            for s in spec.seeds
        ]
        missing_metric = OfflineD1Evaluator().evaluate(
            campaign=spec,
            decision_id="missing-metric",
            arm_id="config-arm",
            incumbent_commit=INCUMBENT,
            candidate_commit=CANDIDATE,
            control_evidence=controls,
            candidate_evidence=candidates,
        )
        self.assertEqual(missing_seed.decision_record.decision, Decision.INCONCLUSIVE)
        self.assertEqual(missing_metric.decision_record.decision, Decision.INCONCLUSIVE)

    def test_failed_or_metric_error_evidence_fails_closed(self) -> None:
        spec = campaign()
        controls = [evidence(seed=s, success=0.4, candidate=False) for s in spec.seeds]
        candidates = [evidence(seed=s, success=0.5, candidate=True) for s in spec.seeds]
        candidates[0] = evidence(
            seed=spec.seeds[0], success=0.5, candidate=True,
            status="failed", metric_errors=["training failed"],
        )
        result = OfflineD1Evaluator().evaluate(
            campaign=spec,
            decision_id="failed-evidence",
            arm_id="config-arm",
            incumbent_commit=INCUMBENT,
            candidate_commit=CANDIDATE,
            control_evidence=controls,
            candidate_evidence=candidates,
        )
        self.assertEqual(result.decision_record.decision, Decision.FAILED)

    def test_evidence_identity_mismatch_is_inconclusive(self) -> None:
        spec = campaign()
        controls = [evidence(seed=s, success=0.4, candidate=False) for s in spec.seeds]
        candidates = [evidence(seed=s, success=0.5, candidate=True) for s in spec.seeds]
        raw = candidates[0].to_dict()
        raw["reset_set_hash"] = "9" * 64
        candidates[0] = TrialEvidence.from_dict(raw)
        result = OfflineD1Evaluator().evaluate(
            campaign=spec,
            decision_id="mismatch",
            arm_id="config-arm",
            incumbent_commit=INCUMBENT,
            candidate_commit=CANDIDATE,
            control_evidence=controls,
            candidate_evidence=candidates,
        )
        self.assertEqual(result.decision_record.decision, Decision.INCONCLUSIVE)


class IncumbentStoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "incumbents.json"

    def store(self):
        return ArmIncumbentStore(
            self.path,
            campaign_id="offline-eval",
            initial_incumbents={"config-arm": INCUMBENT, "code-arm": "c" * 40},
        )

    def test_keep_moves_only_named_arm_and_replay_is_idempotent(self) -> None:
        store = self.store()
        result = evaluate([0.4] * 3, [0.5] * 3)
        self.assertEqual(store.apply("config-arm", result), CANDIDATE)
        self.assertEqual(store.apply("config-arm", result), CANDIDATE)
        self.assertEqual(store.snapshot()["code-arm"], "c" * 40)
        self.assertEqual(self.store().snapshot()["config-arm"], CANDIDATE)

    def test_nonkeep_does_not_move_pointer_and_conflicting_id_is_rejected(self) -> None:
        store = self.store()
        reverted = evaluate([0.4] * 3, [0.3] * 3, decision_id="same-id")
        store.apply("config-arm", reverted)
        self.assertEqual(store.snapshot()["config-arm"], INCUMBENT)
        kept = evaluate([0.4] * 3, [0.5] * 3, decision_id="same-id")
        with self.assertRaisesRegex(EvaluationError, "already bound"):
            store.apply("config-arm", kept)

    def test_restart_rejects_changed_arm_configuration(self) -> None:
        self.store()
        with self.assertRaisesRegex(EvaluationError, "arms"):
            ArmIncumbentStore(
                self.path,
                campaign_id="offline-eval",
                initial_incumbents={"different-arm": INCUMBENT},
            )


if __name__ == "__main__":
    unittest.main()
