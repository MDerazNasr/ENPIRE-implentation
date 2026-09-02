from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from supervisor.canonical import fingerprint
from supervisor.d1_gate import (
    DEFAULT_PACK_PATH,
    D1EvidencePack,
    D1GateError,
    D1GateStatus,
    audit_d1_repository,
    replay_d1_pack,
    run_d1_integration_gate,
)
from tests.test_supervisor_contracts import campaign_data


INCUMBENT = "a" * 40
CANDIDATE = "b" * 40
KNOWN_GOOD = "c" * 40
REQUIRED_ARTIFACTS = (
    "commands",
    "configs",
    "tracker",
    "run-table",
    "plots",
    "cost-report",
    "limitations",
)


def run_data(condition: str, seed: int, success: float) -> dict:
    return {
        "run_id": f"d1-{condition}-{seed}",
        "condition": condition,
        "seed": seed,
        "project_commit": CANDIDATE if condition == "candidate" else INCUMBENT,
        "config_hash": fingerprint({"condition": condition, "seed": seed}),
        "command_hash": fingerprint(["run-d1", condition, seed]),
        "started_at": "2026-08-04T12:00:00Z",
        "finished_at": "2026-08-04T12:01:00Z",
        "status": "complete",
        "exit_code": 0,
        "elapsed_seconds": 60,
        "gpu_cost_usd": "0.5",
        "success_rate": success,
        "successful_episode_length": 40,
        "metric_errors": [],
    }


def pack_data(
    *,
    incumbent: str = INCUMBENT,
    candidate: str = CANDIDATE,
    known_good: str = KNOWN_GOOD,
) -> dict:
    campaign = campaign_data()
    campaign["campaign_id"] = "d1-stage7-replay"
    campaign["baseline_commit"] = incumbent
    seeds = campaign["seeds"]
    runs = [run_data("reference", seeds[0], 0.35)]
    runs.extend(run_data("control", seed, 0.4) for seed in seeds)
    runs.extend(run_data("candidate", seed, 0.5) for seed in seeds)
    for run in runs:
        if run["condition"] == "candidate":
            run["project_commit"] = candidate
        else:
            run["project_commit"] = incumbent
    artifacts = [
        {
            "artifact_id": artifact_id,
            "kind": "stage7-evidence",
            "uri": f"artifact://d1/{artifact_id}",
            "sha256": fingerprint({"artifact": artifact_id}),
            "size_bytes": 100,
        }
        for artifact_id in REQUIRED_ARTIFACTS
    ]
    return {
        "schema_version": 1,
        "pack_id": "d1-stage7-pack",
        "known_good_commit": known_good,
        "incumbent_commit": incumbent,
        "candidate_commit": candidate,
        "campaign": campaign,
        "baseline_non_degenerate": True,
        "legacy_decision": "keep",
        "reviewed_by": "Mohamed Deraz Nasr",
        "reviewed_at": "2026-08-04T14:00:00Z",
        "conclusion": "Candidate C satisfies the preregistered fixture rule.",
        "runs": runs,
        "artifacts": artifacts,
    }


def git(repository: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(repository), *args],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def commit(repository: Path, message: str) -> str:
    git(repository, "add", ".")
    git(
        repository,
        "-c", "user.name=Fixture",
        "-c", "user.email=fixture@invalid.local",
        "commit", "-q", "-m", message,
    )
    return git(repository, "rev-parse", "HEAD")


class D1PackContractTests(unittest.TestCase):
    def test_complete_pack_replays_byte_stable_decision_inputs(self) -> None:
        pack = D1EvidencePack.from_dict(pack_data())
        result = replay_d1_pack(pack)
        self.assertEqual(result.status, D1GateStatus.READY)
        self.assertTrue(result.equivalent)
        self.assertEqual(result.legacy_declared, "keep")
        self.assertEqual(result.legacy_replayed, "keep")
        self.assertEqual(result.supervisor_decision, "keep")
        self.assertEqual(len(result.control_evidence), 3)
        self.assertEqual(pack, D1EvidencePack.from_dict(pack.to_dict()))

    def test_degenerate_baseline_blocks_even_when_evaluators_agree(self) -> None:
        raw = pack_data()
        raw["baseline_non_degenerate"] = False
        result = replay_d1_pack(D1EvidencePack.from_dict(raw))
        self.assertEqual(result.status, D1GateStatus.BLOCKED)
        self.assertTrue(result.equivalent)
        self.assertIn("degenerate", result.reasons[0])

    def test_declared_decision_mismatch_blocks_replay(self) -> None:
        raw = pack_data()
        raw["legacy_decision"] = "revert"
        result = replay_d1_pack(D1EvidencePack.from_dict(raw))
        self.assertEqual(result.status, D1GateStatus.BLOCKED)
        self.assertFalse(result.equivalent)

    def test_failed_candidate_cannot_become_a_keep(self) -> None:
        raw = pack_data()
        failed = raw["runs"][-1]
        failed.update(
            status="failed",
            exit_code=7,
            success_rate=None,
            metric_errors=["success_rate: run failed"],
        )
        raw["legacy_decision"] = "inconclusive"
        result = replay_d1_pack(D1EvidencePack.from_dict(raw))
        self.assertEqual(result.status, D1GateStatus.BLOCKED)
        self.assertEqual(result.legacy_replayed, "inconclusive")
        self.assertEqual(result.supervisor_decision, "failed")

    def test_incomplete_reference_blocks_an_otherwise_matching_replay(self) -> None:
        raw = pack_data()
        reference = raw["runs"][0]
        reference.update(
            status="failed",
            exit_code=3,
            success_rate=None,
            metric_errors=["Reference A failed"],
        )
        result = replay_d1_pack(D1EvidencePack.from_dict(raw))
        self.assertEqual(result.status, D1GateStatus.BLOCKED)
        self.assertTrue(result.equivalent)
        self.assertIn("Reference A", result.reasons[0])

    def test_missing_artifact_seed_and_duplicate_run_are_rejected(self) -> None:
        cases = []
        missing_artifact = pack_data()
        missing_artifact["artifacts"].pop()
        cases.append((missing_artifact, "missing Stage-7 artifacts"))
        missing_seed = pack_data()
        missing_seed["runs"] = [
            item
            for item in missing_seed["runs"]
            if not (item["condition"] == "candidate" and item["seed"] == 2028)
        ]
        cases.append((missing_seed, "approved seeds"))
        duplicate = pack_data()
        duplicate["runs"].append(copy.deepcopy(duplicate["runs"][-1]))
        cases.append((duplicate, "duplicate condition/seed"))
        for raw, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(D1GateError, message):
                    D1EvidencePack.from_dict(raw)


class D1RepositoryGateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.repository = Path(self.temp.name) / "d1"
        self.repository.mkdir()
        git(self.repository, "init", "-q", "-b", "main")
        (self.repository / "docs").mkdir()
        (self.repository / "source.txt").write_text("incumbent\n", encoding="utf-8")
        self.incumbent = commit(self.repository, "incumbent")
        (self.repository / "source.txt").write_text("candidate\n", encoding="utf-8")
        self.candidate = commit(self.repository, "candidate")

    def write_complete_pack(self) -> None:
        checklist = (
            "# Checklist\n\n## Stage 7 — D1 evidence pack\n\n"
            "- [x] Publish commands and configs.\n"
            "- [x] Publish run table and plots.\n"
            "- [x] Publish cost and limitations.\n"
            "- [x] Write conclusion.\n\n## Later\n"
        )
        (self.repository / "docs" / "execution_checklist.md").write_text(
            checklist, encoding="utf-8"
        )
        pack_path = self.repository / DEFAULT_PACK_PATH
        pack_path.parent.mkdir(parents=True)
        payload = pack_data(
            incumbent=self.incumbent,
            candidate=self.candidate,
            known_good=self.candidate,
        )
        pack_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        commit(self.repository, "publish Stage 7 pack")

    def test_clean_tracked_complete_pack_opens_gate(self) -> None:
        self.write_complete_pack()
        result = run_d1_integration_gate(self.repository)
        self.assertEqual(result.status, D1GateStatus.READY)
        self.assertIsNotNone(result.replay)
        self.assertTrue(result.replay.equivalent)
        self.assertEqual(result.audit.head_commit, git(self.repository, "rev-parse", "HEAD"))

    def test_dirty_or_incomplete_repository_is_blocked_read_only(self) -> None:
        (self.repository / "docs" / "execution_checklist.md").write_text(
            "## Stage 7 — D1 evidence pack\n- [ ] Publish evidence.\n"
            "Baseline is degenerate; Stage 6 is blocked.\n",
            encoding="utf-8",
        )
        before = git(self.repository, "status", "--porcelain")
        audit = audit_d1_repository(self.repository)
        after = git(self.repository, "status", "--porcelain")
        self.assertEqual(audit.status, D1GateStatus.BLOCKED)
        self.assertFalse(audit.clean)
        self.assertFalse(audit.pack_exists)
        self.assertTrue(audit.degenerate_baseline_recorded)
        self.assertEqual(before, after)

    def test_pack_path_cannot_escape_repository(self) -> None:
        audit = audit_d1_repository(
            self.repository, pack_relative_path=Path("../outside.json")
        )
        self.assertEqual(audit.status, D1GateStatus.INVALID)
        self.assertIn("contain '..'", audit.reasons[0])

    def test_untracked_pack_cannot_open_gate(self) -> None:
        self.write_complete_pack()
        git(self.repository, "rm", "--cached", str(DEFAULT_PACK_PATH))
        result = run_d1_integration_gate(self.repository)
        self.assertEqual(result.status, D1GateStatus.BLOCKED)
        self.assertIn("not clean", " ".join(result.reasons))


if __name__ == "__main__":
    unittest.main()
