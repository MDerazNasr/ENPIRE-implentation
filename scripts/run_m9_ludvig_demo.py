#!/usr/bin/env python3
"""Build the offline-first M9 meeting bundle and optional read-only D1 replay."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.canonical import fingerprint  # noqa: E402
from supervisor.d1_gate import D1GateStatus, run_d1_integration_gate  # noqa: E402
from supervisor.delivery import (  # noqa: E402
    M9_NOTICE,
    DeliveryError,
    build_delivery_payload,
    write_delivery_bundle,
)


def git(repository: Path, *arguments: str) -> str:
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise DeliveryError(f"supervisor repository Git check failed: {arguments}") from error
    return completed.stdout.strip()


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def preflight(repository: Path, output: Path) -> dict[str, Any]:
    repository = repository.resolve()
    output = output.resolve()
    if not (repository / ".git").exists():
        raise DeliveryError("--repository must be a Git worktree root")
    if _inside(output, repository):
        raise DeliveryError("demo output must be outside the supervisor repository")
    if output.exists() and any(output.iterdir()):
        raise DeliveryError("demo output directory must be absent or empty")
    required = (
        ROOT / "scripts" / "run_m4_offline_demo.py",
        ROOT / "scripts" / "run_m7_scheduler_demo.py",
        ROOT / "scripts" / "run_m8_study_demo.py",
    )
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise DeliveryError(f"required component scripts are missing: {missing}")
    head = git(repository, "rev-parse", "HEAD")
    branch = git(repository, "branch", "--show-current") or "detached"
    clean = not bool(git(repository, "status", "--porcelain"))
    if not clean:
        raise DeliveryError("supervisor repository must be clean before the final demo")
    return {
        "repository": repository,
        "output": output,
        "head": head,
        "branch": branch,
        "clean": clean,
        "scripts": required,
    }


def component_environment() -> dict[str, str]:
    environment = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    temporary = os.environ.get("TMPDIR")
    if temporary:
        environment["TMPDIR"] = temporary
    return environment


def run_component(
    *,
    name: str,
    script: Path,
    arguments: Sequence[str],
    timeout_seconds: int = 120,
) -> tuple[dict[str, Any], dict[str, Any]]:
    argv = [sys.executable, str(script), *arguments]
    logical_argv = ["python3", f"scripts/{script.name}", *arguments]
    started = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=ROOT,
            env=component_environment(),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as error:
        raise DeliveryError(f"{name} demo exceeded {timeout_seconds} seconds") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip()[-1000:] if error.stderr else "no stderr"
        raise DeliveryError(f"{name} demo failed: {message}") from error
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise DeliveryError(f"{name} demo returned non-JSON output") from error
    if not isinstance(payload, dict):
        raise DeliveryError(f"{name} demo summary must be an object")
    logical = list(logical_argv)
    for index, item in enumerate(logical):
        if index and logical[index - 1] == "--output":
            logical[index] = f"<bundle>/components/{name}"
        elif index and logical[index - 1] == "--repository":
            logical[index] = "<supervisor-repository>"
    audit = {
        "component": name,
        "logical_argv": logical,
        "command_hash": fingerprint(logical),
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "return_code": completed.returncode,
        "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
    }
    return payload, audit


def inspect_d1(repository: Path, pack_relative_path: Path) -> dict[str, Any]:
    result = run_d1_integration_gate(
        repository.resolve(), pack_relative_path=pack_relative_path
    )
    return result.to_dict() | {"gate_hash": result.fingerprint()}


def _record_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def public_value(value: Any, replacements: Sequence[tuple[str, str]]) -> Any:
    """Replace machine-local roots in curated meeting artifacts."""

    if isinstance(value, dict):
        return {key: public_value(item, replacements) for key, item in value.items()}
    if isinstance(value, list):
        return [public_value(item, replacements) for item in value]
    if isinstance(value, str):
        result = value
        for private, logical in replacements:
            if private:
                result = result.replace(private, logical)
        return result
    return value


def _relative_artifacts(
    output: Path,
    report: Any,
    *,
    role_prefix: str,
    skip_names: frozenset[str] = frozenset(),
) -> list[tuple[str, str]]:
    if not isinstance(report, dict) or not isinstance(report.get("artifacts"), list):
        raise DeliveryError(f"{role_prefix} report bundle is malformed")
    artifacts: list[tuple[str, str]] = []
    for index, item in enumerate(report["artifacts"]):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise DeliveryError(f"{role_prefix} report artifact {index} is malformed")
        if item.get("name") in skip_names:
            continue
        path = Path(item["path"]).resolve()
        try:
            relative = path.relative_to(output.resolve()).as_posix()
        except ValueError as error:
            raise DeliveryError(f"{role_prefix} artifact escapes the M9 output") from error
        artifacts.append((relative, f"{role_prefix}-artifact"))
    return artifacts


def run(
    *,
    repository: Path,
    output: Path,
    d1_repository: Path | None = None,
    d1_pack_relative_path: Path = Path("results/d1-stage7/evidence_pack.json"),
    require_d1_ready: bool = False,
) -> dict[str, Any]:
    checked = preflight(repository, output)
    output = checked["output"]
    output.mkdir(parents=True, exist_ok=True)

    public_replacements = (
        (str(output), "<bundle>"),
        (str(checked["repository"]), "<supervisor-repository>"),
        (str(ROOT), "<supervisor-source>"),
        (sys.executable, "python3"),
    )

    d1_payload = None
    if d1_repository is not None:
        d1_payload = inspect_d1(d1_repository, d1_pack_relative_path)
        d1_public = public_value(
            d1_payload,
            (*public_replacements, (str(d1_repository.resolve()), "<d1-repository>")),
        )
        _record_json(output / "d1-replay.json", d1_public)
        if require_d1_ready and d1_payload["status"] != D1GateStatus.READY.value:
            blocked = {
                "notice": M9_NOTICE,
                "status": "blocked",
                "reason": "--require-d1-ready was set and the read-only D1 gate is not ready",
                "d1_replay": d1_public,
                "external_calls": [],
            }
            _record_json(output / "m9-blocked.json", blocked)
            return blocked
    elif require_d1_ready:
        raise DeliveryError("--require-d1-ready requires --d1-repository")

    components = output / "components"
    m4_output = components / "m4"
    m7_output = components / "m7"
    m8_output = components / "m8"
    m4, m4_audit = run_component(
        name="m4",
        script=ROOT / "scripts" / "run_m4_offline_demo.py",
        arguments=("--output", str(m4_output)),
    )
    _record_json(
        components / "m4-summary.json",
        public_value(m4, public_replacements),
    )
    m7, m7_audit = run_component(
        name="m7",
        script=ROOT / "scripts" / "run_m7_scheduler_demo.py",
        arguments=(
            "--output", str(m7_output), "--repository", str(checked["repository"]),
        ),
    )
    m8, m8_audit = run_component(
        name="m8",
        script=ROOT / "scripts" / "run_m8_study_demo.py",
        arguments=("--output", str(m8_output)),
    )
    _record_json(
        m8_output / "m8-demo.json",
        public_value(m8, public_replacements),
    )

    raw_m4_report = Path(
        next(
            item["path"]
            for item in m4["report"]["artifacts"]
            if item.get("name") == "report.json"
        )
    )
    public_m4_report = components / "m4" / "public" / "report.json"
    _record_json(
        public_m4_report,
        public_value(
            json.loads(raw_m4_report.read_text(encoding="utf-8")),
            public_replacements,
        ),
    )

    head_after = git(checked["repository"], "rev-parse", "HEAD")
    clean_after = not bool(git(checked["repository"], "status", "--porcelain"))
    if head_after != checked["head"]:
        raise DeliveryError("supervisor HEAD changed during the demo")
    payload = build_delivery_payload(
        repository_head=checked["head"],
        repository_branch=checked["branch"],
        repository_clean_before=checked["clean"],
        repository_clean_after=clean_after,
        m4=m4,
        m7=m7,
        m8=m8,
        d1=d1_payload,
    )
    payload["execution"] = {
        "components": [m4_audit, m7_audit, m8_audit],
        "elapsed_seconds": round(
            sum(item["elapsed_seconds"] for item in (m4_audit, m7_audit, m8_audit)),
            6,
        ),
        "component_order": ["m4", "m7", "m8"],
    }

    artifacts: list[tuple[str, str]] = [
        ("components/m4-summary.json", "m4-summary"),
        ("components/m7/m7-demo.json", "m7-summary"),
        ("components/m8/m8-demo.json", "m8-summary"),
    ]
    artifacts.extend(
        _relative_artifacts(
            output,
            m4["report"],
            role_prefix="m4",
            skip_names=frozenset({"report.json"}),
        )
    )
    artifacts.append(("components/m4/public/report.json", "m4-artifact"))
    artifacts.extend(
        _relative_artifacts(
            output,
            m8["report"],
            role_prefix="m8",
            skip_names=frozenset({"artifact-manifest.json"}),
        )
    )
    if d1_payload is not None:
        artifacts.append(("d1-replay.json", "d1-replay"))
    bundle = write_delivery_bundle(
        output_directory=output,
        payload=payload,
        component_artifacts=artifacts,
    )
    return {
        "notice": M9_NOTICE,
        "status": "complete",
        "scientific_claim_permitted": False,
        "delivery_fingerprint": payload["delivery_fingerprint"],
        "d1_status": payload["d1_replay"]["status"],
        "stable_head_unchanged": True,
        "external_calls": [],
        "bundle": bundle.to_dict(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", type=Path, default=ROOT)
    parser.add_argument("--d1-repository", type=Path)
    parser.add_argument(
        "--d1-pack-relative-path",
        type=Path,
        default=Path("results/d1-stage7/evidence_pack.json"),
    )
    parser.add_argument("--require-d1-ready", action="store_true")
    arguments = parser.parse_args()
    try:
        result = run(
            repository=arguments.repository,
            output=arguments.output,
            d1_repository=arguments.d1_repository,
            d1_pack_relative_path=arguments.d1_pack_relative_path,
            require_d1_ready=arguments.require_d1_ready,
        )
    except DeliveryError as error:
        print(f"M9 demo refused to run: {error}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "complete" else 2


if __name__ == "__main__":
    raise SystemExit(main())
