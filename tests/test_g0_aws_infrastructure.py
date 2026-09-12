from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.check_g0_aws_infrastructure import (
    G0AwsInfrastructureError,
    TEMPLATES,
    _assert_locked_bucket,
    check_templates,
)


ROOT = Path(__file__).resolve().parents[1]


class G0AwsInfrastructureTests(unittest.TestCase):
    def test_templates_pass_offline_and_grant_no_authority(self) -> None:
        result = check_templates(ROOT)
        payload = result["payload"]
        self.assertEqual(payload["locked_bucket_count"], 5)
        self.assertFalse(payload["cloud_resources_created"])
        self.assertFalse(payload["worker_final_input_access"])
        for field in (
            "scientific_execution_authorized", "campaign_activation_authorized",
            "gpu_execution_authorized", "paid_execution_authorized",
            "provider_call_authorized", "model_egress_authorized", "promotion_authorized",
        ):
            self.assertFalse(payload[field])

    def test_weakened_object_lock_fails_closed(self) -> None:
        template = json.loads((ROOT / TEMPLATES["evaluator"]).read_text(encoding="utf-8"))
        bucket = copy.deepcopy(template["Resources"]["FinalInputBucket"])
        bucket["Properties"]["ObjectLockConfiguration"]["Rule"]["DefaultRetention"]["Mode"] = "GOVERNANCE"
        with self.assertRaises(G0AwsInfrastructureError):
            _assert_locked_bucket(bucket, "FinalInputBucket")

    def test_cli_is_create_only_and_byte_stable(self) -> None:
        with tempfile.TemporaryDirectory(prefix="enpire-g0-aws-test-") as temporary:
            output = Path(temporary) / "receipt.json"
            command = [sys.executable, "scripts/check_g0_aws_infrastructure.py", "--output", str(output)]
            first = subprocess.run(command, cwd=ROOT, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertEqual(json.loads(first.stdout), json.loads(output.read_text(encoding="utf-8")))
            second = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("output already exists", second.stderr)


if __name__ == "__main__":
    unittest.main()
