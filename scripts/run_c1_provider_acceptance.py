#!/usr/bin/env python3
"""Prepare or execute the paid, no-GPU C1 Claude acceptance slot."""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.attempts import ProposalAttemptController  # noqa: E402
from supervisor.c1_acceptance import (  # noqa: E402
    C1_BASE_COMMIT,
    C1_PROPOSAL_SLOT_ID,
    build_c1_context,
    context_record,
    repository_snapshot,
)
from supervisor.canonical import canonical_json, fingerprint  # noqa: E402
from supervisor.provider_contract import (  # noqa: E402
    C0_CREDENTIAL_BACKEND,
    C0_EFFORT,
    C0_MAX_TOTAL_COST_USD,
    C0_MODEL,
    C0_TIMEOUT_SECONDS,
    frozen_contract,
)
from supervisor.providers import ClaudeCliProvider, ProposalProvider  # noqa: E402


class RecordingProvider:
    """Retain structured payloads while preserving the provider-neutral seam."""

    def __init__(self, provider: ProposalProvider) -> None:
        self.provider = provider
        self.name = provider.name
        self.payloads: list[dict[str, Any]] = []

    def generate(self, *args, **kwargs):
        result = self.provider.generate(*args, **kwargs)
        self.payloads.append(dict(result.proposal_payload))
        return result


def _write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical_json(value) + "\n", encoding="utf-8")


def _prepared_records(output: Path) -> tuple[Any, Any]:
    campaign, context = build_c1_context(ROOT)
    record = context_record(campaign, context)
    _write(output / "campaign.json", campaign.to_dict())
    _write(output / "context.json", record)
    return campaign, context


def prepare(output: Path) -> int:
    campaign, context = _prepared_records(output)
    credential_ready = bool(os.environ.get("ANTHROPIC_API_KEY"))
    preflight = {
        "schema_version": 1,
        "status": "ready" if credential_ready else "blocked",
        "provider_call_made": False,
        "credential_backend": C0_CREDENTIAL_BACKEND,
        "credential_ready": credential_ready,
        "credential_values_recorded": False,
        "authorized_max_cost_usd": C0_MAX_TOTAL_COST_USD,
        "gpu_authorized": False,
        "campaign_hash": campaign.fingerprint(),
        "context_hash": context.context_hash,
        "provider_contract_hash": fingerprint(frozen_contract()),
        "blockers": [] if credential_ready else ["ANTHROPIC_API_KEY is not present"],
    }
    _write(output / "preflight.json", preflight)
    return 0 if credential_ready else 2


def execute(output: Path, executable: Path) -> int:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        raise SystemExit("blocked before provider call: ANTHROPIC_API_KEY is not present")
    campaign, context = build_c1_context(ROOT)
    expected_campaign = canonical_json(campaign.to_dict()) + "\n"
    expected_context = canonical_json(context_record(campaign, context)) + "\n"
    if (output / "campaign.json").read_text(encoding="utf-8") != expected_campaign:
        raise SystemExit("blocked before provider call: campaign artifact drifted")
    if (output / "context.json").read_text(encoding="utf-8") != expected_context:
        raise SystemExit("blocked before provider call: context artifact drifted")

    before = repository_snapshot(ROOT)
    if not before["clean"]:
        raise SystemExit("blocked before provider call: repository is not clean")
    provider = RecordingProvider(
        ClaudeCliProvider(
            executable=executable,
            working_directory=ROOT,
            credential_backend=C0_CREDENTIAL_BACKEND,
            effort=C0_EFFORT,
        )
    )
    session = ProposalAttemptController(
        campaign=campaign,
        context=context,
        incumbent_commit=C1_BASE_COMMIT,
        provider=provider,
        model=C0_MODEL,
        proposal_slot_id=C1_PROPOSAL_SLOT_ID,
        max_total_cost_usd=C0_MAX_TOTAL_COST_USD,
        timeout_seconds=C0_TIMEOUT_SECONDS,
    ).run()
    after = repository_snapshot(ROOT)
    unchanged = before == after
    report = {
        "schema_version": 1,
        "status": "passed" if unchanged else "blocked",
        "claim_scope": "provider-contract acceptance only; no performance claim",
        "provider_contract_hash": fingerprint(frozen_contract()),
        "campaign_hash": campaign.fingerprint(),
        "context_hash": context.context_hash,
        "repository_before": before,
        "repository_after": after,
        "repository_unchanged_during_call": unchanged,
        "gpu_used": False,
        "tools_available": [],
        "structured_payloads": provider.payloads,
        "session": session.to_dict(),
        "session_hash": session.fingerprint(),
    }
    _write(output / "session.json", report)
    return 0 if unchanged else 2


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output", type=Path, default=ROOT / "results/provider-acceptance/c1"
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--acknowledge-paid-provider-call", action="store_true")
    parser.add_argument("--claude", type=Path)
    args = parser.parse_args()
    if not args.execute:
        return prepare(args.output)
    if not args.acknowledge_paid_provider_call:
        parser.error("--execute requires --acknowledge-paid-provider-call")
    found = args.claude or (Path(value) if (value := shutil.which("claude")) else None)
    if found is None:
        parser.error("Claude CLI was not found; pass --claude")
    return execute(args.output, found.absolute())


if __name__ == "__main__":
    raise SystemExit(main())
