from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.check_d0_candidate_config import inspect_config


ROOT = Path(__file__).resolve().parents[1]


class D0AcceptanceTests(unittest.TestCase):
    def test_checker_validates_and_dry_resolves_without_a_process(self) -> None:
        source = json.loads((ROOT / "configs/d1/control.yaml").read_text())
        source["scientific_values"]["online_bc_weight"] = 2.25
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "candidate.json"
            path.write_text(json.dumps(source), encoding="utf-8")
            contract = inspect_config(path, dry_resolve=False)
            dry = inspect_config(path, dry_resolve=True)
        self.assertEqual(contract["status"], "passed")
        self.assertFalse(contract["process_launched"])
        self.assertTrue(dry["dry_resolved"])
        self.assertFalse(dry["process_launched"])
        self.assertEqual(len(dry["logical_command_hash"]), 64)
        self.assertIn("actor.seed=2026", dry["logical_command"])


if __name__ == "__main__":
    unittest.main()
