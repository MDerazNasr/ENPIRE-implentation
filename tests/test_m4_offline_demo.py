from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts.run_m4_offline_demo import run
from supervisor.reporting import SYNTHETIC_NOTICE


class OfflineDemoTests(unittest.TestCase):
    def test_one_command_demo_exercises_repair_decision_and_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "demo"
            result = run(output)
            self.assertEqual(result["notice"], SYNTHETIC_NOTICE)
            self.assertEqual(result["status"], "decided")
            self.assertEqual(result["decision"], "keep")
            self.assertEqual(result["invalid_attempts_before_acceptance"], 1)
            self.assertTrue(result["stable_head_unchanged"])
            report = json.loads((output / "report" / "report.json").read_text())
            self.assertEqual(report["totals"]["invalid_attempts"], 1)
            self.assertEqual(report["totals"]["decision_counts"], {"keep": 1})
            self.assertIsNone(report["totals"]["gpu_utilization_percent"])


if __name__ == "__main__":
    unittest.main()
