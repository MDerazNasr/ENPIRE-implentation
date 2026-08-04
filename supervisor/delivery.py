"""M9 meeting-delivery validation, rendering, and artifact reconciliation."""

from __future__ import annotations

import hashlib
import html
import json
import os
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from supervisor.canonical import (
    ContractError,
    canonical_json,
    fingerprint,
    require_exact_keys,
    require_git_commit,
    require_identifier,
    require_nonempty_text,
    require_safe_relative_path,
    require_sha256,
)


M9_DELIVERY_VERSION = "m9-ludvig-delivery-v1"
M9_NOTICE = "SYNTHETIC CONTROL-PLANE DEMONSTRATION — NOT RLT PERFORMANCE EVIDENCE"


class DeliveryError(ContractError):
    """Raised when a component or final delivery artifact is inconsistent."""


@dataclass(frozen=True)
class DeliveryArtifact:
    path: str
    role: str
    sha256: str
    size_bytes: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "role": self.role,
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }


@dataclass(frozen=True)
class DeliveryBundle:
    output_directory: str
    delivery_fingerprint: str
    manifest_path: str
    artifacts: tuple[DeliveryArtifact, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "delivery_version": M9_DELIVERY_VERSION,
            "output_directory": self.output_directory,
            "delivery_fingerprint": self.delivery_fingerprint,
            "manifest_path": self.manifest_path,
            "artifacts": [item.to_dict() for item in self.artifacts],
        }


def _require_mapping(value: Any, field: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise DeliveryError(f"{field} must be an object")
    return value


def _require_bool(value: Any, field: str) -> bool:
    if not isinstance(value, bool):
        raise DeliveryError(f"{field} must be boolean")
    return value


def _require_int(value: Any, field: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise DeliveryError(f"{field} must be an integer >= {minimum}")
    return value


def normalize_m4_summary(value: Any) -> dict[str, Any]:
    data = _require_mapping(value, "M4 summary")
    notice = require_nonempty_text(data.get("notice"), "M4 notice")
    if "SYNTHETIC" not in notice or "NOT RESEARCH EVIDENCE" not in notice:
        raise DeliveryError("M4 output lost its synthetic evidence boundary")
    status = require_identifier(data.get("status"), "M4 status")
    decision = require_identifier(data.get("decision"), "M4 decision")
    if status != "decided" or decision not in {"keep", "revert", "inconclusive", "failed"}:
        raise DeliveryError("M4 demo did not reach a frozen terminal decision")
    stable = _require_bool(data.get("stable_head_unchanged"), "M4 stable-head proof")
    if not stable:
        raise DeliveryError("M4 demo moved its stable branch")
    return {
        "status": status,
        "decision": decision,
        "invalid_attempts_before_acceptance": _require_int(
            data.get("invalid_attempts_before_acceptance"),
            "M4 invalid attempt count",
        ),
        "stable_head_unchanged": stable,
    }


def normalize_m7_summary(value: Any) -> dict[str, Any]:
    data = _require_mapping(value, "M7 summary")
    notice = require_nonempty_text(data.get("notice"), "M7 notice")
    if "SYNTHETIC" not in notice or "NOT RLT PERFORMANCE EVIDENCE" not in notice:
        raise DeliveryError("M7 output lost its synthetic evidence boundary")
    external = data.get("external_calls")
    if external != []:
        raise DeliveryError("M7 offline demo unexpectedly recorded external calls")
    decisions = _require_mapping(data.get("decisions"), "M7 decisions")
    normalized_decisions: dict[str, str] = {}
    for arm, result in sorted(decisions.items()):
        require_identifier(arm, "M7 arm")
        record = _require_mapping(
            _require_mapping(result, "M7 evaluation").get("decision_record"),
            "M7 decision record",
        )
        normalized_decisions[arm] = require_identifier(
            record.get("decision"), "M7 decision"
        )
    if not normalized_decisions:
        raise DeliveryError("M7 demo contains no decisions")
    states = _require_mapping(data.get("final_trial_states"), "M7 final states")
    if not states or set(states.values()) != {"completed"}:
        raise DeliveryError("M7 demo did not reconcile every trial to complete")
    if not _require_bool(data.get("stale_completion_rejected"), "M7 stale rejection"):
        raise DeliveryError("M7 demo accepted stale authority")
    if not _require_bool(data.get("stable_head_unchanged"), "M7 stable-head proof"):
        raise DeliveryError("M7 demo moved the supervisor stable branch")
    return {
        "first_batch_parallelism": _require_int(
            data.get("first_batch_parallelism"), "M7 parallelism", minimum=1
        ),
        "lost_trial_attempts": _require_int(
            data.get("lost_trial_attempts"), "M7 retry count", minimum=1
        ),
        "stale_completion_rejected": True,
        "completed_trial_count": len(states),
        "decisions": normalized_decisions,
        "stable_head_unchanged": True,
    }


def normalize_m8_summary(value: Any) -> dict[str, Any]:
    data = _require_mapping(value, "M8 summary")
    notice = require_nonempty_text(data.get("notice"), "M8 notice")
    if "SYNTHETIC" not in notice or "NOT RL OR RESEARCH EVIDENCE" not in notice:
        raise DeliveryError("M8 output lost its synthetic evidence boundary")
    if data.get("external_calls") != []:
        raise DeliveryError("M8 offline demo unexpectedly recorded external calls")
    if data.get("phase") != "complete":
        raise DeliveryError("M8 study did not complete")
    selections = _require_mapping(data.get("selected_records"), "M8 selections")
    expected_arms = {"fixed-rule-config", "claude-config", "claude-code"}
    if set(selections) != expected_arms or not all(selections.values()):
        raise DeliveryError("M8 study lacks an exact selected candidate per arm")
    return {
        "phase": "complete",
        "preregistration_hash": require_sha256(
            data.get("preregistration_hash"), "M8 preregistration hash"
        ),
        "discovery_records": _require_int(
            data.get("discovery_records"), "M8 discovery count"
        ),
        "confirmation_records": _require_int(
            data.get("confirmation_records"), "M8 confirmation count"
        ),
        "worker_seed_runs": _require_int(
            data.get("worker_seed_runs"), "M8 seed-run count"
        ),
        "selected_records": dict(sorted(selections.items())),
    }


def normalize_d1_summary(value: Any | None) -> dict[str, Any]:
    if value is None:
        return {
            "requested": False,
            "status": "not_requested",
            "gate_hash": None,
            "replay_equivalent": None,
            "reasons": [],
        }
    data = _require_mapping(value, "D1 summary")
    status = require_identifier(data.get("status"), "D1 gate status")
    if status not in {"ready", "blocked", "invalid"}:
        raise DeliveryError("D1 gate status is unsupported")
    reasons = data.get("reasons")
    if not isinstance(reasons, list) or not all(isinstance(item, str) and item for item in reasons):
        raise DeliveryError("D1 reasons must be non-empty strings")
    replay = data.get("replay")
    equivalent = None
    if replay is not None:
        equivalent = _require_bool(
            _require_mapping(replay, "D1 replay").get("equivalent"),
            "D1 replay equivalence",
        )
    if status == "ready" and equivalent is not True:
        raise DeliveryError("ready D1 status requires equivalent replay")
    return {
        "requested": True,
        "status": status,
        "gate_hash": require_sha256(data.get("gate_hash"), "D1 gate hash"),
        "replay_equivalent": equivalent,
        "reasons": list(reasons),
    }


def build_delivery_payload(
    *,
    repository_head: str,
    repository_branch: str,
    repository_clean_before: bool,
    repository_clean_after: bool,
    m4: Any,
    m7: Any,
    m8: Any,
    d1: Any | None,
) -> dict[str, Any]:
    head = require_git_commit(repository_head, "delivery repository head")
    branch = require_nonempty_text(repository_branch, "delivery repository branch")
    if not repository_clean_before or not repository_clean_after:
        raise DeliveryError("final demo requires a clean supervisor repository")
    m4_summary = normalize_m4_summary(m4)
    m7_summary = normalize_m7_summary(m7)
    m8_summary = normalize_m8_summary(m8)
    d1_summary = normalize_d1_summary(d1)
    semantic = {
        "delivery_version": M9_DELIVERY_VERSION,
        "repository_head": head,
        "repository_branch": branch,
        "m4": m4_summary,
        "m7": m7_summary,
        "m8": m8_summary,
        "d1": d1_summary,
    }
    return {
        "delivery_version": M9_DELIVERY_VERSION,
        "notice": M9_NOTICE,
        "status": "complete",
        "synthetic": True,
        "scientific_claim_permitted": False,
        "evidence_mode": (
            "synthetic-control-plane-plus-ready-d1-replay"
            if d1_summary["status"] == "ready"
            else "synthetic-control-plane"
        ),
        "delivery_fingerprint": fingerprint(semantic),
        "repository": {
            "head": head,
            "branch": branch,
            "clean_before": True,
            "clean_after": True,
            "head_unchanged": True,
        },
        "components": {
            "m4_policy_improvement": m4_summary,
            "m7_distributed_execution": m7_summary,
            "m8_three_arm_study": m8_summary,
        },
        "d1_replay": d1_summary,
        "external_calls": [],
        "what_this_proves": [
            "bounded proposals can be validated and isolated before execution",
            "worker loss and stale completion do not gain promotion authority",
            "three arm histories remain isolated under a frozen selection rule",
            "every displayed control-plane result reconciles to retained artifacts",
        ],
        "what_this_does_not_prove": [
            "that RLT improved the frozen VLA",
            "that Claude outperforms the fixed rule or another coding agent",
            "that synthetic worker timing represents GPU scaling",
            "that the objective overlay is attached to the final D1 RLinf loss site",
        ],
        "meeting_steps": [
            "Frame the agent as outer-loop RL supervision, not action or gradient control.",
            "Show the immutable/editable architecture boundary.",
            "Run M4 proposal validation, branch isolation, evaluation, and keep/revert.",
            "Show M7 two-worker overlap, loss retry, and stale-result rejection.",
            "Show M8 preregistration, three isolated arms, selection, and confirmation.",
            "Open the artifact manifest and state the evidence/claim boundary.",
            "If available, show read-only D1 replay status and compatibility next steps.",
        ],
        "limitations": [
            "all M4/M7/M8 numerical outcomes in this bundle are deterministic fixtures",
            "no provider, GPU, SSH, W&B, RLinf, paid service, or robot was contacted",
            "D1 replay, when requested, is read-only and is not a new training run",
            "a real three-arm comparison requires the ready D1 baseline and approved compute",
        ],
    }


def architecture_svg() -> str:
    """Return a dependency-free architecture visual for the final report."""

    svg = """<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="660" viewBox="0 0 1200 660" role="img" aria-labelledby="title desc">
<title id="title">RLT coding-agent supervisor architecture</title>
<desc id="desc">Three bounded proposers feed supervisor validation and isolated Git candidates, independent workers return immutable evidence, and a deterministic evaluator alone updates isolated arm incumbents.</desc>
<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L0,6 L9,3 z" fill="#47627a"/></marker></defs>
<rect width="1200" height="660" rx="22" fill="#f5f8fb"/>
<text x="50" y="48" font-family="system-ui" font-size="26" font-weight="700" fill="#142638">ENPIRE-inspired outer-loop supervision of RLT</text>
<g font-family="system-ui" font-size="17" fill="#142638">
<rect x="50" y="95" width="230" height="62" rx="12" fill="#dcecff" stroke="#3974a8"/><text x="72" y="122">Fixed-rule config</text><text x="72" y="145" font-size="13">transparent baseline arm</text>
<rect x="50" y="180" width="230" height="62" rx="12" fill="#e7e0ff" stroke="#7358b8"/><text x="72" y="207">Claude config</text><text x="72" y="230" font-size="13">tool-free structured proposal</text>
<rect x="50" y="265" width="230" height="62" rx="12" fill="#e7e0ff" stroke="#7358b8"/><text x="72" y="292">Claude objective code</text><text x="72" y="315" font-size="13">one project-owned function</text>
<rect x="375" y="140" width="250" height="140" rx="14" fill="#fff5ce" stroke="#b28a16"/><text x="397" y="172" font-weight="700">Supervisor authority</text><text x="397" y="201" font-size="14">scope + budget validation</text><text x="397" y="225" font-size="14">isolated Git candidate</text><text x="397" y="249" font-size="14">fixed tests; no agent tools</text>
<rect x="720" y="115" width="240" height="85" rx="14" fill="#dff6e7" stroke="#43855a"/><text x="742" y="148" font-weight="700">Independent worker A</text><text x="742" y="174" font-size="14">exact commit + run contract</text>
<rect x="720" y="220" width="240" height="85" rx="14" fill="#dff6e7" stroke="#43855a"/><text x="742" y="253" font-weight="700">Independent worker B</text><text x="742" y="279" font-size="14">lease, retry, fixed evidence</text>
<rect x="370" y="390" width="265" height="105" rx="14" fill="#ffe5dc" stroke="#b65e42"/><text x="392" y="423" font-weight="700">Deterministic evaluator</text><text x="392" y="449" font-size="14">paired seeds + frozen D1 rule</text><text x="392" y="473" font-size="14">agent claims have no authority</text>
<rect x="720" y="390" width="240" height="105" rx="14" fill="#dcecff" stroke="#3974a8"/><text x="742" y="423" font-weight="700">Per-arm incumbents</text><text x="742" y="449" font-size="14">KEEP advances named arm only</text><text x="742" y="473" font-size="14">REVERT retains evidence</text>
<rect x="370" y="555" width="590" height="62" rx="14" fill="#e9eef2" stroke="#667989"/><text x="392" y="584" font-weight="700">Preregistered M8 study + durable JSON/CSV/Markdown/HTML reports</text><text x="392" y="604" font-size="13">complete results, failures, costs, hashes, limitations, and paired confirmation</text>
<rect x="1005" y="95" width="150" height="210" rx="14" fill="#fff" stroke="#a8b3bd" stroke-dasharray="7 5"/><text x="1026" y="128" font-weight="700">Frozen inside run</text><text x="1026" y="158" font-size="13">base VLA</text><text x="1026" y="183" font-size="13">simulator/reset</text><text x="1026" y="208" font-size="13">success labels</text><text x="1026" y="233" font-size="13">canonical RLinf</text><text x="1026" y="258" font-size="13">evaluator</text><text x="1026" y="283" font-size="13">budget rules</text>
</g>
<g fill="none" stroke="#47627a" stroke-width="3" marker-end="url(#arrow)"><path d="M280 126 C330 126 330 175 375 175"/><path d="M280 211 L375 211"/><path d="M280 296 C330 296 330 245 375 245"/><path d="M625 180 C665 180 675 158 720 158"/><path d="M625 240 C665 240 675 262 720 262"/><path d="M840 305 C840 350 635 345 565 390"/><path d="M635 442 L720 442"/><path d="M840 495 L840 555"/><path d="M502 495 L502 555"/></g>
<path d="M960 158 L1005 158" stroke="#a8b3bd" stroke-width="2" stroke-dasharray="6 5"/><text x="966" y="148" font-family="system-ui" font-size="12" fill="#667989">uses</text>
</svg>"""
    try:
        ET.fromstring(svg)
    except ET.ParseError as error:  # pragma: no cover - static invariant
        raise DeliveryError("embedded architecture SVG is invalid") from error
    return svg + "\n"


def render_delivery_markdown(payload: Mapping[str, Any]) -> str:
    components = payload["components"]
    m4 = components["m4_policy_improvement"]
    m7 = components["m7_distributed_execution"]
    m8 = components["m8_three_arm_study"]
    d1 = payload["d1_replay"]
    lines = [
        f"# {payload['notice']}",
        "",
        "## Outcome",
        "",
        "The complete coding-agent supervisor control plane is ready for an "
        "offline meeting demonstration. This bundle does not contain a real "
        "RLT improvement result.",
        "",
        f"Delivery fingerprint: `{payload['delivery_fingerprint']}`  ",
        f"Supervisor commit: `{payload['repository']['head']}`  ",
        f"D1 replay: `{d1['status']}`",
        "",
        "![Supervisor architecture](architecture.svg)",
        "",
        "## Demonstrated components",
        "",
        "| Component | Evidence | Result |",
        "|---|---|---|",
        f"| M4 policy improvement | structured proposal → isolated candidate → frozen evaluation | `{m4['status']}/{m4['decision']}`; {m4['invalid_attempts_before_acceptance']} invalid attempt retained |",
        f"| M7 distributed execution | two independent workers, loss/retry, stale rejection | parallelism `{m7['first_batch_parallelism']}`; `{m7['completed_trial_count']}` trials complete |",
        f"| M8 three-arm study | 3 discovery slots/arm plus paired confirmation | `{m8['discovery_records']}` discovery; `{m8['confirmation_records']}` confirmation; `{m8['worker_seed_runs']}` seed records |",
        "",
        "## What this proves",
        "",
    ]
    lines.extend(f"- {item}" for item in payload["what_this_proves"])
    lines.extend(["", "## What this does not prove", ""])
    lines.extend(f"- {item}" for item in payload["what_this_does_not_prove"])
    lines.extend(["", "## Meeting sequence", ""])
    lines.extend(f"{index}. {item}" for index, item in enumerate(payload["meeting_steps"], start=1))
    lines.extend(["", "## D1 handoff", ""])
    if d1["status"] == "ready":
        lines.append(
            "The supplied D1 pack replayed equivalently and can provide the "
            "identity/evidence seam for an explicitly approved live campaign."
        )
    elif d1["requested"]:
        lines.append(
            "The supplied D1 repository is not ready. The offline demo remains "
            "valid; no real policy or arm comparison should be claimed."
        )
        lines.extend(f"- {item}" for item in d1["reasons"])
    else:
        lines.append(
            "D1 was not requested. Use `--d1-repository` for a read-only gate "
            "replay when the reviewed Stage-7 pack is available."
        )
    lines.extend(["", "## Limitations", ""])
    lines.extend(f"- {item}" for item in payload["limitations"])
    lines.append("")
    return "\n".join(lines)


def render_delivery_html(payload: Mapping[str, Any], markdown: str) -> str:
    components = payload["components"]
    cards = "".join(
        f"<article><h3>{html.escape(title)}</h3><p>{html.escape(text)}</p></article>"
        for title, text in (
            (
                "M4 · Policy improvement",
                f"{components['m4_policy_improvement']['status']} / {components['m4_policy_improvement']['decision']}",
            ),
            (
                "M7 · Worker orchestration",
                f"parallelism {components['m7_distributed_execution']['first_batch_parallelism']}; stale result rejected",
            ),
            (
                "M8 · Three-arm study",
                f"{components['m8_three_arm_study']['discovery_records']} discovery + {components['m8_three_arm_study']['confirmation_records']} confirmation records",
            ),
        )
    )
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>RLT coding-agent supervisor demo</title>
<style>:root{{--ink:#142638;--blue:#27699c;--paper:#f4f7fa;--warning:#fff0c2}}
body{{margin:0;font:16px/1.5 system-ui;color:var(--ink);background:var(--paper)}}
main{{max-width:1180px;margin:auto;padding:36px 24px 70px}}.notice{{background:var(--warning);border:2px solid #a56500;padding:14px 18px;font-weight:800;border-radius:10px}}
h1{{font-size:42px;line-height:1.08;margin:34px 0 12px}}.lede{{font-size:20px;max-width:850px}}
.meta{{font-family:ui-monospace,monospace;background:#e9eef2;padding:12px;border-radius:8px;overflow-wrap:anywhere}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:16px;margin:28px 0}}article{{background:white;border:1px solid #ccd6df;border-radius:14px;padding:18px;box-shadow:0 4px 14px #1b334414}}
.diagram{{width:100%;background:white;border:1px solid #ccd6df;border-radius:16px;margin:24px 0}}pre{{white-space:pre-wrap;background:white;padding:22px;border-radius:12px;border:1px solid #ccd6df}}
@media(max-width:800px){{.cards{{grid-template-columns:1fr}}h1{{font-size:34px}}}}</style></head>
<body><main><div class="notice">{html.escape(str(payload['notice']))}</div>
<h1>Audited coding-agent supervision for RLT</h1><p class="lede">A bounded outer loop that proposes changes, runs isolated experiments, trusts deterministic evidence, and retains every failure.</p>
<p class="meta">Delivery {html.escape(str(payload['delivery_fingerprint']))}<br>Commit {html.escape(str(payload['repository']['head']))}<br>D1 replay {html.escape(str(payload['d1_replay']['status']))}</p>
<div class="cards">{cards}</div><img class="diagram" src="architecture.svg" alt="Supervisor architecture">
<h2>Presenter narrative and evidence boundary</h2><pre>{html.escape(markdown)}</pre></main></body></html>"""


def _atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=path.parent
    )
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _artifact(root: Path, relative: str, role: str) -> DeliveryArtifact:
    safe = require_safe_relative_path(relative, "delivery artifact path")
    path = (root / safe).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as error:
        raise DeliveryError("delivery artifact escapes output root") from error
    if not path.is_file() or path.is_symlink():
        raise DeliveryError(f"delivery artifact is missing or unsafe: {safe}")
    content = path.read_bytes()
    return DeliveryArtifact(
        path=safe,
        role=require_identifier(role, "delivery artifact role"),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


def write_delivery_bundle(
    *,
    output_directory: str | Path,
    payload: Mapping[str, Any],
    component_artifacts: Sequence[tuple[str, str]],
) -> DeliveryBundle:
    output = Path(output_directory).resolve()
    if payload.get("delivery_version") != M9_DELIVERY_VERSION:
        raise DeliveryError("delivery payload version is unsupported")
    if payload.get("notice") != M9_NOTICE or payload.get("scientific_claim_permitted") is not False:
        raise DeliveryError("delivery payload lost its claim boundary")
    markdown = render_delivery_markdown(payload)
    generated = {
        "m9-demo.json": (json.dumps(dict(payload), indent=2, sort_keys=True) + "\n").encode(),
        "demo-report.md": markdown.encode(),
        "presentation.html": render_delivery_html(payload, markdown).encode(),
        "architecture.svg": architecture_svg().encode(),
    }
    for relative, content in generated.items():
        _atomic_write(output / relative, content)
    requested = list(component_artifacts) + [
        ("m9-demo.json", "delivery-json"),
        ("demo-report.md", "delivery-report"),
        ("presentation.html", "delivery-presentation"),
        ("architecture.svg", "architecture-view"),
    ]
    paths = [item[0] for item in requested]
    if len(set(paths)) != len(paths):
        raise DeliveryError("delivery artifact paths must be unique")
    artifacts = tuple(_artifact(output, path, role) for path, role in requested)
    manifest = {
        "manifest_version": "m9-artifact-manifest-v1",
        "delivery_version": M9_DELIVERY_VERSION,
        "delivery_fingerprint": require_sha256(
            payload.get("delivery_fingerprint"), "delivery fingerprint"
        ),
        "notice": M9_NOTICE,
        "artifacts": [item.to_dict() for item in artifacts],
    }
    manifest_path = output / "artifact-manifest.json"
    _atomic_write(manifest_path, (canonical_json(manifest) + "\n").encode())
    verified = verify_artifact_manifest(output)
    return DeliveryBundle(
        output_directory=str(output),
        delivery_fingerprint=manifest["delivery_fingerprint"],
        manifest_path=str(manifest_path),
        artifacts=verified,
    )


def verify_artifact_manifest(output_directory: str | Path) -> tuple[DeliveryArtifact, ...]:
    output = Path(output_directory).resolve()
    path = output / "artifact-manifest.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise DeliveryError("M9 artifact manifest is unreadable") from error
    data = require_exact_keys(
        raw,
        "M9 artifact manifest",
        {"manifest_version", "delivery_version", "delivery_fingerprint", "notice", "artifacts"},
    )
    if data["manifest_version"] != "m9-artifact-manifest-v1" or data["delivery_version"] != M9_DELIVERY_VERSION:
        raise DeliveryError("M9 artifact manifest version is unsupported")
    if data["notice"] != M9_NOTICE:
        raise DeliveryError("M9 artifact manifest lost its synthetic notice")
    require_sha256(data["delivery_fingerprint"], "manifest delivery fingerprint")
    rows = data["artifacts"]
    if not isinstance(rows, list) or not rows:
        raise DeliveryError("M9 artifact manifest must contain artifacts")
    artifacts: list[DeliveryArtifact] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        item = require_exact_keys(
            row,
            f"M9 artifact {index}",
            {"path", "role", "sha256", "size_bytes"},
        )
        relative = require_safe_relative_path(item["path"], "manifest artifact path")
        if relative in seen or relative == "artifact-manifest.json":
            raise DeliveryError("manifest artifact paths must be unique and non-recursive")
        seen.add(relative)
        artifact = _artifact(output, relative, item["role"])
        if artifact.sha256 != require_sha256(item["sha256"], "manifest artifact hash") or artifact.size_bytes != _require_int(item["size_bytes"], "manifest artifact size"):
            raise DeliveryError(f"artifact does not match manifest: {relative}")
        artifacts.append(artifact)
    return tuple(artifacts)
