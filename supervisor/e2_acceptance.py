"""Identity reconciliation for the E2 live-objective acceptance gate."""

from __future__ import annotations

from typing import Any, Mapping

from supervisor.canonical import ContractError, require_sha256
from supervisor.objective_validation import OBJECTIVE_CONTRACT_VERSION


class E2AcceptanceError(ContractError):
    """Raised when E2 artifacts disagree about the objective that executed."""


def verify_e2_identity(
    *,
    objective_sha256: str,
    plan: Mapping[str, Any],
    manifest: Mapping[str, Any],
    runtime: Mapping[str, Any],
    evidence: Mapping[str, Any],
) -> dict[str, bool]:
    """Require one objective identity across every E2 execution boundary."""

    expected = require_sha256(objective_sha256, "E2 objective hash")
    checks = {
        "plan": plan.get("objective_sha256") == expected,
        "plan_contract": (
            plan.get("objective_contract_version") == OBJECTIVE_CONTRACT_VERSION
        ),
        "logical_command": (
            f"objective.sha256={expected}" in plan.get("logical_rlinf_command", [])
        ),
        "execution_command": expected in plan.get("execution_argv", []),
        "manifest": manifest.get("objective_sha256") == expected,
        "manifest_contract": (
            manifest.get("objective_contract_version") == OBJECTIVE_CONTRACT_VERSION
        ),
        "manifest_validation": (
            isinstance(manifest.get("objective_validation"), dict)
            and manifest["objective_validation"].get("source_sha256") == expected
            and manifest["objective_validation"].get("behavior_changed") is True
            and manifest["objective_validation"].get("errors") == []
        ),
        "runtime": runtime.get("objective_sha256") == expected,
        "runtime_attachment": (
            isinstance(runtime.get("attachment"), dict)
            and runtime["attachment"].get("objective_sha256") == expected
            and runtime["attachment"].get("objective_contract_version")
            == OBJECTIVE_CONTRACT_VERSION
        ),
        "evidence": any(
            isinstance(item, dict)
            and item.get("kind") == "actor-objective"
            and item.get("sha256") == expected
            for item in evidence.get("artifacts", [])
        ),
    }
    failed = sorted(name for name, passed in checks.items() if not passed)
    if failed:
        raise E2AcceptanceError(
            "E2 objective identity mismatch at: " + ", ".join(failed)
        )
    return checks
