from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.d1_adversarial_fixture_launcher import (
    mutate_fixture_artifacts,
    scenario_from_run_id,
)


class D1AdversarialFixtureTests(unittest.TestCase):
    def test_run_id_selects_only_named_scenarios(self) -> None:
        self.assertEqual(
            scenario_from_run_id("d1-cost-overrun-config-01.s2026"),
            "cost-overrun",
        )
        with self.assertRaises(ValueError):
            scenario_from_run_id("unscoped-fixture")

    def test_fault_mutations_are_explicit(self) -> None:
        for scenario, expected_code in (
            ("hash-mismatch", 0),
            ("cost-overrun", 0),
            ("failure-normalization", 7),
        ):
            with self.subTest(scenario=scenario), tempfile.TemporaryDirectory() as temp:
                root = Path(temp)
                run_id = f"d1-{scenario}-config-01.s2026"
                run_directory = root / "d1" / run_id
                run_directory.mkdir(parents=True)
                manifest_path = run_directory / "manifest.json"
                manifest_path.write_text(
                    json.dumps(
                        {
                            "config_sha256": "a" * 64,
                            "run_cost_usd": 0,
                            "final_cost_usd": 0,
                            "status": "complete",
                            "exit_code": 0,
                        }
                    ),
                    encoding="utf-8",
                )
                code = mutate_fixture_artifacts(root, run_id, scenario)
                mutated = json.loads(manifest_path.read_text(encoding="utf-8"))
                self.assertEqual(code, expected_code)
                if scenario == "hash-mismatch":
                    self.assertEqual(mutated["config_sha256"], "0" * 64)
                elif scenario == "cost-overrun":
                    self.assertEqual(mutated["run_cost_usd"], 999)
                else:
                    self.assertEqual(mutated["status"], "failed")
                    self.assertEqual(mutated["exit_code"], 7)

    def test_missing_artifact_removes_only_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            run_id = "d1-missing-artifact-config-01.s2026"
            run_directory = root / "d1" / run_id
            run_directory.mkdir(parents=True)
            manifest = run_directory / "manifest.json"
            log = run_directory / "run.log"
            manifest.write_text("{}", encoding="utf-8")
            log.write_text("retained\n", encoding="utf-8")
            self.assertEqual(
                mutate_fixture_artifacts(root, run_id, "missing-artifact"), 0
            )
            self.assertFalse(manifest.exists())
            self.assertEqual(log.read_text(encoding="utf-8"), "retained\n")


if __name__ == "__main__":
    unittest.main()
