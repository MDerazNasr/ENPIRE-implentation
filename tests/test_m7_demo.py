from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class M7DemoTests(unittest.TestCase):
    def test_two_worker_loss_retry_and_frozen_decisions(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "demo"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "run_m7_scheduler_demo.py"),
                    "--output",
                    str(output),
                    "--repository",
                    str(ROOT),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env={
                    "PATH": "/usr/bin:/bin",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "PYTHONDONTWRITEBYTECODE": "1",
                },
            )
            payload = json.loads((output / "m7-demo.json").read_text())
            self.assertIn("NOT RLT PERFORMANCE EVIDENCE", payload["notice"])
            self.assertEqual(payload["first_batch_parallelism"], 2)
            self.assertEqual(payload["lost_trial_attempts"], 2)
            self.assertTrue(payload["stale_completion_rejected"])
            self.assertTrue(payload["stable_head_unchanged"])
            self.assertEqual(set(payload["final_trial_states"].values()), {"completed"})
            self.assertEqual(
                payload["decisions"]["config-arm"]["decision_record"]["decision"],
                "keep",
            )
            self.assertEqual(
                payload["decisions"]["code-arm"]["decision_record"]["decision"],
                "revert",
            )
            self.assertEqual(payload["external_calls"], [])
            self.assertIn("first_batch_parallelism", completed.stdout)


if __name__ == "__main__":
    unittest.main()
