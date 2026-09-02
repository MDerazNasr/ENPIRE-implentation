"""Offline composition of proposal, Git, worker, evaluator, and ledger layers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from supervisor.attempts import ProposalSessionResult
from supervisor.canonical import ContractError, fingerprint, require_identifier
from supervisor.contracts import CampaignSpec, Decision, TrialEvidence, TrialState
from supervisor.evaluation import (
    ArmIncumbentStore,
    EvaluationResult,
    OfflineD1Evaluator,
)
from supervisor.git_manager import (
    GitExperimentManager,
    PreparationRecord,
    PreparationStatus,
    append_preparation_to_ledger,
)
from supervisor.ledger import EntityType, EventLedger
from supervisor.workers import (
    ExperimentWorker,
    RunContract,
    WorkerSnapshot,
    WorkerState,
)


class CoordinatorError(ContractError):
    """Raised when coordinator inputs or state are inconsistent."""


class RunContractFactory(Protocol):
    """Create and register a backend-specific immutable run contract."""

    synthetic: bool
    promotion_allowed: bool

    def create(
        self,
        *,
        campaign: CampaignSpec,
        proposal: Any,
        preparation: PreparationRecord,
        trial_id: str,
        seed: int,
        incumbent_commit: str,
        candidate_commit: str,
        default_config_hash: str,
        max_gpu_cost_usd: str,
    ) -> RunContract: ...


class IterationStatus(str, Enum):
    PROPOSAL_REJECTED = "proposal_rejected"
    PREPARATION_REJECTED = "preparation_rejected"
    PREPARATION_FAILED = "preparation_failed"
    WORKER_FAILED = "worker_failed"
    ACCEPTANCE_RECORDED = "acceptance_recorded"
    DECIDED = "decided"


@dataclass(frozen=True)
class LedgerAnchor:
    trial_id: str
    state: str
    sequence: int
    head_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "state": self.state,
            "sequence": self.sequence,
            "head_hash": self.head_hash,
        }


@dataclass(frozen=True)
class OfflineIterationResult:
    iteration_id: str
    status: IterationStatus
    campaign_id: str
    arm_id: str | None
    proposal_session_hash: str
    preparation: PreparationRecord | None
    run_contracts: tuple[RunContract, ...]
    worker_snapshots: tuple[WorkerSnapshot, ...]
    evidence: tuple[TrialEvidence, ...]
    evaluation: EvaluationResult | None
    incumbent_before: str | None
    incumbent_after: str | None
    ledger_anchors: tuple[LedgerAnchor, ...]
    errors: tuple[str, ...]
    synthetic: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "iteration_id": self.iteration_id,
            "status": self.status.value,
            "campaign_id": self.campaign_id,
            "arm_id": self.arm_id,
            "proposal_session_hash": self.proposal_session_hash,
            "preparation": self.preparation.to_dict() if self.preparation else None,
            "run_contracts": [item.to_dict() for item in self.run_contracts],
            "worker_snapshots": [item.to_dict() for item in self.worker_snapshots],
            "evidence": [item.to_dict() for item in self.evidence],
            "evaluation": self.evaluation.to_dict() if self.evaluation else None,
            "incumbent_before": self.incumbent_before,
            "incumbent_after": self.incumbent_after,
            "ledger_anchors": [item.to_dict() for item in self.ledger_anchors],
            "errors": list(self.errors),
            "synthetic": self.synthetic,
        }

    def fingerprint(self) -> str:
        return fingerprint(self.to_dict())


class OfflineCampaignCoordinator:
    def __init__(
        self,
        *,
        campaign: CampaignSpec,
        git_manager: GitExperimentManager,
        worker: ExperimentWorker,
        evaluator: OfflineD1Evaluator,
        incumbents: ArmIncumbentStore,
        ledger_root: Path,
        run_contract_factory: RunContractFactory | None = None,
        synthetic: bool = True,
        evaluation_enabled: bool = True,
    ) -> None:
        self.campaign = campaign
        self.git_manager = git_manager
        self.worker = worker
        self.evaluator = evaluator
        self.incumbents = incumbents
        self.ledger_root = ledger_root
        self.run_contract_factory = run_contract_factory
        self.synthetic = synthetic
        self.evaluation_enabled = evaluation_enabled
        self.ledger_root.mkdir(parents=True, exist_ok=True)
        if incumbents.campaign_id != campaign.campaign_id:
            raise CoordinatorError("incumbent store campaign does not match coordinator")
        if run_contract_factory is not None and run_contract_factory.synthetic != synthetic:
            raise CoordinatorError(
                "run-contract factory synthetic label does not match coordinator"
            )
        factory_promotion = (
            getattr(run_contract_factory, "promotion_allowed", True)
            if run_contract_factory is not None
            else True
        )
        if evaluation_enabled != factory_promotion:
            raise CoordinatorError(
                "coordinator evaluation authority disagrees with run-contract factory"
            )

    def run(
        self,
        *,
        iteration_id: str,
        proposal_session: ProposalSessionResult,
        control_evidence: Sequence[TrialEvidence],
        decision_id: str,
        base_config: Mapping[str, Any] | None = None,
    ) -> OfflineIterationResult:
        iteration = require_identifier(iteration_id, "coordinator.iteration_id")
        session_hash = proposal_session.fingerprint()
        proposal = proposal_session.proposal
        if not proposal_session.accepted or proposal is None:
            return OfflineIterationResult(
                iteration_id=iteration,
                status=IterationStatus.PROPOSAL_REJECTED,
                campaign_id=self.campaign.campaign_id,
                arm_id=None,
                proposal_session_hash=session_hash,
                preparation=None,
                run_contracts=(),
                worker_snapshots=(),
                evidence=(),
                evaluation=None,
                incumbent_before=None,
                incumbent_after=None,
                ledger_anchors=(),
                errors=("proposal session did not produce an accepted proposal",),
                synthetic=self.synthetic,
            )
        if proposal.campaign_id != self.campaign.campaign_id:
            raise CoordinatorError("proposal session campaign does not match coordinator")
        arm_id = proposal.arm_id
        current = self.incumbents.snapshot()
        if arm_id not in current:
            raise CoordinatorError("proposal arm is not registered in incumbent store")
        incumbent = current[arm_id]
        preparation = self.git_manager.prepare(
            proposal,
            self.campaign,
            incumbent_commit=incumbent,
            base_config=base_config,
        )
        if preparation.status != PreparationStatus.READY:
            status = (
                IterationStatus.PREPARATION_REJECTED
                if preparation.status == PreparationStatus.REJECTED
                else IterationStatus.PREPARATION_FAILED
            )
            return OfflineIterationResult(
                iteration_id=iteration,
                status=status,
                campaign_id=self.campaign.campaign_id,
                arm_id=arm_id,
                proposal_session_hash=session_hash,
                preparation=preparation,
                run_contracts=(),
                worker_snapshots=(),
                evidence=(),
                evaluation=None,
                incumbent_before=incumbent,
                incumbent_after=incumbent,
                ledger_anchors=(),
                errors=preparation.errors,
                synthetic=self.synthetic,
            )
        candidate = preparation.candidate_commit
        if candidate is None:
            raise CoordinatorError("ready preparation is missing its candidate commit")
        config_hash = preparation.resolved_config_hash or preparation.staged_diff_hash
        if config_hash is None:
            raise CoordinatorError("ready preparation is missing a runnable config hash")

        contracts: list[RunContract] = []
        snapshots: list[WorkerSnapshot] = []
        evidence: list[TrialEvidence] = []
        ledgers: dict[str, EventLedger] = {}
        worker_errors: list[str] = []
        per_trial_gpu_cap = self._per_trial_gpu_cap(
            proposal.estimated_budget.gpu_cost_usd,
            len(self.campaign.seeds),
        )
        for seed in self.campaign.seeds:
            trial_id = require_identifier(
                f"{proposal.proposal_id}.s{seed}", "coordinator trial ID"
            )
            ledger = EventLedger(
                self.ledger_root / f"{trial_id}.jsonl",
                campaign_id=self.campaign.campaign_id,
                entity_type=EntityType.TRIAL,
                entity_id=trial_id,
            )
            ledgers[trial_id] = ledger
            append_preparation_to_ledger(ledger, preparation)
            try:
                contract = self._create_run_contract(
                    proposal=proposal,
                    preparation=preparation,
                    trial_id=trial_id,
                    seed=seed,
                    incumbent=incumbent,
                    candidate=candidate,
                    config_hash=config_hash,
                    max_gpu_cost_usd=per_trial_gpu_cap,
                )
            except ContractError as error:
                worker_errors.append(
                    f"run-contract planning failed for trial {trial_id}: {error}"
                )
                ledger.append_transition(
                    TrialState.FAILED,
                    actor=self._actor("coordinator"),
                    reason="backend rejected the immutable run plan",
                )
                continue
            contracts.append(contract)
            try:
                prepared = self.worker.prepare(contract)
                self._validate_worker_snapshot(
                    prepared, contract, {WorkerState.PREPARED}
                )
                heartbeat = self.worker.heartbeat(trial_id)
                self._validate_worker_snapshot(
                    heartbeat, contract, {WorkerState.PREPARED}
                )
            except ContractError as error:
                worker_errors.append(f"worker rejected trial {trial_id}: {error}")
                ledger.append_transition(
                    TrialState.FAILED,
                    actor=self._actor("coordinator"),
                    reason="worker rejected the immutable run contract",
                )
                continue
            ledger.append_transition(
                TrialState.RUNNING,
                actor=self.worker.worker_id,
                reason=(
                    "worker launched synthetic trial"
                    if self.synthetic
                    else "worker launched authorized D1 trial"
                ),
                metadata={
                    "worker_id": self.worker.worker_id,
                    "run_contract_hash": contract.fingerprint(),
                },
            )
            try:
                terminal = self.worker.launch(trial_id)
                self._validate_worker_snapshot(
                    terminal,
                    contract,
                    {
                        WorkerState.COMPLETED,
                        WorkerState.FAILED,
                        WorkerState.CANCELLED,
                        WorkerState.LOST,
                    },
                )
            except ContractError as error:
                worker_errors.append(f"worker failed trial {trial_id}: {error}")
                ledger.append_transition(
                    TrialState.FAILED,
                    actor=self._actor("coordinator"),
                    reason="worker returned an invalid terminal response",
                )
                continue
            snapshots.append(terminal)
            if terminal.state in {WorkerState.COMPLETED, WorkerState.FAILED}:
                try:
                    item = self.worker.fetch_evidence(trial_id)
                    if item.fingerprint() != terminal.evidence_hash:
                        raise CoordinatorError(
                            "worker evidence hash does not match status"
                        )
                except ContractError as error:
                    worker_errors.append(
                        f"worker evidence failed for trial {trial_id}: {error}"
                    )
                    ledger.append_transition(
                        TrialState.FAILED,
                        actor=self._actor("coordinator"),
                        reason="worker evidence failed contract validation",
                    )
                    continue
                evidence.append(item)
                target = TrialState.FAILED
                if terminal.state == WorkerState.COMPLETED:
                    target = (
                        TrialState.EVALUATED
                        if self.evaluation_enabled
                        else TrialState.RECORDED
                    )
                ledger.append_transition(
                    target,
                    actor=self._actor("evidence-normalizer"),
                    reason=(
                        "strict evidence is ready for evaluation"
                        if target == TrialState.EVALUATED
                        else (
                            "strict paid-acceptance evidence was recorded"
                            if target == TrialState.RECORDED
                            else "worker reported a failed trial"
                        )
                    ),
                    metadata={"evidence_hash": item.fingerprint()},
                )
            else:
                worker_errors.append(
                    f"worker ended trial {trial_id} in state {terminal.state.value}"
                )
                ledger.append_transition(
                    TrialState.FAILED,
                    actor=self._actor("coordinator"),
                    reason="worker did not return terminal evidence",
                    metadata={"worker_state": terminal.state.value},
                )

        if worker_errors or len(evidence) != len(self.campaign.seeds):
            self._fail_evaluated_ledgers(ledgers, "campaign worker set was incomplete")
            return self._result(
                iteration=iteration,
                status=IterationStatus.WORKER_FAILED,
                session_hash=session_hash,
                arm_id=arm_id,
                preparation=preparation,
                contracts=contracts,
                snapshots=snapshots,
                evidence=evidence,
                evaluation=None,
                incumbent_before=incumbent,
                incumbent_after=incumbent,
                ledgers=ledgers,
                errors=worker_errors or ["worker evidence set is incomplete"],
            )

        if not self.evaluation_enabled:
            return self._result(
                iteration=iteration,
                status=IterationStatus.ACCEPTANCE_RECORDED,
                session_hash=session_hash,
                arm_id=arm_id,
                preparation=preparation,
                contracts=contracts,
                snapshots=snapshots,
                evidence=evidence,
                evaluation=None,
                incumbent_before=incumbent,
                incumbent_after=incumbent,
                ledgers=ledgers,
                errors=[],
            )

        evaluation = self.evaluator.evaluate(
            campaign=self.campaign,
            decision_id=decision_id,
            arm_id=arm_id,
            incumbent_commit=incumbent,
            candidate_commit=candidate,
            control_evidence=control_evidence,
            candidate_evidence=evidence,
        )
        updated = self.incumbents.apply(arm_id, evaluation)
        terminal_state = {
            Decision.KEEP: TrialState.KEPT,
            Decision.REVERT: TrialState.REVERTED,
            Decision.INCONCLUSIVE: TrialState.INCONCLUSIVE,
            Decision.FAILED: TrialState.FAILED,
        }[evaluation.decision_record.decision]
        for trial_id, ledger in ledgers.items():
            if ledger.read().state == TrialState.EVALUATED:
                ledger.append_transition(
                    terminal_state,
                    actor=self._actor("deterministic-evaluator"),
                    reason=evaluation.decision_record.reason,
                    metadata={
                        "decision_hash": evaluation.decision_record.fingerprint(),
                        "evaluation_hash": evaluation.fingerprint(),
                    },
                )
        return self._result(
            iteration=iteration,
            status=IterationStatus.DECIDED,
            session_hash=session_hash,
            arm_id=arm_id,
            preparation=preparation,
            contracts=contracts,
            snapshots=snapshots,
            evidence=evidence,
            evaluation=evaluation,
            incumbent_before=incumbent,
            incumbent_after=updated,
            ledgers=ledgers,
            errors=[],
        )

    def _per_trial_gpu_cap(self, proposal_cap: str, count: int) -> str:
        from decimal import Decimal

        total = min(
            Decimal(self.campaign.budget.max_gpu_cost_usd),
            Decimal(proposal_cap),
        )
        return str(total / Decimal(count))

    def _create_run_contract(
        self,
        *,
        proposal: Any,
        preparation: PreparationRecord,
        trial_id: str,
        seed: int,
        incumbent: str,
        candidate: str,
        config_hash: str,
        max_gpu_cost_usd: str,
    ) -> RunContract:
        if self.run_contract_factory is not None:
            return self.run_contract_factory.create(
                campaign=self.campaign,
                proposal=proposal,
                preparation=preparation,
                trial_id=trial_id,
                seed=seed,
                incumbent_commit=incumbent,
                candidate_commit=candidate,
                default_config_hash=config_hash,
                max_gpu_cost_usd=max_gpu_cost_usd,
            )
        command_hash = fingerprint(
            {
                "backend": "offline-fake-worker-v1",
                "candidate_commit": candidate,
                "config_hash": config_hash,
                "seed": seed,
            }
        )
        return RunContract.create(
            campaign_id=self.campaign.campaign_id,
            trial_id=trial_id,
            arm_id=proposal.arm_id,
            parent_commit=incumbent,
            candidate_commit=candidate,
            rlinf_commit=self.campaign.rlinf_commit,
            config_hash=config_hash,
            command_hash=command_hash,
            seed=seed,
            reset_set_hash=self.campaign.reset_set_hash,
            evaluator_version=self.campaign.evaluator_version,
            max_wall_time_seconds=proposal.estimated_budget.wall_time_seconds,
            max_gpu_cost_usd=max_gpu_cost_usd,
        )

    def _validate_worker_snapshot(
        self,
        snapshot: WorkerSnapshot,
        contract: RunContract,
        allowed_states: set[WorkerState],
    ) -> None:
        if not isinstance(snapshot, WorkerSnapshot):
            raise CoordinatorError("worker returned an unsupported status type")
        if snapshot.worker_id != self.worker.worker_id:
            raise CoordinatorError("worker status identity mismatch")
        if snapshot.trial_id != contract.trial_id:
            raise CoordinatorError("worker status trial mismatch")
        if snapshot.contract_hash != contract.fingerprint():
            raise CoordinatorError("worker status run-contract mismatch")
        if snapshot.state not in allowed_states:
            raise CoordinatorError("worker status lifecycle mismatch")

    def _fail_evaluated_ledgers(
        self,
        ledgers: Mapping[str, EventLedger], reason: str
    ) -> None:
        for ledger in ledgers.values():
            if ledger.read().state == TrialState.EVALUATED:
                ledger.append_transition(
                    TrialState.FAILED,
                    actor=self._actor("coordinator"),
                    reason=reason,
                )

    def _actor(self, role: str) -> str:
        return f"{'synthetic' if self.synthetic else 'd1'}-{role}"

    def _result(
        self,
        *,
        iteration: str,
        status: IterationStatus,
        session_hash: str,
        arm_id: str,
        preparation: PreparationRecord,
        contracts: Sequence[RunContract],
        snapshots: Sequence[WorkerSnapshot],
        evidence: Sequence[TrialEvidence],
        evaluation: EvaluationResult | None,
        incumbent_before: str,
        incumbent_after: str,
        ledgers: Mapping[str, EventLedger],
        errors: Sequence[str],
    ) -> OfflineIterationResult:
        anchors: list[LedgerAnchor] = []
        for trial_id, ledger in sorted(ledgers.items()):
            snapshot = ledger.read()
            anchors.append(
                LedgerAnchor(
                    trial_id=trial_id,
                    state=snapshot.state.value,
                    sequence=snapshot.sequence,
                    head_hash=snapshot.head_hash,
                )
            )
        return OfflineIterationResult(
            iteration_id=iteration,
            status=status,
            campaign_id=self.campaign.campaign_id,
            arm_id=arm_id,
            proposal_session_hash=session_hash,
            preparation=preparation,
            run_contracts=tuple(contracts),
            worker_snapshots=tuple(snapshots),
            evidence=tuple(evidence),
            evaluation=evaluation,
            incumbent_before=incumbent_before,
            incumbent_after=incumbent_after,
            ledger_anchors=tuple(anchors),
            errors=tuple(errors),
            synthetic=self.synthetic,
        )


# M5 makes the coordinator backend-neutral; keep the established name compatible.
CampaignCoordinator = OfflineCampaignCoordinator
