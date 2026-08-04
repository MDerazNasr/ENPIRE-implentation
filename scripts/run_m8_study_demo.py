#!/usr/bin/env python3
"""Run the deterministic offline M8 three-arm study rehearsal."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.canonical import fingerprint  # noqa: E402
from supervisor.contracts import CampaignSpec, TrialEvidence  # noqa: E402
from supervisor.evaluation import OfflineD1Evaluator  # noqa: E402
from supervisor.study import (  # noqa: E402
    CLAUDE_CODE_ARM,
    CLAUDE_CONFIG_ARM,
    FIXED_RULE_CONFIG_ARM,
    EditMode,
    ProposerKind,
    StudyActivation,
    StudyArmSpec,
    StudyRecordStatus,
    StudySpec,
    StudyStage,
    StudyStateStore,
    StudyTrialRecord,
    ThreeArmStudy,
)
from supervisor.study_reporting import write_study_report  # noqa: E402


NOW = datetime(2026, 8, 4, 12, tzinfo=timezone.utc)
NOTICE = "SYNTHETIC M8 STUDY REHEARSAL — NOT RL OR RESEARCH EVIDENCE"


def build_campaign() -> CampaignSpec:
    raw = json.loads((ROOT / "examples" / "supervisor" / "campaign.json").read_text())
    raw["campaign_id"] = "m8-three-arm-study"
    raw["research_question"] = "Synthetic only: does the frozen three-arm protocol reconcile?"
    return CampaignSpec.from_dict(raw)


def build_spec(campaign: CampaignSpec) -> StudySpec:
    worker = {"discovery_slots": 3, "max_wall_time_seconds_per_candidate": 600, "max_gpu_cost_usd_per_candidate": "1"}
    return StudySpec.create(
        study_id="m8-three-arm-study",
        campaign_id=campaign.campaign_id,
        research_question="Under matched worker budgets, how do fixed-rule configuration, Claude configuration, and Claude objective-code supervision compare?",
        baseline_commit=campaign.baseline_commit,
        rlinf_commit=campaign.rlinf_commit,
        reset_set_hash=campaign.reset_set_hash,
        evaluator_version=campaign.evaluator_version,
        paired_seeds=campaign.seeds,
        created_at=NOW,
        arms=(
            StudyArmSpec.create(arm_id=FIXED_RULE_CONFIG_ARM, proposer=ProposerKind.FIXED_RULE, edit_mode=EditMode.CONFIG_ONLY, max_llm_cost_usd_per_candidate="0", **worker),
            StudyArmSpec.create(arm_id=CLAUDE_CONFIG_ARM, proposer=ProposerKind.CLAUDE, edit_mode=EditMode.CONFIG_ONLY, max_llm_cost_usd_per_candidate="0.5", **worker),
            StudyArmSpec.create(arm_id=CLAUDE_CODE_ARM, proposer=ProposerKind.CLAUDE, edit_mode=EditMode.ACTOR_OBJECTIVE, max_llm_cost_usd_per_candidate="0.5", **worker),
        ),
    )


def evidence(
    campaign: CampaignSpec,
    *,
    prefix: str,
    arm_id: str,
    parent: str,
    candidate: str,
    successes: tuple[float, float, float],
    control: bool = False,
    fail_seed: int | None = None,
) -> tuple[TrialEvidence, ...]:
    rows = []
    for seed, success in zip(campaign.seeds, successes):
        failed = seed == fail_seed
        rows.append(
            TrialEvidence.from_dict(
                {
                    "schema_version": 1,
                    "campaign_id": campaign.campaign_id,
                    "trial_id": f"{prefix}.s{seed}",
                    "arm_id": "control" if control else arm_id,
                    "parent_commit": parent,
                    "candidate_commit": parent if control else candidate,
                    "rlinf_commit": campaign.rlinf_commit,
                    "config_hash": fingerprint({"prefix": prefix, "kind": "config"}),
                    "command_hash": fingerprint({"prefix": prefix, "seed": seed}),
                    "seed": seed,
                    "reset_set_hash": campaign.reset_set_hash,
                    "evaluator_version": campaign.evaluator_version,
                    "started_at": "2026-08-04T12:00:00Z",
                    "finished_at": "2026-08-04T12:01:30Z",
                    "status": "failed" if failed else "complete",
                    "exit_code": 7 if failed else 0,
                    "elapsed_seconds": 90,
                    "gpu_cost_usd": "0.05",
                    "llm_cost_usd": "0",
                    "metrics": {"success_rate": success, "successful_episode_length": 40},
                    "metric_errors": [],
                    "artifacts": [],
                }
            )
        )
    return tuple(rows)


def evaluated_record(
    campaign: CampaignSpec,
    *,
    record_id: str,
    arm_id: str,
    stage: StudyStage,
    slot: int,
    edit_mode: EditMode,
    parent: str,
    candidate: str,
    control_success: float,
    candidate_success: float,
    proposal_hash: str | None,
    failed: bool = False,
    confirmation: bool = False,
) -> StudyTrialRecord:
    prefix = f"{record_id}.{'confirm' if confirmation else 'discover'}"
    controls = evidence(
        campaign, prefix=f"{prefix}.control", arm_id=arm_id, parent=parent,
        candidate=parent, successes=(control_success,) * 3, control=True,
    )
    candidates = evidence(
        campaign, prefix=f"{prefix}.candidate", arm_id=arm_id, parent=parent,
        candidate=candidate, successes=(candidate_success,) * 3,
        fail_seed=campaign.seeds[1] if failed else None,
    )
    result = OfflineD1Evaluator().evaluate(
        campaign=campaign,
        decision_id=f"decision-{record_id}",
        arm_id=arm_id,
        incumbent_commit=parent,
        candidate_commit=candidate,
        control_evidence=controls,
        candidate_evidence=candidates,
        decided_at=NOW,
    )
    return StudyTrialRecord.create(
        record_id=record_id,
        arm_id=arm_id,
        stage=stage,
        slot_number=slot,
        status=StudyRecordStatus.FAILED if failed else StudyRecordStatus.COMPLETE,
        edit_mode=edit_mode,
        incumbent_before=parent,
        candidate_commit=candidate,
        proposal_session_hash=proposal_hash,
        proposal_valid=True,
        candidate_valid=not failed,
        evidence=candidates,
        evaluation=result,
        proposal_llm_cost_usd="0" if proposal_hash is None else "0.08",
        input_tokens=0 if proposal_hash is None else 700,
        output_tokens=0 if proposal_hash is None else 180,
        human_interventions=0,
        reason="synthetic deterministic fixture",
        recorded_at=NOW,
    )


def invalid_record(*, record_id: str, arm_id: str, slot: int, edit_mode: EditMode, incumbent: str, claude: bool) -> StudyTrialRecord:
    return StudyTrialRecord.create(
        record_id=record_id,
        arm_id=arm_id,
        stage=StudyStage.DISCOVERY,
        slot_number=slot,
        status=StudyRecordStatus.INVALID,
        edit_mode=edit_mode,
        incumbent_before=incumbent,
        candidate_commit=None,
        proposal_session_hash=fingerprint({"invalid": record_id}) if claude else None,
        proposal_valid=False,
        candidate_valid=False,
        proposal_llm_cost_usd="0.03" if claude else "0",
        input_tokens=350 if claude else 0,
        output_tokens=60 if claude else 0,
        reason="synthetic invalid proposal retained and charged to its slot",
        recorded_at=NOW,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)

    campaign = build_campaign()
    spec = build_spec(campaign)
    activation = StudyActivation.create(spec=spec, synthetic=True, activated_by="m8-demo", activated_at=NOW)
    store = StudyStateStore(output / "study-state.json")
    store.initialize(spec, activation)
    study = ThreeArmStudy(store)
    baseline = spec.baseline_commit
    commits = {
        "r1": "1" * 40, "r2": "2" * 40,
        "c1": "3" * 40, "c2": "4" * 40,
        "o1": "5" * 40, "o2": "6" * 40, "o3": "7" * 40,
    }
    # Fixed rule: one kept candidate, one null result, one invalid slot.
    study.record_discovery(evaluated_record(campaign, record_id="rule-d1", arm_id=FIXED_RULE_CONFIG_ARM, stage=StudyStage.DISCOVERY, slot=1, edit_mode=EditMode.CONFIG_ONLY, parent=baseline, candidate=commits["r1"], control_success=.40, candidate_success=.46, proposal_hash=None))
    study.record_discovery(evaluated_record(campaign, record_id="rule-d2", arm_id=FIXED_RULE_CONFIG_ARM, stage=StudyStage.DISCOVERY, slot=2, edit_mode=EditMode.CONFIG_ONLY, parent=commits["r1"], candidate=commits["r2"], control_success=.46, candidate_success=.44, proposal_hash=None))
    study.record_discovery(invalid_record(record_id="rule-d3", arm_id=FIXED_RULE_CONFIG_ARM, slot=3, edit_mode=EditMode.CONFIG_ONLY, incumbent=commits["r1"], claude=False))
    # Claude config: invalid output, then a keep, then a reverted candidate.
    study.record_discovery(invalid_record(record_id="config-d1", arm_id=CLAUDE_CONFIG_ARM, slot=1, edit_mode=EditMode.CONFIG_ONLY, incumbent=baseline, claude=True))
    study.record_discovery(evaluated_record(campaign, record_id="config-d2", arm_id=CLAUDE_CONFIG_ARM, stage=StudyStage.DISCOVERY, slot=2, edit_mode=EditMode.CONFIG_ONLY, parent=baseline, candidate=commits["c1"], control_success=.40, candidate_success=.50, proposal_hash=fingerprint({"session": "config-d2"})))
    study.record_discovery(evaluated_record(campaign, record_id="config-d3", arm_id=CLAUDE_CONFIG_ARM, stage=StudyStage.DISCOVERY, slot=3, edit_mode=EditMode.CONFIG_ONLY, parent=commits["c1"], candidate=commits["c2"], control_success=.50, candidate_success=.47, proposal_hash=fingerprint({"session": "config-d3"})))
    # Claude code: a worker failure is retained, then two improving candidates.
    study.record_discovery(evaluated_record(campaign, record_id="code-d1", arm_id=CLAUDE_CODE_ARM, stage=StudyStage.DISCOVERY, slot=1, edit_mode=EditMode.ACTOR_OBJECTIVE, parent=baseline, candidate=commits["o1"], control_success=.40, candidate_success=.45, proposal_hash=fingerprint({"session": "code-d1"}), failed=True))
    study.record_discovery(evaluated_record(campaign, record_id="code-d2", arm_id=CLAUDE_CODE_ARM, stage=StudyStage.DISCOVERY, slot=2, edit_mode=EditMode.ACTOR_OBJECTIVE, parent=baseline, candidate=commits["o2"], control_success=.40, candidate_success=.48, proposal_hash=fingerprint({"session": "code-d2"})))
    study.record_discovery(evaluated_record(campaign, record_id="code-d3", arm_id=CLAUDE_CODE_ARM, stage=StudyStage.DISCOVERY, slot=3, edit_mode=EditMode.ACTOR_OBJECTIVE, parent=commits["o2"], candidate=commits["o3"], control_success=.48, candidate_success=.55, proposal_hash=fingerprint({"session": "code-d3"})))

    selected = study.select_candidates()
    for arm in selected.arms:
        assert arm.selection and arm.selection.selected_candidate_commit
        selected_record = next(item for item in selected.records if item.record_id == arm.selection.selected_record_id)
        expected = selected_record.evaluation.candidate_mean_success
        study.record_confirmation(
            evaluated_record(
                campaign,
                record_id=f"{arm.arm_id}-confirm",
                arm_id=arm.arm_id,
                stage=StudyStage.CONFIRMATION,
                slot=1,
                edit_mode=spec.arm(arm.arm_id).edit_mode,
                parent=baseline,
                candidate=arm.selection.selected_candidate_commit,
                control_success=.40,
                candidate_success=float(expected),
                proposal_hash=(None if arm.arm_id == FIXED_RULE_CONFIG_ARM else fingerprint({"confirmation": arm.arm_id})),
                confirmation=True,
            )
        )
    final = store.load()
    bundle = write_study_report(state=final, output_directory=output / "report")
    summary = {
        "notice": NOTICE,
        "phase": final.phase.value,
        "preregistration_hash": spec.fingerprint(),
        "state_hash": final.fingerprint(),
        "discovery_records": sum(item.stage == StudyStage.DISCOVERY for item in final.records),
        "confirmation_records": sum(item.stage == StudyStage.CONFIRMATION for item in final.records),
        "worker_seed_runs": sum(len(item.evidence) for item in final.records),
        "selected_records": {arm.arm_id: arm.selection.selected_record_id for arm in final.arms},
        "external_calls": [],
        "report": bundle.to_dict(),
    }
    (output / "m8-demo.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
