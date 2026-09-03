import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent.d1_config import RLINF_COMMIT
from agent.rlt_objective_seam import (
    BACKWARD_PATH,
    CONFIG_PATH,
    PINNED_FILES,
    REQUIRED_SOURCE,
    WORKER_PATH,
    RLTObjectiveSeamError,
    audit_rlinf_objective_seam,
)


class RLTObjectiveSeamTests(unittest.TestCase):
    def _fixture(self, root: Path) -> dict[Path, str]:
        expected = {}
        for relative, statements in REQUIRED_SOURCE.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("\n".join(statements) + "\n")
            import hashlib

            expected[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return expected

    @staticmethod
    def _git_result(commit: str = RLINF_COMMIT):
        return subprocess.CompletedProcess([], 0, stdout=commit + "\n", stderr="")

    def test_contract_freezes_all_three_upstream_files(self):
        self.assertEqual(set(PINNED_FILES), {WORKER_PATH, BACKWARD_PATH, CONFIG_PATH})
        self.assertTrue(all(len(value) == 64 for value in PINNED_FILES.values()))

    def test_exact_fixture_passes_and_returns_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = self._fixture(root)
            with patch("agent.rlt_objective_seam.subprocess.run", return_value=self._git_result()):
                result = audit_rlinf_objective_seam(root, expected_files=expected)
        self.assertEqual(result["rlinf_commit"], RLINF_COMMIT)
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["files"][str(WORKER_PATH)], expected[WORKER_PATH])

    def test_commit_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory, patch(
            "agent.rlt_objective_seam.subprocess.run",
            return_value=self._git_result("f" * 40),
        ):
            with self.assertRaisesRegex(RLTObjectiveSeamError, "commit mismatch"):
                audit_rlinf_objective_seam(Path(directory), expected_files={})

    def test_source_drift_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            expected = self._fixture(root)
            (root / WORKER_PATH).write_text("changed\n")
            with patch(
                "agent.rlt_objective_seam.subprocess.run",
                return_value=self._git_result(),
            ):
                with self.assertRaisesRegex(RLTObjectiveSeamError, "hash mismatch"):
                    audit_rlinf_objective_seam(root, expected_files=expected)


if __name__ == "__main__":
    unittest.main()
