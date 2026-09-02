from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from supervisor.delivery import verify_artifact_manifest


ROOT = Path(__file__).resolve().parents[1]


def git(repository: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()


def clean_repository(root: Path) -> Path:
    repository = root / "clean-supervisor-proof"
    repository.mkdir()
    git(repository, "init", "-q", "-b", "feature/d2-agent-supervisor")
    (repository / "README.md").write_text("clean M9 proof repository\n", encoding="utf-8")
    git(repository, "add", "README.md")
    git(
        repository,
        "-c", "user.name=M9 Test",
        "-c", "user.email=m9-test@invalid.local",
        "commit", "-q", "-m", "clean proof",
    )
    return repository


def run_demo(output: Path, repository: Path, *extra: str, check: bool = True):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_m9_ludvig_demo.py"),
            "--output", str(output),
            "--repository", str(repository),
            *extra,
        ],
        check=check,
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


class M9DemoTests(unittest.TestCase):
    def test_one_command_demo_is_repeatable_and_manifest_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = clean_repository(root)
            head = git(repository, "rev-parse", "HEAD")
            first_output = root / "first"
            second_output = root / "second"
            first = run_demo(first_output, repository)
            second = run_demo(second_output, repository)
            first_summary = json.loads(first.stdout)
            second_summary = json.loads(second.stdout)
            first_payload = json.loads((first_output / "m9-demo.json").read_text())
            self.assertEqual(first_summary["status"], "complete")
            self.assertEqual(first_summary["delivery_fingerprint"], second_summary["delivery_fingerprint"])
            self.assertFalse(first_summary["scientific_claim_permitted"])
            self.assertEqual(first_summary["external_calls"], [])
            self.assertTrue(first_summary["stable_head_unchanged"])
            self.assertEqual(first_payload["repository"]["head"], head)
            self.assertEqual(first_payload["components"]["m4_policy_improvement"]["status"], "decided")
            self.assertTrue(first_payload["components"]["m7_distributed_execution"]["stale_completion_rejected"])
            self.assertEqual(first_payload["components"]["m8_three_arm_study"]["discovery_records"], 9)
            self.assertEqual(first_payload["d1_replay"]["status"], "not_requested")
            verified_artifacts = verify_artifact_manifest(first_output)
            self.assertGreaterEqual(len(verified_artifacts), 15)
            for artifact in verified_artifacts:
                path = first_output / artifact.path
                if path.suffix.lower() not in {".html", ".json", ".md", ".svg"}:
                    continue
                public_text = path.read_text(encoding="utf-8")
                self.assertNotIn(str(root), public_text)
                self.assertNotIn(str(repository), public_text)
            verified = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "verify_m9_bundle.py"),
                    str(first_output),
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
            self.assertEqual(json.loads(verified.stdout)["status"], "verified")
            self.assertEqual(git(repository, "rev-parse", "HEAD"), head)
            self.assertEqual(git(repository, "status", "--porcelain"), "")

    def test_unavailable_d1_has_safe_fallback_and_strict_mode_blocks_early(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = clean_repository(root)
            missing_d1 = root / "missing-d1"
            fallback_output = root / "fallback"
            fallback = run_demo(
                fallback_output,
                repository,
                "--d1-repository", str(missing_d1),
            )
            fallback_summary = json.loads(fallback.stdout)
            fallback_payload = json.loads((fallback_output / "m9-demo.json").read_text())
            self.assertEqual(fallback_summary["status"], "complete")
            self.assertEqual(fallback_summary["d1_status"], "invalid")
            self.assertFalse(fallback_payload["scientific_claim_permitted"])
            self.assertIn("not ready", (fallback_output / "demo-report.md").read_text())
            self.assertNotIn(
                str(missing_d1),
                (fallback_output / "d1-replay.json").read_text(encoding="utf-8"),
            )

            strict_output = root / "strict"
            strict = run_demo(
                strict_output,
                repository,
                "--d1-repository", str(missing_d1),
                "--require-d1-ready",
                check=False,
            )
            self.assertEqual(strict.returncode, 2)
            blocked = json.loads((strict_output / "m9-blocked.json").read_text())
            self.assertEqual(blocked["status"], "blocked")
            self.assertFalse((strict_output / "components").exists())

    def test_dirty_repository_is_rejected_before_outputs_or_components(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = clean_repository(root)
            (repository / "README.md").write_text("dirty\n", encoding="utf-8")
            output = root / "refused"
            completed = run_demo(output, repository, check=False)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("must be clean", completed.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
