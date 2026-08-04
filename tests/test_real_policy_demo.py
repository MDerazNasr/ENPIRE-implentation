from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from supervisor.toy_demo import ToyDemoError, verify_manifest


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
    repository = root / "clean-supervisor"
    repository.mkdir()
    git(repository, "init", "-q", "-b", "feature/d2-agent-supervisor")
    (repository / "README.md").write_text("clean demo proof\n", encoding="utf-8")
    git(repository, "add", "README.md")
    git(
        repository,
        "-c", "user.name=Demo Test",
        "-c", "user.email=demo-test@invalid.local",
        "commit", "-q", "-m", "clean proof",
    )
    return repository


def run_demo(output: Path, repository: Path, *, check: bool = True):
    return subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run_real_policy_demo.py"),
            "--output", str(output),
            "--repository", str(repository),
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


class RealPolicyDemoTests(unittest.TestCase):
    def test_real_demo_trains_models_keeps_candidate_and_is_repeatable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = clean_repository(root)
            head = git(repository, "rev-parse", "HEAD")
            first_output = root / "first"
            second_output = root / "second"
            first = json.loads(run_demo(first_output, repository).stdout)
            second = json.loads(run_demo(second_output, repository).stdout)
            payload = json.loads(
                (first_output / "public" / "real-policy-demo.json").read_text()
            )

            self.assertEqual(first["status"], "complete")
            self.assertEqual(first["decision"], "keep")
            self.assertGreater(first["mean_success_delta"], 0.80)
            self.assertLess(first["control_mean_success"], 0.20)
            self.assertGreaterEqual(first["candidate_mean_success"], 0.99)
            self.assertEqual(first["result_fingerprint"], second["result_fingerprint"])
            self.assertGreaterEqual(first["maximum_concurrent_workers"], 2)
            self.assertEqual(first["external_calls"], [])
            self.assertFalse(first["rlt_claim_permitted"])
            self.assertFalse(payload["proposal_generation"]["live_provider_call"])
            self.assertEqual(payload["execution"]["worker_count"], 6)
            self.assertEqual(
                payload["proposal"]["config_overrides"]["training.exploration_std"],
                0.35,
            )
            self.assertEqual(payload["preparation"]["changed_paths"], ["candidate/config.json"])
            self.assertTrue(payload["repository"]["stable_head_unchanged"])
            self.assertEqual(git(repository, "rev-parse", "HEAD"), head)
            self.assertEqual(git(repository, "status", "--porcelain"), "")

            artifacts = verify_manifest(first_output)
            self.assertEqual(len(artifacts), 14)
            for artifact in artifacts:
                path = first_output / artifact.path
                if path.suffix.lower() not in {".html", ".json", ".md", ".svg"}:
                    continue
                content = path.read_text(encoding="utf-8")
                self.assertNotIn(str(root), content)
                self.assertNotIn(str(first_output), content)

            presentation = (
                first_output / "public" / "presentation.html"
            ).read_text(encoding="utf-8")
            self.assertIn("real local execution", presentation)
            self.assertIn("What this does not prove", presentation)
            self.assertIn("not RLinf/RLT", presentation)

    def test_manifest_detects_tampering(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = clean_repository(root)
            output = root / "demo"
            run_demo(output, repository)
            report = output / "public" / "report.md"
            report.write_text("tampered\n", encoding="utf-8")
            with self.assertRaises(ToyDemoError):
                verify_manifest(output)

    def test_dirty_repository_is_rejected_before_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repository = clean_repository(root)
            (repository / "README.md").write_text("dirty\n", encoding="utf-8")
            output = root / "rejected"
            completed = run_demo(output, repository, check=False)
            self.assertEqual(completed.returncode, 2)
            self.assertIn("must be clean", completed.stderr)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
