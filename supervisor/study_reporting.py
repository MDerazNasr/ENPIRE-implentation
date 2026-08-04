"""Mechanical JSON/CSV/Markdown/HTML reports for the M8 study."""

from __future__ import annotations

import csv
import hashlib
import html
import io
import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

from supervisor.canonical import canonical_json
from supervisor.reporting import ReportArtifact, ReportBundle, _atomic_write
from supervisor.study import (
    REQUIRED_ARMS,
    StudyPhase,
    StudyStage,
    StudyState,
    equal_budget_audit,
)


SYNTHETIC_STUDY_NOTICE = "SYNTHETIC M8 STUDY REHEARSAL — NOT RL OR RESEARCH EVIDENCE"
LIVE_LIMITATION = (
    "Three paired seeds support a preregistered engineering comparison only; "
    "report paired outcomes and ranges without broad significance claims."
)


def _arm_totals(state: StudyState, arm_id: str) -> dict[str, Any]:
    records = [item for item in state.records if item.arm_id == arm_id]
    discovery = [item for item in records if item.stage == StudyStage.DISCOVERY]
    confirmation = [item for item in records if item.stage == StudyStage.CONFIRMATION]
    return {
        "discovery_slots_used": len(discovery),
        "confirmation_records": len(confirmation),
        "worker_seed_runs": sum(len(item.evidence) for item in records),
        "invalid_records": sum(item.status.value == "invalid" for item in records),
        "failed_records": sum(item.status.value == "failed" for item in records),
        "inconclusive_records": sum(item.status.value == "inconclusive" for item in records),
        "complete_records": sum(item.status.value == "complete" for item in records),
        "wall_time_seconds": sum(item.worker_wall_time_seconds for item in records),
        "gpu_cost_usd": str(sum((item.worker_gpu_cost_usd for item in records), Decimal(0))),
        "proposal_llm_cost_usd": str(sum((Decimal(item.proposal_llm_cost_usd) for item in records), Decimal(0))),
        "input_tokens": sum(item.input_tokens for item in records),
        "output_tokens": sum(item.output_tokens for item in records),
        "human_interventions": sum(item.human_interventions for item in records),
    }


def build_study_report_payload(state: StudyState) -> dict[str, Any]:
    arm_states = {item.arm_id: item for item in state.arms}
    selections: list[dict[str, Any]] = []
    confirmations: list[dict[str, Any]] = []
    records = {item.record_id: item for item in state.records}
    for arm_id in REQUIRED_ARMS:
        arm = arm_states[arm_id]
        selections.append(
            {
                "arm_id": arm_id,
                "selected_record_id": arm.selection.selected_record_id if arm.selection else None,
                "selected_candidate_commit": arm.selection.selected_candidate_commit if arm.selection else None,
                "selection_reason": arm.selection.reason if arm.selection else "selection not run",
                "confirmation_record_id": arm.confirmation_record_id,
            }
        )
        if arm.confirmation_record_id:
            record = records[arm.confirmation_record_id]
            evaluation = record.evaluation
            confirmations.append(
                {
                    "arm_id": arm_id,
                    "record_id": record.record_id,
                    "candidate_commit": record.candidate_commit,
                    "decision": evaluation.decision.value if evaluation else None,
                    "control_mean_success": evaluation.control_mean_success if evaluation else None,
                    "candidate_mean_success": evaluation.candidate_mean_success if evaluation else None,
                    "mean_success_delta": evaluation.mean_success_delta if evaluation else None,
                    "success_delta_ci95": list(evaluation.success_delta_ci95) if evaluation and evaluation.success_delta_ci95 else None,
                    "evidence_hashes": [item.fingerprint() for item in record.evidence],
                }
            )
    synthetic = state.activation.synthetic
    return {
        "report_schema": "m8-study-report-v1",
        "notice": SYNTHETIC_STUDY_NOTICE if synthetic else LIVE_LIMITATION,
        "synthetic": synthetic,
        "scientific_claim_permitted": not synthetic and state.phase == StudyPhase.COMPLETE,
        "interpretation": (
            "Synthetic fixtures validate study mechanics only; they support no policy, RL, agent, or arm-performance claim."
            if synthetic
            else LIVE_LIMITATION
        ),
        "study_phase": state.phase.value,
        "study_spec": state.spec.to_dict(),
        "preregistration_hash": state.spec.fingerprint(),
        "activation": state.activation.to_dict(),
        "state_hash": state.fingerprint(),
        "state_generation": state.generation,
        "equal_budget_audit": equal_budget_audit(state.spec),
        "arm_totals": {arm_id: _arm_totals(state, arm_id) for arm_id in REQUIRED_ARMS},
        "totals": {
            "candidate_experiments": len(state.records),
            "discovery_records": sum(item.stage == StudyStage.DISCOVERY for item in state.records),
            "confirmation_records": sum(item.stage == StudyStage.CONFIRMATION for item in state.records),
            "worker_seed_runs": sum(len(item.evidence) for item in state.records),
            "invalid_records": sum(item.status.value == "invalid" for item in state.records),
            "failed_records": sum(item.status.value == "failed" for item in state.records),
            "inconclusive_records": sum(item.status.value == "inconclusive" for item in state.records),
            "human_interventions": sum(item.human_interventions for item in state.records),
        },
        "selections": selections,
        "confirmations": confirmations,
        "records": [item.to_dict() | {"record_hash": item.fingerprint()} for item in state.records],
        "limitations": [
            LIVE_LIMITATION,
            "Discovery candidate experiments each aggregate the same three paired seeds; confirmation is an independent rerun of the frozen selected commit.",
            "Arms receive equal worker budgets; the fixed-rule arm correctly consumes no LLM budget.",
            "Missing valid candidates are reported as missing and are never replaced from another arm.",
        ],
    }


def _markdown(payload: Mapping[str, Any]) -> str:
    lines = [
        f"# {payload['notice']}", "",
        f"Study phase: `{payload['study_phase']}`  ",
        f"Preregistration: `{payload['preregistration_hash']}`  ",
        f"State: `{payload['state_hash']}`", "",
        "## Protocol integrity", "",
        "| Check | Result |", "|---|---|",
    ]
    for key, value in payload["equal_budget_audit"].items():
        lines.append(f"| {key} | {value} |")
    lines.extend(["", "## Arm summary", "", "| Arm | Discovery | Invalid | Failed | Selected | Confirmation |", "|---|---:|---:|---:|---|---|"])
    selection_by_arm = {item["arm_id"]: item for item in payload["selections"]}
    for arm_id, totals in payload["arm_totals"].items():
        selection = selection_by_arm[arm_id]
        lines.append(
            f"| {arm_id} | {totals['discovery_slots_used']} | {totals['invalid_records']} | "
            f"{totals['failed_records']} | {selection['selected_record_id'] or 'none'} | "
            f"{selection['confirmation_record_id'] or 'none'} |"
        )
    lines.extend(["", "## Paired confirmation", ""])
    if payload["confirmations"]:
        lines.extend(["| Arm | Decision | Control mean | Candidate mean | Delta | CI95 |", "|---|---|---:|---:|---:|---|"])
        for item in payload["confirmations"]:
            lines.append(
                f"| {item['arm_id']} | {item['decision']} | {item['control_mean_success']} | "
                f"{item['candidate_mean_success']} | {item['mean_success_delta']} | {item['success_delta_ci95']} |"
            )
    else:
        lines.append("No confirmations recorded.")
    lines.extend(["", "## Interpretation boundary", "", str(payload["interpretation"]), "", "## Limitations", ""])
    lines.extend(f"- {item}" for item in payload["limitations"])
    lines.append("")
    return "\n".join(lines)


def _csv_text(payload: Mapping[str, Any]) -> str:
    output = io.StringIO()
    fields = [
        "record_id", "record_hash", "arm_id", "stage", "slot_number", "status",
        "candidate_commit", "decision", "control_mean_success", "candidate_mean_success",
        "mean_success_delta", "worker_seed_runs", "worker_wall_time_seconds",
        "worker_gpu_cost_usd", "proposal_llm_cost_usd", "input_tokens", "output_tokens",
        "human_interventions", "reason",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    for item in payload["records"]:
        evaluation = item["evaluation"] or {}
        evidence = item["evidence"]
        writer.writerow(
            {
                "record_id": item["record_id"],
                "record_hash": item["record_hash"],
                "arm_id": item["arm_id"],
                "stage": item["stage"],
                "slot_number": item["slot_number"],
                "status": item["status"],
                "candidate_commit": item["candidate_commit"],
                "decision": evaluation.get("decision"),
                "control_mean_success": evaluation.get("control_mean_success"),
                "candidate_mean_success": evaluation.get("candidate_mean_success"),
                "mean_success_delta": evaluation.get("mean_success_delta"),
                "worker_seed_runs": len(evidence),
                "worker_wall_time_seconds": sum(row["elapsed_seconds"] for row in evidence),
                "worker_gpu_cost_usd": str(sum((Decimal(row["gpu_cost_usd"]) for row in evidence), Decimal(0))),
                "proposal_llm_cost_usd": item["proposal_llm_cost_usd"],
                "input_tokens": item["input_tokens"],
                "output_tokens": item["output_tokens"],
                "human_interventions": item["human_interventions"],
                "reason": item["reason"],
            }
        )
    return output.getvalue()


def _html(payload: Mapping[str, Any], markdown: str) -> str:
    rows = "".join(
        "<tr>" + "".join(
            f"<td>{html.escape(str(value))}</td>"
            for value in (
                item["arm_id"], item["stage"], item["slot_number"], item["status"],
                (item["evaluation"] or {}).get("decision"), item["candidate_commit"],
            )
        ) + "</tr>"
        for item in payload["records"]
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<title>M8 three-arm study</title><style>
body{{font:15px system-ui;max-width:1200px;margin:35px auto;padding:0 20px;color:#17212b}}
.notice{{padding:16px;border:2px solid #9a5a00;background:#fff0c2;font-weight:800}}
table{{border-collapse:collapse;width:100%;margin:18px 0}}th,td{{border:1px solid #ccd4dc;padding:7px;text-align:left}}
code,pre{{background:#f4f6f8}}pre{{padding:16px;white-space:pre-wrap}}</style></head>
<body><div class="notice">{html.escape(str(payload['notice']))}</div>
<h1>M8 preregistered three-arm study</h1><p>Preregistration <code>{payload['preregistration_hash']}</code></p>
<h2>Complete retained record</h2><table><tr><th>Arm</th><th>Stage</th><th>Slot</th><th>Status</th><th>Decision</th><th>Candidate</th></tr>{rows}</table>
<h2>Report narrative</h2><pre>{html.escape(markdown)}</pre></body></html>"""


def write_study_report(*, state: StudyState, output_directory: str | Path) -> ReportBundle:
    output = Path(output_directory)
    payload = build_study_report_payload(state)
    markdown = _markdown(payload)
    contents = {
        "study-report.json": (json.dumps(payload, indent=2, sort_keys=True) + "\n").encode(),
        "study-trials.csv": _csv_text(payload).encode(),
        "study-report.md": markdown.encode(),
        "study-report.html": _html(payload, markdown).encode(),
    }
    artifacts: list[ReportArtifact] = []
    for name, content in contents.items():
        path = output / name
        _atomic_write(path, content)
        artifacts.append(ReportArtifact(name=name, path=str(path), sha256=hashlib.sha256(content).hexdigest(), size_bytes=len(content)))
    manifest_payload = {
        "manifest_schema": "m8-report-manifest-v1",
        "preregistration_hash": state.spec.fingerprint(),
        "state_hash": state.fingerprint(),
        "artifacts": [item.to_dict() for item in artifacts],
    }
    manifest_content = (canonical_json(manifest_payload) + "\n").encode()
    manifest_path = output / "artifact-manifest.json"
    _atomic_write(manifest_path, manifest_content)
    artifacts.append(ReportArtifact(name="artifact-manifest.json", path=str(manifest_path), sha256=hashlib.sha256(manifest_content).hexdigest(), size_bytes=len(manifest_content)))
    return ReportBundle(report_id=f"{state.spec.study_id}-m8", output_directory=str(output), artifacts=tuple(artifacts))
