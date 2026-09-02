from __future__ import annotations

import copy
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from agent.d1_rules import decide_d1_candidate
from supervisor.canonical import fingerprint
from supervisor.d1_pack_builder import (
    DEFAULT_BUILD_SPEC,
    D1PackBuildError,
    build_canonical_pack,
    current_readiness_payload,
    pack_bytes,
    readiness_envelope,
    verify_readiness_envelope,
)
from supervisor.d1_gate import D1GateStatus, run_d1_integration_gate
from tests.test_d1_integration_gate import pack_data


ROOT = Path(__file__).resolve().parents[1]
REQUIRED_ARTIFACTS = (
    "commands",
    "configs",
    "tracker",
    "run-table",
    "plots",
    "cost-report",
    "limitations",
)


def git(repository: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *arguments],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def commit(repository: Path, message: str, *paths: str) -> str:
    git(repository, "add", *(paths or (".",)))
    git(
        repository,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@invalid.local",
        "commit",
        "-q",
        "-m",
        message,
    )
    return git(repository, "rev-parse", "HEAD")


class CanonicalD1PackBuilderTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repository = Path(self.temp.name) / "repository"
        self.repository.mkdir()
        git(self.repository, "init", "-q", "-b", "main")
        checklist = self.repository / "docs" / "execution_checklist.md"
        checklist.parent.mkdir()
        checklist.write_text(
            "# Checklist\n\n## Stage 7 — D1 evidence pack\n\n"
            "- [x] Publish commands and configs.\n"
            "- [x] Publish run table and plots.\n"
            "- [x] Publish cost and limitations.\n"
            "- [x] Write conclusion.\n\n## Later\n",
            encoding="utf-8",
        )
        (self.repository / "README.md").write_text("incumbent\n", encoding="utf-8")
        self.incumbent = commit(self.repository, "incumbent")
        (self.repository / "candidate.txt").write_text("candidate\n", encoding="utf-8")
        self.candidate = commit(self.repository, "candidate")

        artifact_root = self.repository / "stage7-artifacts"
        artifact_root.mkdir()
        self.artifact_sources = []
        for artifact_id in REQUIRED_ARTIFACTS:
            relative = f"stage7-artifacts/{artifact_id}.json"
            (self.repository / relative).write_text(
                json.dumps({"artifact": artifact_id}, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            self.artifact_sources.append(
                {
                    "artifact_id": artifact_id,
                    "kind": "stage7-evidence",
                    "path": relative,
                }
            )
        commit(self.repository, "artifact sources")

        raw_pack = pack_data(
            incumbent=self.incumbent,
            candidate=self.candidate,
            known_good=self.candidate,
        )
        raw_pack.pop("artifacts")
        runtime_hash = fingerprint({"runtime": "matched"})
        self.source = {
            "schema_version": 1,
            "pack": raw_pack,
            "runtime_identity_hashes": {
                "reference": runtime_hash,
                "control": runtime_hash,
                "candidate": runtime_hash,
            },
            "artifact_sources": self.artifact_sources,
        }
        self.source_path = self.repository / DEFAULT_BUILD_SPEC
        self.source_path.parent.mkdir(parents=True)
        self._write_and_commit_source("reviewed source")

    def _write_and_commit_source(self, message: str) -> None:
        self.source_path.write_text(
            json.dumps(self.source, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        commit(self.repository, message, DEFAULT_BUILD_SPEC.as_posix())

    def test_build_is_deterministic_and_hashes_all_required_artifacts(self) -> None:
        first = build_canonical_pack(self.repository)
        second = build_canonical_pack(self.repository)
        self.assertEqual(pack_bytes(first), pack_bytes(second))
        self.assertEqual(
            {item.artifact_id for item in first.artifacts}, set(REQUIRED_ARTIFACTS)
        )
        for artifact in first.artifacts:
            source = self.repository / artifact.uri.removeprefix("git:")
            content = source.read_bytes()
            self.assertEqual(artifact.size_bytes, len(content))
            self.assertEqual(artifact.sha256, hashlib.sha256(content).hexdigest())

    def test_cli_publishes_and_rebuilds_byte_identical_pack(self) -> None:
        command = [
            sys.executable,
            str(ROOT / "scripts" / "build_d1_evidence_pack.py"),
            "--repository",
            str(self.repository),
            "--publish",
        ]
        first = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(first.returncode, 0, first.stderr)
        pack_path = self.repository / "results/d1-stage7/evidence_pack.json"
        first_bytes = pack_path.read_bytes()
        readiness = json.loads(
            (self.repository / "results/d1-stage7/readiness.json").read_text()
        )
        self.assertEqual(verify_readiness_envelope(readiness)["status"], "ready")
        second = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(first_bytes, pack_path.read_bytes())

    def test_builder_pack_opens_gate_with_exact_evaluator_equivalence(self) -> None:
        command = [
            sys.executable,
            str(ROOT / "scripts" / "build_d1_evidence_pack.py"),
            "--repository",
            str(self.repository),
            "--publish",
        ]
        completed = subprocess.run(command, check=False, capture_output=True, text=True)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        commit(self.repository, "publish canonical pack")

        result = run_d1_integration_gate(self.repository)
        self.assertEqual(result.status, D1GateStatus.READY)
        self.assertIsNotNone(result.replay)
        replay = result.replay
        assert replay is not None
        legacy = decide_d1_candidate([0.4, 0.4, 0.4], [0.5, 0.5, 0.5])
        self.assertTrue(replay.equivalent)
        self.assertEqual(replay.legacy_declared, legacy.decision)
        self.assertEqual(replay.legacy_replayed, legacy.decision)
        self.assertEqual(replay.supervisor_decision, legacy.decision)
        self.assertEqual(replay.evaluation.control_mean_success, legacy.control_mean_success)
        self.assertEqual(
            replay.evaluation.candidate_mean_success, legacy.candidate_mean_success
        )
        self.assertEqual(replay.evaluation.mean_success_delta, legacy.mean_success_delta)
        self.assertEqual(replay.evaluation.success_delta_ci95, legacy.success_delta_ci95)

    def test_incomplete_seeds_and_unresolved_decision_are_rejected(self) -> None:
        self.source["pack"]["campaign"]["seeds"] = [2026, 2027]
        self.source["pack"]["runs"] = [
            item for item in self.source["pack"]["runs"] if item["seed"] != 2028
        ]
        self._write_and_commit_source("incomplete seeds")
        with self.assertRaisesRegex(D1PackBuildError, "exactly 3 paired seeds"):
            build_canonical_pack(self.repository)

        self.source["pack"]["campaign"]["seeds"] = [2026, 2027, 2028]
        self.source["pack"] = pack_data(
            incumbent=self.incumbent,
            candidate=self.candidate,
            known_good=self.candidate,
        )
        self.source["pack"].pop("artifacts")
        self.source["pack"]["legacy_decision"] = "inconclusive"
        self._write_and_commit_source("unresolved decision")
        with self.assertRaisesRegex(D1PackBuildError, "resolved keep or revert"):
            build_canonical_pack(self.repository)

    def test_runtime_mismatch_missing_and_duplicate_roles_are_rejected(self) -> None:
        self.source["runtime_identity_hashes"]["candidate"] = fingerprint(
            {"runtime": "different"}
        )
        self._write_and_commit_source("runtime mismatch")
        with self.assertRaisesRegex(D1PackBuildError, "runtime identities must match"):
            build_canonical_pack(self.repository)

        matched = self.source["runtime_identity_hashes"]["control"]
        self.source["runtime_identity_hashes"]["candidate"] = matched
        self.source["artifact_sources"].pop()
        self._write_and_commit_source("missing role")
        with self.assertRaisesRegex(D1PackBuildError, "exactly match"):
            build_canonical_pack(self.repository)

        self.source["artifact_sources"] = copy.deepcopy(self.artifact_sources)
        self.source["artifact_sources"].append(copy.deepcopy(self.artifact_sources[0]))
        self._write_and_commit_source("duplicate role")
        with self.assertRaisesRegex(D1PackBuildError, "must be unique"):
            build_canonical_pack(self.repository)

    def test_nonfinite_dirty_and_untracked_inputs_are_rejected(self) -> None:
        self.source["pack"]["runs"][-1]["success_rate"] = float("nan")
        self._write_and_commit_source("nonfinite metric")
        with self.assertRaisesRegex(D1PackBuildError, "finite"):
            build_canonical_pack(self.repository)

        self.source["pack"] = pack_data(
            incumbent=self.incumbent,
            candidate=self.candidate,
            known_good=self.candidate,
        )
        self.source["pack"].pop("artifacts")
        self._write_and_commit_source("restore valid source")
        dirty_path = self.repository / self.artifact_sources[0]["path"]
        dirty_path.write_text("dirty\n", encoding="utf-8")
        with self.assertRaisesRegex(D1PackBuildError, "match the tracked"):
            build_canonical_pack(self.repository)
        git(self.repository, "restore", self.artifact_sources[0]["path"])

        untracked = self.repository / "stage7-artifacts" / "untracked.json"
        untracked.write_text("{}\n", encoding="utf-8")
        self.source["artifact_sources"][0]["path"] = str(
            untracked.relative_to(self.repository)
        )
        self._write_and_commit_source("point at untracked input")
        with self.assertRaisesRegex(D1PackBuildError, "tracked by Git"):
            build_canonical_pack(self.repository)

    def test_unknown_commit_and_run_commit_mismatch_are_rejected(self) -> None:
        unknown = "f" * 40
        self.source["pack"]["known_good_commit"] = unknown
        self._write_and_commit_source("unknown source commit")
        with self.assertRaisesRegex(D1PackBuildError, "does not exist"):
            build_canonical_pack(self.repository)

        self.source["pack"]["known_good_commit"] = self.candidate
        self.source["pack"]["runs"][-1]["project_commit"] = self.incumbent
        self._write_and_commit_source("mismatched run commit")
        with self.assertRaisesRegex(D1PackBuildError, "does not match its condition"):
            build_canonical_pack(self.repository)


class CurrentD1ReadinessTests(unittest.TestCase):
    def test_current_evidence_report_is_deterministic_and_explicitly_blocked(self) -> None:
        first = current_readiness_payload(ROOT)
        second = current_readiness_payload(ROOT)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "blocked")
        self.assertFalse(first["canonical_pack_claimed"])
        self.assertEqual(first["source_inventory_count"], 10)
        self.assertEqual(first["source_inventory_bytes"], 53449)
        self.assertEqual(first["indexed_evidence_count"], 14)
        self.assertEqual(first["paired_seed_summary"]["paired_seeds"], [2026])
        codes = {item["code"] for item in first["blockers"]}
        self.assertTrue(
            {
                "canonical_source_spec_missing",
                "paired_seed_count_incomplete",
                "runtime_identity_mismatch",
                "reset_set_hash_missing",
                "reference_provenance_incomplete",
                "candidate_provenance_incomplete",
                "tracker_artifact_incomplete",
                "review_approval_missing",
                "candidate_policy_remote_only",
            }.issubset(codes)
        )

    def test_readiness_envelope_detects_tampering(self) -> None:
        envelope = readiness_envelope(current_readiness_payload(ROOT))
        self.assertEqual(verify_readiness_envelope(envelope)["status"], "blocked")
        envelope["payload"]["status"] = "ready"
        with self.assertRaisesRegex(D1PackBuildError, "does not match"):
            verify_readiness_envelope(envelope)


if __name__ == "__main__":
    unittest.main()
