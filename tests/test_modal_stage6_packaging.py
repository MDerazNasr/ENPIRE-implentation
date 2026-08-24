from __future__ import annotations

import hashlib
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NORM_STATS = (
    ROOT
    / "configs"
    / "d1"
    / "assets"
    / "maniskill_peginsertionside_joint.norm_stats.json"
)
EXPECTED_NORM_SHA256 = (
    "d5d6a96be65d2066b6dc0fd547e2eeb25473ea32558e819bbddd78f811aadfbd"
)


class ModalStage6PackagingTests(unittest.TestCase):
    def test_norm_stats_is_stable_and_hash_pinned(self) -> None:
        self.assertTrue(NORM_STATS.is_file())
        self.assertEqual(
            hashlib.sha256(NORM_STATS.read_bytes()).hexdigest(),
            EXPECTED_NORM_SHA256,
        )

    def test_modal_image_has_no_untracked_tmp_inputs(self) -> None:
        source = (ROOT / "modal_stage6.py").read_text()
        self.assertNotIn('.add_local_file("tmp/', source)
        self.assertNotIn("control_d1_runs.jsonl", source)
        self.assertIn(str(NORM_STATS.relative_to(ROOT)), source)


if __name__ == "__main__":
    unittest.main()
