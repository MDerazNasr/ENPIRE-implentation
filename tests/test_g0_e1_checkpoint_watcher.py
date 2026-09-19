import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.watch_g0_e1_checkpoints import find_checkpoint


class G0E1CheckpointWatcherTests(unittest.TestCase):
    def test_finds_one_exact_checkpoint_directory(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            expected = root / "experiment/checkpoints/global_step_250"
            expected.mkdir(parents=True)
            self.assertEqual(find_checkpoint(root, 250), expected)
            self.assertIsNone(find_checkpoint(root, 500))

    def test_duplicate_step_directory_fails_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "one/global_step_250").mkdir(parents=True)
            (root / "two/global_step_250").mkdir(parents=True)
            with self.assertRaisesRegex(RuntimeError, "multiple"):
                find_checkpoint(root, 250)


if __name__ == "__main__":
    unittest.main()
