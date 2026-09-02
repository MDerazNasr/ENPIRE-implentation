from __future__ import annotations

import csv
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class M8DemoTests(unittest.TestCase):
    def test_complete_three_arm_rehearsal_and_report_reconcile(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "m8"
            completed = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "run_m8_study_demo.py"), "--output", str(output)],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"},
            )
            summary = json.loads((output / "m8-demo.json").read_text())
            report = json.loads((output / "report" / "study-report.json").read_text())
            with (output / "report" / "study-trials.csv").open(newline="") as handle:
                rows = list(csv.DictReader(handle))
            self.assertIn("NOT RL OR RESEARCH EVIDENCE", summary["notice"])
            self.assertEqual(summary["phase"], "complete")
            self.assertEqual(summary["discovery_records"], 9)
            self.assertEqual(summary["confirmation_records"], 3)
            self.assertEqual(len(rows), 12)
            self.assertEqual(set(summary["selected_records"]), {"fixed-rule-config", "claude-config", "claude-code"})
            self.assertEqual(report["preregistration_hash"], summary["preregistration_hash"])
            self.assertFalse(report["scientific_claim_permitted"])
            self.assertEqual(report["totals"]["invalid_records"], 2)
            self.assertEqual(report["totals"]["failed_records"], 1)
            self.assertEqual(report["totals"]["human_interventions"], 0)
            self.assertEqual(report["totals"]["worker_seed_runs"], summary["worker_seed_runs"])
            self.assertEqual(summary["external_calls"], [])
            self.assertIn("preregistration_hash", completed.stdout)
            manifest = json.loads((output / "report" / "artifact-manifest.json").read_text())
            for artifact in manifest["artifacts"]:
                data = Path(artifact["path"]).read_bytes()
                self.assertEqual(hashlib.sha256(data).hexdigest(), artifact["sha256"])


if __name__ == "__main__":
    unittest.main()
