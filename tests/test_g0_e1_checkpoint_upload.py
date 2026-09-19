import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.upload_g0_e1_checkpoint import (
    UploadError,
    build_plan,
    inventory,
    validate_prefix,
)


class G0E1CheckpointUploadTests(unittest.TestCase):
    def test_inventory_hashes_regular_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "actor").mkdir()
            (root / "actor/weights.bin").write_bytes(b"weights")
            files, size = inventory(root)
            self.assertEqual(size, 7)
            self.assertEqual(files[0]["path"], "actor/weights.bin")
            self.assertEqual(
                files[0]["sha256"],
                "9a129038d9a00aed0cf6a7ea059ca50a813449061ab87848cf1a13eafdf33b2c",
            )

    def test_prefix_is_confined_to_runs_namespace(self):
        self.assertEqual(validate_prefix("runs/e1/"), "runs/e1/")
        for value in ("final/", "/runs/e1/", "runs/../final/", "runs/e1"):
            with self.subTest(value=value), self.assertRaises(UploadError):
                validate_prefix(value)

    @patch("scripts.upload_g0_e1_checkpoint.list_prefix")
    def test_plan_refuses_existing_step_prefix(self, listing):
        listing.return_value = [{"Key": "partial", "Size": 1}]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "weights").write_bytes(b"x")
            with self.assertRaisesRegex(UploadError, "partial-prefix"):
                build_plan(
                    root,
                    step=250,
                    bucket="bucket",
                    campaign_prefix="runs/e1/",
                    profile="worker",
                    max_total_bytes=100,
                )

    @patch("scripts.upload_g0_e1_checkpoint.list_prefix")
    def test_plan_enforces_campaign_byte_cap(self, listing):
        listing.side_effect = [[], [{"Key": "prior", "Size": 9}]]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "weights").write_bytes(b"xx")
            with self.assertRaisesRegex(UploadError, "byte cap"):
                build_plan(
                    root,
                    step=500,
                    bucket="bucket",
                    campaign_prefix="runs/e1/",
                    profile="worker",
                    max_total_bytes=10,
                )


if __name__ == "__main__":
    unittest.main()
