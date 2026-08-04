"""Deterministic campaign artifacts for offline supervisor demonstrations."""

from __future__ import annotations

import csv
import hashlib
import html
import json
import os
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping, Sequence

from supervisor.attempts import ProposalSessionResult
from supervisor.canonical import canonical_json, fingerprint, require_sha256
from supervisor.contracts import SCHEMA_VERSION, CampaignSpec
from supervisor.coordinator import OfflineIterationResult


SYNTHETIC_NOTICE = (
    "SYNTHETIC OFFLINE DEMONSTRATION — NOT RESEARCH EVIDENCE"
)


@dataclass(frozen=True)
class ReportArtifact:
    name: str
    path: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "path": self.path,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class ReportBundle:
    report_id: str
    output_directory: str
    artifacts: tuple[ReportArtifact, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "report_id": self.report_id,
            "output_directory": self.output_directory,
            "artifacts": [item.to_dict() for item in self.artifacts],
        }


def _atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _totals(
    sessions: Sequence[ProposalSessionResult],
    iterations: Sequence[OfflineIterationResult],
) -> dict[str, Any]:
    attempts = [attempt for session in sessions for attempt in session.attempts]
    evidence = [item for iteration in iterations for item in iteration.evidence]
    attempt_status_counts: dict[str, int] = {}
    for item in attempts:
        attempt_status_counts[item.status.value] = (
            attempt_status_counts.get(item.status.value, 0) + 1
        )
    decision_counts: dict[str, int] = {}
    for iteration in iterations:
        if iteration.evaluation is not None:
            value = iteration.evaluation.decision_record.decision.value
            decision_counts[value] = decision_counts.get(value, 0) + 1
    proposal_llm = sum(
        (Decimal(session.total_cost_usd) for session in sessions), Decimal(0)
    )
    worker_llm = sum(
        (Decimal(item.llm_cost_usd) for item in evidence), Decimal(0)
    )
    return {
        "proposal_sessions": len(sessions),
        "proposal_attempts": len(attempts),
        "accepted_attempts": sum(item.status.value == "accepted" for item in attempts),
        "invalid_attempts": sum(item.status.value == "invalid" for item in attempts),
        "iterations": len(iterations),
        "trials_with_evidence": len(evidence),
        "failed_trials": sum(item.status.value != "complete" for item in evidence),
        "attempt_status_counts": dict(sorted(attempt_status_counts.items())),
        "decision_counts": dict(sorted(decision_counts.items())),
        "wall_time_seconds": sum(item.elapsed_seconds for item in evidence),
        "gpu_cost_usd": str(
            sum((Decimal(item.gpu_cost_usd) for item in evidence), Decimal(0))
        ),
        "proposal_llm_cost_usd": str(proposal_llm),
        "worker_llm_cost_usd": str(worker_llm),
        "total_llm_cost_usd": str(proposal_llm + worker_llm),
        "input_tokens": sum(item.input_tokens or 0 for item in attempts),
        "output_tokens": sum(item.output_tokens or 0 for item in attempts),
        "human_interventions": 0,
        "gpu_utilization_percent": None,
    }


def build_report_payload(
    *,
    campaign: CampaignSpec,
    proposal_sessions: Sequence[ProposalSessionResult],
    iterations: Sequence[OfflineIterationResult],
    incumbent_snapshot: Mapping[str, str],
) -> dict[str, Any]:
    sessions = tuple(proposal_sessions)
    results = tuple(iterations)
    return {
        "schema_version": SCHEMA_VERSION,
        "notice": SYNTHETIC_NOTICE,
        "synthetic": True,
        "campaign": campaign.to_dict(),
        "campaign_hash": campaign.fingerprint(),
        "totals": _totals(sessions, results),
        "proposal_sessions": [item.to_dict() for item in sessions],
        "iterations": [item.to_dict() for item in results],
        "incumbent_snapshot": dict(sorted(incumbent_snapshot.items())),
    }


def _markdown(payload: Mapping[str, Any]) -> str:
    totals = payload["totals"]
    lines = [
        f"# {SYNTHETIC_NOTICE}",
        "",
        f"Campaign: `{payload['campaign']['campaign_id']}`",
        f"Campaign hash: `{payload['campaign_hash']}`",
        "",
        "## Totals",
        "",
        "| Metric | Value |",
        "|---|---:|",
    ]
    lines.extend(f"| {key} | {value} |" for key, value in totals.items())
    lines.extend(["", "## Iterations", ""])
    for item in payload["iterations"]:
        evaluation = item["evaluation"]
        decision = (
            evaluation["decision_record"]["decision"] if evaluation else "none"
        )
        lines.extend(
            [
                f"### {item['iteration_id']}",
                "",
                f"- Status: `{item['status']}`",
                f"- Arm: `{item['arm_id']}`",
                f"- Decision: `{decision}`",
                f"- Incumbent: `{item['incumbent_before']}` → "
                f"`{item['incumbent_after']}`",
                f"- Trial evidence records: {len(item['evidence'])}",
                f"- Errors: {', '.join(item['errors']) if item['errors'] else 'none'}",
                "",
            ]
        )
    lines.extend(
        [
            "## Interpretation boundary",
            "",
            "All metrics in this bundle are deterministic fixtures used to validate "
            "orchestration. They are not RL training results and support no scientific "
            "performance claim.",
            "",
        ]
    )
    return "\n".join(lines)


def _html(markdown_summary: str, payload: Mapping[str, Any]) -> str:
    totals = "".join(
        f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
        for key, value in payload["totals"].items()
    )
    iterations = "".join(
        "<tr>"
        f"<td>{html.escape(item['iteration_id'])}</td>"
        f"<td>{html.escape(item['status'])}</td>"
        f"<td>{html.escape(str(item['arm_id']))}</td>"
        f"<td>{html.escape(_decision_text(item))}</td>"
        "</tr>"
        for item in payload["iterations"]
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>M4 Offline Supervisor Demo</title>
<style>body{{font:16px system-ui;max-width:1050px;margin:40px auto;padding:0 20px;color:#17212b}}
.notice{{background:#fff0c2;border:2px solid #b26a00;padding:16px;font-weight:800}}
table{{border-collapse:collapse;width:100%;margin:18px 0}}
th,td{{border:1px solid #ccd4dc;padding:8px;text-align:left}}
code{{background:#eef2f5;padding:2px 5px}}
pre{{white-space:pre-wrap;background:#f6f8fa;padding:16px}}</style></head>
<body><div class="notice">{html.escape(SYNTHETIC_NOTICE)}</div>
<h1>Offline coding-agent supervisor</h1>
<p>Campaign <code>{html.escape(payload['campaign']['campaign_id'])}</code></p>
<h2>Totals</h2><table>{totals}</table>
<h2>Iterations</h2>
<table><tr><th>ID</th><th>Status</th><th>Arm</th><th>Decision</th></tr>
{iterations}</table>
<h2>Machine-readable narrative</h2><pre>{html.escape(markdown_summary)}</pre>
</body></html>"""


def _decision_text(iteration: Mapping[str, Any]) -> str:
    evaluation = iteration["evaluation"]
    return evaluation["decision_record"]["decision"] if evaluation else "none"


def write_report_bundle(
    output_directory: Path,
    *,
    campaign: CampaignSpec,
    proposal_sessions: Sequence[ProposalSessionResult],
    iterations: Sequence[OfflineIterationResult],
    incumbent_snapshot: Mapping[str, str],
) -> ReportBundle:
    payload = build_report_payload(
        campaign=campaign,
        proposal_sessions=proposal_sessions,
        iterations=iterations,
        incumbent_snapshot=incumbent_snapshot,
    )
    output_directory.mkdir(parents=True, exist_ok=True)
    report_id = fingerprint(payload)
    summary = _markdown(payload)
    files = {
        "report.json": canonical_json(payload).encode("utf-8") + b"\n",
        "report.md": summary.encode("utf-8"),
        "report.html": _html(summary, payload).encode("utf-8"),
    }
    rows: list[dict[str, Any]] = []
    for iteration in payload["iterations"]:
        for evidence in iteration["evidence"]:
            rows.append(
                {
                    "iteration_id": iteration["iteration_id"],
                    "trial_id": evidence["trial_id"],
                    "arm_id": evidence["arm_id"],
                    "seed": evidence["seed"],
                    "status": evidence["status"],
                    "success_rate": evidence["metrics"].get("success_rate", ""),
                    "successful_episode_length": evidence["metrics"].get(
                        "successful_episode_length", ""
                    ),
                    "elapsed_seconds": evidence["elapsed_seconds"],
                    "gpu_cost_usd": evidence["gpu_cost_usd"],
                    "llm_cost_usd": evidence["llm_cost_usd"],
                    "evidence_hash": fingerprint(evidence),
                }
            )
    csv_path = output_directory / "trials.csv"
    csv_fields = [
        "iteration_id", "trial_id", "arm_id", "seed", "status",
        "success_rate", "successful_episode_length", "elapsed_seconds",
        "gpu_cost_usd", "llm_cost_usd", "evidence_hash",
    ]
    with tempfile.TemporaryFile(mode="w+", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=csv_fields)
        writer.writeheader()
        writer.writerows(rows)
        handle.seek(0)
        files[csv_path.name] = handle.read().encode("utf-8")
    artifacts: list[ReportArtifact] = []
    for name, data in files.items():
        path = output_directory / name
        _atomic_write(path, data)
        sha256 = hashlib.sha256(data).hexdigest()
        require_sha256(sha256, "report artifact hash")
        artifacts.append(
            ReportArtifact(name=name, path=str(path), sha256=sha256, size_bytes=len(data))
        )
    return ReportBundle(
        report_id=report_id,
        output_directory=str(output_directory),
        artifacts=tuple(sorted(artifacts, key=lambda item: item.name)),
    )
