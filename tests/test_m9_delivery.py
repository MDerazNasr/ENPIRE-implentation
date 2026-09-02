from __future__ import annotations

import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from supervisor.delivery import (
    DeliveryError,
    M9_NOTICE,
    architecture_svg,
    build_delivery_payload,
    verify_artifact_manifest,
    write_delivery_bundle,
)


HEAD = "1" * 40


def m4_summary() -> dict:
    return {
        "notice": "SYNTHETIC OFFLINE DEMONSTRATION — NOT RESEARCH EVIDENCE",
        "status": "decided",
        "decision": "keep",
        "invalid_attempts_before_acceptance": 1,
        "stable_head_unchanged": True,
    }


def m7_summary() -> dict:
    def evaluation(decision: str) -> dict:
        return {"decision_record": {"decision": decision}}

    return {
        "notice": "SYNTHETIC M7 ORCHESTRATION DEMO — NOT RLT PERFORMANCE EVIDENCE",
        "first_batch_parallelism": 2,
        "lost_trial_attempts": 2,
        "stale_completion_rejected": True,
        "final_trial_states": {"a": "completed", "b": "completed"},
        "decisions": {"config": evaluation("keep"), "code": evaluation("revert")},
        "stable_head_unchanged": True,
        "external_calls": [],
    }


def m8_summary() -> dict:
    return {
        "notice": "SYNTHETIC M8 STUDY REHEARSAL — NOT RL OR RESEARCH EVIDENCE",
        "phase": "complete",
        "preregistration_hash": "a" * 64,
        "discovery_records": 9,
        "confirmation_records": 3,
        "worker_seed_runs": 30,
        "selected_records": {
            "fixed-rule-config": "rule-d1",
            "claude-config": "config-d2",
            "claude-code": "code-d3",
        },
        "external_calls": [],
    }


class M9DeliveryTests(unittest.TestCase):
    def payload(self, d1=None) -> dict:
        return build_delivery_payload(
            repository_head=HEAD,
            repository_branch="feature/d2-agent-supervisor",
            repository_clean_before=True,
            repository_clean_after=True,
            m4=m4_summary(),
            m7=m7_summary(),
            m8=m8_summary(),
            d1=d1,
        )

    def test_payload_preserves_claim_boundary_and_semantic_fingerprint(self) -> None:
        first = self.payload()
        second = self.payload()
        self.assertEqual(first["delivery_fingerprint"], second["delivery_fingerprint"])
        self.assertEqual(first["notice"], M9_NOTICE)
        self.assertFalse(first["scientific_claim_permitted"])
        self.assertEqual(first["external_calls"], [])
        self.assertEqual(first["d1_replay"]["status"], "not_requested")
        self.assertIn("that RLT improved the frozen VLA", first["what_this_does_not_prove"])

    def test_ready_d1_replay_does_not_turn_synthetic_study_into_science(self) -> None:
        ready = {
            "status": "ready",
            "gate_hash": "b" * 64,
            "reasons": [],
            "replay": {"equivalent": True},
        }
        payload = self.payload(ready)
        self.assertEqual(payload["d1_replay"]["status"], "ready")
        self.assertEqual(
            payload["evidence_mode"],
            "synthetic-control-plane-plus-ready-d1-replay",
        )
        self.assertFalse(payload["scientific_claim_permitted"])

    def test_malformed_component_or_dirty_repository_fails_closed(self) -> None:
        bad_m7 = m7_summary()
        bad_m7["external_calls"] = ["ssh"]
        with self.assertRaisesRegex(DeliveryError, "external calls"):
            build_delivery_payload(
                repository_head=HEAD,
                repository_branch="main",
                repository_clean_before=True,
                repository_clean_after=True,
                m4=m4_summary(),
                m7=bad_m7,
                m8=m8_summary(),
                d1=None,
            )
        with self.assertRaisesRegex(DeliveryError, "clean"):
            build_delivery_payload(
                repository_head=HEAD,
                repository_branch="main",
                repository_clean_before=False,
                repository_clean_after=True,
                m4=m4_summary(),
                m7=m7_summary(),
                m8=m8_summary(),
                d1=None,
            )

    def test_manifest_reconciles_every_file_and_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            component = output / "components" / "fixture.json"
            component.parent.mkdir()
            component.write_text('{"fixture":true}\n', encoding="utf-8")
            bundle = write_delivery_bundle(
                output_directory=output,
                payload=self.payload(),
                component_artifacts=(("components/fixture.json", "fixture"),),
            )
            self.assertEqual(len(bundle.artifacts), 5)
            self.assertEqual(len(verify_artifact_manifest(output)), 5)
            ET.fromstring((output / "architecture.svg").read_text())
            component.write_text('{"fixture":false}\n', encoding="utf-8")
            with self.assertRaisesRegex(DeliveryError, "does not match"):
                verify_artifact_manifest(output)

    def test_architecture_is_static_valid_svg_with_accessible_title(self) -> None:
        root = ET.fromstring(architecture_svg())
        self.assertTrue(root.tag.endswith("svg"))
        titles = [item.text for item in root if item.tag.endswith("title")]
        self.assertIn("RLT coding-agent supervisor architecture", titles)


if __name__ == "__main__":
    unittest.main()
