from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from scripts.run_m8_study_demo import (
    build_campaign,
    build_spec,
    evaluated_record,
    invalid_record,
)
from supervisor.canonical import fingerprint
from supervisor.study import (
    CLAUDE_CODE_ARM,
    CLAUDE_CONFIG_ARM,
    FIXED_RULE_CONFIG_ARM,
    EditMode,
    StudyActivation,
    StudyError,
    StudyPhase,
    StudyRecordStatus,
    StudyStage,
    StudyStateStore,
    ThreeArmStudy,
    equal_budget_audit,
)


NOW = datetime(2026, 8, 4, 12, tzinfo=timezone.utc)


class M8StudyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.campaign = build_campaign()
        self.spec = build_spec(self.campaign)
        self.activation = StudyActivation.create(
            spec=self.spec, synthetic=True, activated_by="test", activated_at=NOW
        )
        self.store = StudyStateStore(self.root / "study.json")
        self.store.initialize(self.spec, self.activation)
        self.study = ThreeArmStudy(self.store)

    def _fill_with_one_valid_candidate_per_arm(self) -> None:
        for index, arm_id in enumerate(
            (FIXED_RULE_CONFIG_ARM, CLAUDE_CONFIG_ARM, CLAUDE_CODE_ARM), start=1
        ):
            mode = self.spec.arm(arm_id).edit_mode
            candidate = str(index) * 40
            claude = arm_id != FIXED_RULE_CONFIG_ARM
            self.study.record_discovery(
                evaluated_record(
                    self.campaign,
                    record_id=f"{arm_id}-d1",
                    arm_id=arm_id,
                    stage=StudyStage.DISCOVERY,
                    slot=1,
                    edit_mode=mode,
                    parent=self.spec.baseline_commit,
                    candidate=candidate,
                    control_success=.4,
                    candidate_success=.5,
                    proposal_hash=(fingerprint({"session": arm_id}) if claude else None),
                )
            )
            for slot in (2, 3):
                self.study.record_discovery(
                    invalid_record(
                        record_id=f"{arm_id}-d{slot}",
                        arm_id=arm_id,
                        slot=slot,
                        edit_mode=mode,
                        incumbent=candidate,
                        claude=claude,
                    )
                )

    def test_preregistration_freezes_three_arms_and_matched_budgets(self) -> None:
        audit = equal_budget_audit(self.spec)
        self.assertTrue(audit["passed"])
        self.assertEqual([arm.discovery_slots for arm in self.spec.arms], [3, 3, 3])
        self.assertEqual(len(self.spec.paired_seeds), 3)
        self.assertEqual(self.spec, type(self.spec).from_dict(self.spec.to_dict()))
        self.assertEqual(self.spec.fingerprint(), fingerprint(self.spec.to_dict()))

    def test_live_activation_requires_ready_d1_gate_hash(self) -> None:
        with self.assertRaisesRegex(StudyError, "ready D1 gate"):
            StudyActivation.create(
                spec=self.spec, synthetic=False, activated_by="test", activated_at=NOW
            )
        live = StudyActivation.create(
            spec=self.spec,
            synthetic=False,
            activated_by="test",
            activated_at=NOW,
            d1_gate_hash="d" * 64,
            d1_gate_status="ready",
        )
        self.assertFalse(live.synthetic)

    def test_invalid_record_consumes_slot_and_replay_is_idempotent(self) -> None:
        record = invalid_record(
            record_id="rule-invalid",
            arm_id=FIXED_RULE_CONFIG_ARM,
            slot=1,
            edit_mode=EditMode.CONFIG_ONLY,
            incumbent=self.spec.baseline_commit,
            claude=False,
        )
        first = self.study.record_discovery(record)
        replay = self.study.record_discovery(record)
        self.assertEqual(first.generation, replay.generation)
        self.assertEqual(first.arm(FIXED_RULE_CONFIG_ARM).discovery_record_ids, (record.record_id,))
        wrong_slot = replace(record, record_id="new-record", slot_number=1)
        with self.assertRaisesRegex(StudyError, "next discovery slot.*2"):
            self.study.record_discovery(wrong_slot)

    def test_arm_lineage_and_edit_mode_cannot_leak(self) -> None:
        promoted = "1" * 40
        first = evaluated_record(
            self.campaign,
            record_id="rule-d1",
            arm_id=FIXED_RULE_CONFIG_ARM,
            stage=StudyStage.DISCOVERY,
            slot=1,
            edit_mode=EditMode.CONFIG_ONLY,
            parent=self.spec.baseline_commit,
            candidate=promoted,
            control_success=.4,
            candidate_success=.5,
            proposal_hash=None,
        )
        state = self.study.record_discovery(first)
        self.assertEqual(state.arm(FIXED_RULE_CONFIG_ARM).incumbent_commit, promoted)
        leaked = invalid_record(
            record_id="config-d1",
            arm_id=CLAUDE_CONFIG_ARM,
            slot=1,
            edit_mode=EditMode.CONFIG_ONLY,
            incumbent=promoted,
            claude=True,
        )
        with self.assertRaisesRegex(StudyError, "crosses arm lineage"):
            self.study.record_discovery(leaked)
        wrong_mode = invalid_record(
            record_id="rule-d2",
            arm_id=FIXED_RULE_CONFIG_ARM,
            slot=2,
            edit_mode=EditMode.ACTOR_OBJECTIVE,
            incumbent=promoted,
            claude=False,
        )
        with self.assertRaisesRegex(StudyError, "edit mode"):
            self.study.record_discovery(wrong_mode)

    def test_tampering_and_preregistration_mutation_fail_closed(self) -> None:
        with self.assertRaisesRegex(StudyError, "immutable"):
            self.store.mutate(
                lambda state: replace(
                    state,
                    spec=replace(state.spec, research_question="changed after activation"),
                )
            )
        envelope = json.loads(self.store.path.read_text())
        envelope["payload"]["generation"] = 99
        self.store.path.write_text(json.dumps(envelope))
        with self.assertRaisesRegex(StudyError, "hash mismatch"):
            self.store.load()

    def test_failed_candidate_is_retained_but_does_not_advance(self) -> None:
        record = evaluated_record(
            self.campaign,
            record_id="config-failed",
            arm_id=CLAUDE_CONFIG_ARM,
            stage=StudyStage.DISCOVERY,
            slot=1,
            edit_mode=EditMode.CONFIG_ONLY,
            parent=self.spec.baseline_commit,
            candidate="3" * 40,
            control_success=.4,
            candidate_success=.6,
            proposal_hash=fingerprint({"session": "failed"}),
            failed=True,
        )
        state = self.study.record_discovery(record)
        self.assertEqual(record.status, StudyRecordStatus.FAILED)
        self.assertEqual(state.arm(CLAUDE_CONFIG_ARM).incumbent_commit, self.spec.baseline_commit)
        self.assertEqual(len(state.records), 1)

    def test_selection_cannot_run_before_all_nine_slots(self) -> None:
        with self.assertRaisesRegex(StudyError, "all nine"):
            self.study.select_candidates()
        self.assertEqual(self.store.load().phase, StudyPhase.ACTIVE_DISCOVERY)

    def test_confirmation_is_bound_to_selected_commit_and_baseline(self) -> None:
        self._fill_with_one_valid_candidate_per_arm()
        selected = self.study.select_candidates()
        arm = selected.arm(CLAUDE_CONFIG_ARM)
        self.assertEqual(arm.selection.selected_candidate_commit, "2" * 40)
        wrong = evaluated_record(
            self.campaign,
            record_id="config-confirm-wrong",
            arm_id=CLAUDE_CONFIG_ARM,
            stage=StudyStage.CONFIRMATION,
            slot=1,
            edit_mode=EditMode.CONFIG_ONLY,
            parent=self.spec.baseline_commit,
            candidate="9" * 40,
            control_success=.4,
            candidate_success=.6,
            proposal_hash=fingerprint({"confirmation": "wrong"}),
            confirmation=True,
        )
        with self.assertRaisesRegex(StudyError, "frozen selection"):
            self.study.record_confirmation(wrong)

    def test_arm_without_valid_candidate_is_not_replaced_from_another_arm(self) -> None:
        for slot in (1, 2, 3):
            self.study.record_discovery(
                invalid_record(
                    record_id=f"rule-d{slot}",
                    arm_id=FIXED_RULE_CONFIG_ARM,
                    slot=slot,
                    edit_mode=EditMode.CONFIG_ONLY,
                    incumbent=self.spec.baseline_commit,
                    claude=False,
                )
            )
        for index, arm_id in enumerate((CLAUDE_CONFIG_ARM, CLAUDE_CODE_ARM), start=2):
            mode = self.spec.arm(arm_id).edit_mode
            candidate = str(index) * 40
            self.study.record_discovery(
                evaluated_record(
                    self.campaign,
                    record_id=f"{arm_id}-d1",
                    arm_id=arm_id,
                    stage=StudyStage.DISCOVERY,
                    slot=1,
                    edit_mode=mode,
                    parent=self.spec.baseline_commit,
                    candidate=candidate,
                    control_success=.4,
                    candidate_success=.5,
                    proposal_hash=fingerprint({"session": arm_id}),
                )
            )
            for slot in (2, 3):
                self.study.record_discovery(
                    invalid_record(
                        record_id=f"{arm_id}-d{slot}",
                        arm_id=arm_id,
                        slot=slot,
                        edit_mode=mode,
                        incumbent=candidate,
                        claude=True,
                    )
                )
        selected = self.study.select_candidates()
        self.assertIsNone(selected.arm(FIXED_RULE_CONFIG_ARM).selection.selected_candidate_commit)
        self.assertIsNotNone(selected.arm(CLAUDE_CONFIG_ARM).selection.selected_candidate_commit)


if __name__ == "__main__":
    unittest.main()
