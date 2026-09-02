from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from supervisor.canonical import ContractError, canonical_json
from supervisor.contracts import CampaignState, TrialState
from supervisor.ledger import EntityType, EventLedger, LedgerCorruption
from supervisor.state import CAMPAIGN_STATE_MACHINE, TRIAL_STATE_MACHINE, TransitionError


class StateMachineTests(unittest.TestCase):
    def test_campaign_happy_path_and_terminal_state(self) -> None:
        state = CAMPAIGN_STATE_MACHINE.replay(
            [
                (CampaignState.DRAFT, CampaignState.VALIDATED),
                (CampaignState.VALIDATED, CampaignState.APPROVED),
                (CampaignState.APPROVED, CampaignState.ACTIVE),
                (CampaignState.ACTIVE, CampaignState.COMPLETED),
            ]
        )
        self.assertEqual(state, CampaignState.COMPLETED)
        with self.assertRaises(TransitionError):
            CAMPAIGN_STATE_MACHINE.transition(state, CampaignState.ACTIVE)

    def test_trial_happy_paths_and_invalid_skip(self) -> None:
        prefix = [
            (TrialState.PROPOSING, TrialState.PROPOSAL_VALIDATED),
            (TrialState.PROPOSAL_VALIDATED, TrialState.QUEUED),
            (TrialState.QUEUED, TrialState.RUNNING),
            (TrialState.RUNNING, TrialState.EVALUATED),
        ]
        for terminal in (
            TrialState.KEPT,
            TrialState.REVERTED,
            TrialState.INCONCLUSIVE,
            TrialState.FAILED,
        ):
            with self.subTest(terminal=terminal):
                self.assertEqual(
                    TRIAL_STATE_MACHINE.replay(
                        [*prefix, (TrialState.EVALUATED, terminal)]
                    ),
                    terminal,
                )
        with self.assertRaises(TransitionError):
            TRIAL_STATE_MACHINE.transition(TrialState.PROPOSING, TrialState.RUNNING)


class LedgerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "campaign.jsonl"
        self.at = datetime(2026, 8, 4, 12, tzinfo=timezone.utc)

    def campaign_ledger(self) -> EventLedger:
        return EventLedger(
            self.path,
            campaign_id="campaign-1",
            entity_type=EntityType.CAMPAIGN,
            entity_id="campaign-1",
        )

    def populate(self) -> EventLedger:
        ledger = self.campaign_ledger()
        ledger.append_transition(
            CampaignState.VALIDATED,
            actor="validator",
            reason="contract passed",
            at=self.at,
            metadata={"spec_hash": "a" * 64},
        )
        ledger.append_transition(
            CampaignState.APPROVED,
            actor="Mohamed",
            reason="bounded envelope approved",
            at=self.at,
        )
        return ledger

    def test_append_restart_and_replay(self) -> None:
        metadata = {"nested": ["original"]}
        ledger = self.campaign_ledger()
        ledger.append_transition(
            CampaignState.VALIDATED,
            actor="validator",
            reason="contract passed",
            at=self.at,
            metadata=metadata,
        )
        metadata["nested"].append("mutated-after-append")
        ledger.append_transition(
            CampaignState.APPROVED,
            actor="Mohamed",
            reason="bounded envelope approved",
            at=self.at,
        )
        first_snapshot = ledger.read()
        self.assertEqual(first_snapshot.state, CampaignState.APPROVED)
        self.assertEqual(first_snapshot.sequence, 2)
        self.assertNotEqual(first_snapshot.head_hash, "0" * 64)
        self.assertEqual(first_snapshot.events[0].metadata["nested"], ("original",))
        with self.assertRaises(AttributeError):
            first_snapshot.events[0].metadata["nested"].append("not-allowed")

        restarted = self.campaign_ledger()
        restarted.append_transition(
            CampaignState.ACTIVE,
            actor="coordinator",
            reason="campaign started",
            at=self.at,
        )
        snapshot = restarted.read()
        self.assertEqual(snapshot.state, CampaignState.ACTIVE)
        self.assertEqual(snapshot.sequence, 3)
        self.assertEqual(snapshot.events[1].previous_hash, snapshot.events[0].event_hash)

    def test_wrong_entity_state_and_invalid_transition_are_rejected(self) -> None:
        ledger = self.campaign_ledger()
        with self.assertRaisesRegex(ContractError, "campaign state"):
            ledger.append_transition(
                TrialState.QUEUED, actor="bad", reason="wrong enum", at=self.at
            )
        with self.assertRaises(TransitionError):
            ledger.append_transition(
                CampaignState.ACTIVE, actor="bad", reason="skipped gates", at=self.at
            )
        self.assertFalse(self.path.exists() and self.path.read_text())

    def test_noncanonical_metadata_is_rejected_before_append(self) -> None:
        ledger = self.campaign_ledger()
        with self.assertRaisesRegex(ContractError, "canonical JSON"):
            ledger.append_transition(
                CampaignState.VALIDATED,
                actor="validator",
                reason="bad metadata",
                at=self.at,
                metadata={"loss": float("nan")},
            )
        self.assertEqual(ledger.read().sequence, 0)

    def test_content_tampering_is_detected(self) -> None:
        ledger = self.populate()
        lines = self.path.read_text().splitlines()
        first = json.loads(lines[0])
        first["actor"] = "attacker"
        lines[0] = canonical_json(first)
        self.path.write_text("\n".join(lines) + "\n")
        with self.assertRaisesRegex(LedgerCorruption, "hash does not match"):
            ledger.read()

    def test_malformed_event_contract_is_reported_as_ledger_corruption(self) -> None:
        ledger = self.populate()
        lines = self.path.read_text().splitlines()
        first = json.loads(lines[0])
        first["campaign_id"] = "../../escape"
        lines[0] = canonical_json(first)
        self.path.write_text("\n".join(lines) + "\n")
        with self.assertRaises(LedgerCorruption):
            ledger.read()

    def test_reorder_deletion_duplicate_and_partial_tail_are_detected(self) -> None:
        for corruption in ("reorder", "delete", "duplicate", "partial"):
            with self.subTest(corruption=corruption):
                path = Path(self.temp.name) / f"{corruption}.jsonl"
                ledger = EventLedger(
                    path,
                    campaign_id="campaign-1",
                    entity_type=EntityType.CAMPAIGN,
                    entity_id="campaign-1",
                )
                for state in (
                    CampaignState.VALIDATED,
                    CampaignState.APPROVED,
                    CampaignState.ACTIVE,
                ):
                    ledger.append_transition(
                        state, actor="test", reason=f"to {state.value}", at=self.at
                    )
                lines = path.read_text().splitlines()
                if corruption == "reorder":
                    lines[0], lines[1] = lines[1], lines[0]
                    path.write_text("\n".join(lines) + "\n")
                elif corruption == "delete":
                    path.write_text("\n".join([lines[0], lines[2]]) + "\n")
                elif corruption == "duplicate":
                    path.write_text("\n".join([lines[0], lines[0], *lines[1:]]) + "\n")
                else:
                    path.write_text("\n".join(lines))
                with self.assertRaises(LedgerCorruption):
                    ledger.read()

    def test_external_head_anchor_detects_complete_tail_deletion(self) -> None:
        ledger = self.populate()
        trusted = ledger.read()
        lines = self.path.read_text().splitlines()
        self.path.write_text(lines[0] + "\n")
        self.assertEqual(ledger.read().sequence, 1)
        with self.assertRaisesRegex(LedgerCorruption, "external anchor"):
            ledger.read(
                expected_head_hash=trusted.head_hash,
                expected_sequence=trusted.sequence,
            )

    def test_trial_ledger_is_independent_from_campaign_ledger(self) -> None:
        trial = EventLedger(
            Path(self.temp.name) / "trial.jsonl",
            campaign_id="campaign-1",
            entity_type=EntityType.TRIAL,
            entity_id="trial-1",
        )
        trial.append_transition(
            TrialState.PROPOSAL_VALIDATED,
            actor="validator",
            reason="proposal accepted",
            at=self.at,
        )
        self.assertEqual(trial.read().state, TrialState.PROPOSAL_VALIDATED)
        self.assertEqual(self.campaign_ledger().read().state, CampaignState.DRAFT)


if __name__ == "__main__":
    unittest.main()
