"""Frozen C0 Claude provider policy and no-call local audit."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path
from typing import Any

from supervisor.attempts import MAX_PROPOSAL_ATTEMPTS, MAX_REPAIR_REQUEST_BYTES
from supervisor.canonical import canonical_json, fingerprint
from supervisor.context import (
    MAX_BASELINE_SUMMARY_BYTES,
    MAX_BOUNDARY_BYTES,
    MAX_CONTEXT_BYTES,
    MAX_DELTA_SUMMARY_BYTES,
    MAX_EXCERPT_BYTES,
    MAX_EXCERPTS,
    MAX_METRIC_DEFINITION_BYTES,
    MAX_PRIOR_SUMMARY_BYTES,
    MAX_PRIOR_TRIALS,
    SYSTEM_INSTRUCTION,
)
from supervisor.proposals import (
    MAX_DIFF_BYTES,
    MAX_HYPOTHESIS_CHARS,
    MAX_TESTS,
    PROPOSAL_SCHEMA_HASH,
)
from supervisor.providers import (
    MAX_PROVIDER_OUTPUT_BYTES,
    MAX_PROVIDER_TIMEOUT_SECONDS,
    MAX_REPAIR_FEEDBACK_BYTES,
    PROVIDER_CREDENTIAL_ENVIRONMENT,
    RUNTIME_ENVIRONMENT,
    ClaudeCliProvider,
)


C0_CONTRACT_ID = "c0-claude-direct-v1"
C0_CLI_VERSION = "2.1.236 (Claude Code)"
C0_MODEL = "claude-opus-5"
C0_EFFORT = "medium"
C0_CREDENTIAL_BACKEND = "anthropic-direct"
C0_MAX_TOTAL_COST_USD = "0.5"
C0_TIMEOUT_SECONDS = 600

REQUIRED_CLI_FLAGS = (
    "--print",
    "--bare",
    "--safe-mode",
    "--disable-slash-commands",
    "--no-chrome",
    "--input-format",
    "--output-format",
    "--json-schema",
    "--no-session-persistence",
    "--tools",
    "--permission-mode",
    "--max-budget-usd",
    "--model",
    "--effort",
    "--system-prompt",
)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _command_output(executable: Path, argument: str) -> str:
    completed = subprocess.run(
        [str(executable), argument],
        env={},
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=10,
        check=False,
        shell=False,
    )
    if completed.returncode != 0:
        return f"<exit:{completed.returncode}>"
    return completed.stdout.strip()


def frozen_contract() -> dict[str, Any]:
    allowed_environment = sorted(
        RUNTIME_ENVIRONMENT
        | PROVIDER_CREDENTIAL_ENVIRONMENT[C0_CREDENTIAL_BACKEND]
    )
    return {
        "contract_id": C0_CONTRACT_ID,
        "provider": ClaudeCliProvider.name,
        "credential_backend": C0_CREDENTIAL_BACKEND,
        "cli_version": C0_CLI_VERSION,
        "model": C0_MODEL,
        "effort": C0_EFFORT,
        "timeout_seconds": C0_TIMEOUT_SECONDS,
        "max_total_cost_usd": C0_MAX_TOTAL_COST_USD,
        "max_attempts": MAX_PROPOSAL_ATTEMPTS,
        "allowed_environment_names": allowed_environment,
        "required_cli_flags": list(REQUIRED_CLI_FLAGS),
        "schema_hash": PROPOSAL_SCHEMA_HASH,
        "system_instruction_hash": fingerprint(SYSTEM_INSTRUCTION),
        "limits": {
            "baseline_summary_bytes": MAX_BASELINE_SUMMARY_BYTES,
            "boundary_bytes": MAX_BOUNDARY_BYTES,
            "context_bytes": MAX_CONTEXT_BYTES,
            "delta_summary_bytes": MAX_DELTA_SUMMARY_BYTES,
            "diff_bytes": MAX_DIFF_BYTES,
            "excerpt_bytes": MAX_EXCERPT_BYTES,
            "excerpts": MAX_EXCERPTS,
            "hypothesis_characters": MAX_HYPOTHESIS_CHARS,
            "metric_definition_bytes": MAX_METRIC_DEFINITION_BYTES,
            "prior_summary_bytes": MAX_PRIOR_SUMMARY_BYTES,
            "prior_trials": MAX_PRIOR_TRIALS,
            "provider_output_bytes": MAX_PROVIDER_OUTPUT_BYTES,
            "repair_feedback_bytes": MAX_REPAIR_FEEDBACK_BYTES,
            "repair_request_bytes": MAX_REPAIR_REQUEST_BYTES,
            "requested_tests": MAX_TESTS,
        },
    }


def audit_local_contract(executable: Path, working_directory: Path) -> dict[str, Any]:
    contract = frozen_contract()
    version = _command_output(executable, "--version")
    help_text = _command_output(executable, "--help")
    provider = ClaudeCliProvider(
        executable=executable,
        working_directory=working_directory,
        environment={"PATH": "/usr/bin", "ANTHROPIC_API_KEY": "redacted"},
        credential_backend=C0_CREDENTIAL_BACKEND,
        effort=C0_EFFORT,
    )
    argv = provider.build_argv(
        model=C0_MODEL, max_budget_usd=C0_MAX_TOTAL_COST_USD
    )
    shape = list(argv)
    shape[0] = "{absolute_executable}"
    shape[shape.index("--json-schema") + 1] = "{proposal_schema_json}"
    shape[shape.index("--system-prompt") + 1] = "{system_instruction}"

    violations: list[str] = []
    if version != C0_CLI_VERSION:
        violations.append(
            f"CLI version mismatch: expected {C0_CLI_VERSION!r}, observed {version!r}"
        )
    for flag in REQUIRED_CLI_FLAGS:
        if flag not in help_text:
            violations.append(f"CLI help does not advertise {flag}")
        if flag not in argv:
            violations.append(f"adapter invocation omits {flag}")
    if argv[argv.index("--tools") + 1] != "":
        violations.append("tools value is not empty")
    if argv[argv.index("--permission-mode") + 1] != "dontAsk":
        violations.append("permission mode is not dontAsk")
    if set(provider.environment) != {"PATH", "ANTHROPIC_API_KEY"}:
        violations.append("sanitized environment differs from the direct-backend policy")
    if C0_TIMEOUT_SECONDS != MAX_PROVIDER_TIMEOUT_SECONDS:
        violations.append("C0 timeout differs from the adapter ceiling")

    return {
        "schema_version": 1,
        "status": "passed" if not violations else "blocked",
        "provider_call_made": False,
        "contract": contract,
        "contract_hash": fingerprint(contract),
        "local_cli": {
            "command_path": str(executable),
            "resolved_path": str(executable.resolve()),
            "binary_sha256": _sha256_file(executable.resolve()),
            "version": version,
        },
        "invocation_shape": shape,
        "invocation_shape_hash": fingerprint(shape),
        "violations": violations,
    }


def canonical_audit_json(executable: Path, working_directory: Path) -> str:
    return canonical_json(audit_local_contract(executable, working_directory))
