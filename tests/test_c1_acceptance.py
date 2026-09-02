from __future__ import annotations

import tempfile
import subprocess
import unittest
from pathlib import Path

from supervisor.c1_acceptance import (
    C1_ARM_ID,
    C1_BASE_COMMIT,
    C1_TARGET_PATH,
    build_c1_context,
    context_record,
    repository_snapshot,
)


ROOT = Path(__file__).resolve().parents[1]


class C1AcceptanceTests(unittest.TestCase):
    def test_curated_context_is_deterministic_and_acceptance_only(self) -> None:
        first_campaign, first = build_c1_context(ROOT)
        second_campaign, second = build_c1_context(ROOT)
        self.assertEqual(context_record(first_campaign, first), context_record(second_campaign, second))
        self.assertEqual(first_campaign.baseline_commit, C1_BASE_COMMIT)
        self.assertEqual(first_campaign.editable_paths, (C1_TARGET_PATH,))
        self.assertEqual(first_campaign.seeds, (2026,))
        self.assertIn("provider-contract acceptance only", first.rendered_prompt)
        self.assertIn("formal result remains inconclusive", first.rendered_prompt)
        self.assertIn(f"Use arm_id {C1_ARM_ID}", first.rendered_prompt)
        self.assertLessEqual(first.byte_count, 65_536)

    def test_repository_snapshot_detects_untracked_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repository = Path(directory)
            subprocess.run(["git", "init", "-q"], cwd=repository, check=True)
            (repository / "tracked.txt").write_text("base", encoding="utf-8")
            subprocess.run(["git", "add", "tracked.txt"], cwd=repository, check=True)
            subprocess.run(
                [
                    "git",
                    "-c",
                    "user.name=C1 Test",
                    "-c",
                    "user.email=c1-test@invalid.local",
                    "commit",
                    "-q",
                    "-m",
                    "base",
                ],
                cwd=repository,
                check=True,
            )
            clean = repository_snapshot(repository)
            self.assertTrue(clean["clean"])
            (repository / "mutation.txt").write_text("changed", encoding="utf-8")
            changed = repository_snapshot(repository)
            self.assertFalse(changed["clean"])
            self.assertNotEqual(clean["status_sha256"], changed["status_sha256"])


if __name__ == "__main__":
    unittest.main()
