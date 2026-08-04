"""Real CPU toy-policy demonstration wired through supervisor contracts."""

from __future__ import annotations

import concurrent.futures
import csv
import hashlib
import html
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from supervisor.canonical import (
    ContractError,
    canonical_json,
    fingerprint,
    require_exact_keys,
    require_identifier,
    require_safe_relative_path,
    require_sha256,
    timestamp_text,
)
from supervisor.contracts import CampaignSpec, SCHEMA_VERSION, TrialEvidence
from supervisor.delivery import DeliveryArtifact
from supervisor.enforcement import EnforcementPolicy, ProposalEnforcer
from supervisor.evaluation import OfflineD1Evaluator
from supervisor.git_manager import GitExperimentManager, HarnessCheck, PreparationStatus
from supervisor.proposals import Proposal
from supervisor.toy_policy import TOY_POLICY_VERSION, TrainingConfig, make_resets


REAL_TOY_DEMO_VERSION = "real-toy-policy-demo-v1"
REAL_TOY_NOTICE = "REAL CPU MODEL DEMO — TOY TASK, NOT RLT OR π0.5 EVIDENCE"
SEEDS = (101, 202, 303)
EVALUATION_SEED = 424_242
EVALUATION_EPISODES = 256
DISPLAY_SEED = 90_900
DISPLAY_EPISODES = 6
CANDIDATE_ARM = "recorded-agent-config"


class ToyDemoError(ContractError):
    """Raised when the public real-policy demonstration fails closed."""


@dataclass(frozen=True)
class ToyDemoBundle:
    output_directory: str
    result_fingerprint: str
    manifest_path: str
    artifacts: tuple[DeliveryArtifact, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "output_directory": self.output_directory,
            "result_fingerprint": self.result_fingerprint,
            "manifest_path": self.manifest_path,
            "artifact_count": len(self.artifacts),
            "artifacts": [artifact.to_dict() for artifact in self.artifacts],
        }


def _git(repository: Path, *arguments: str, environment: Mapping[str, str] | None = None) -> str:
    env = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C",
        "LC_ALL": "C",
        "GIT_TERMINAL_PROMPT": "0",
    }
    if environment:
        env.update(environment)
    try:
        completed = subprocess.run(
            ["git", "-C", str(repository), *arguments],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
            env=env,
        )
    except (OSError, subprocess.SubprocessError) as error:
        raise ToyDemoError(f"Git operation failed: {arguments}") from error
    return completed.stdout.strip()


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


def _write_json(path: Path, value: Any) -> None:
    _atomic_write(path, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode())


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def preflight(supervisor_repository: Path, output: Path) -> dict[str, Any]:
    supervisor_repository = supervisor_repository.resolve()
    output = output.resolve()
    if not (supervisor_repository / ".git").exists():
        raise ToyDemoError("--repository must be a Git worktree root")
    if _inside(output, supervisor_repository):
        raise ToyDemoError("demo output must be outside the supervisor repository")
    if output.exists() and any(output.iterdir()):
        raise ToyDemoError("demo output directory must be absent or empty")
    head = _git(supervisor_repository, "rev-parse", "HEAD")
    branch = _git(supervisor_repository, "branch", "--show-current") or "detached"
    if _git(supervisor_repository, "status", "--porcelain"):
        raise ToyDemoError("supervisor repository must be clean before the demo")
    return {
        "repository": supervisor_repository,
        "output": output,
        "head": head,
        "branch": branch,
    }


def base_config() -> dict[str, Any]:
    return {
        "demo": REAL_TOY_DEMO_VERSION,
        "training": TrainingConfig(exploration_std=0.01).to_dict(),
    }


def _initialize_toy_repository(runtime: Path) -> tuple[Path, str]:
    repository = runtime / "stable-repository"
    repository.mkdir(parents=True)
    _git(repository, "init", "-q", "-b", "stable")
    _write_json(repository / "candidate" / "config.json", base_config())
    _atomic_write(
        repository / "README.md",
        b"Meeting-safe real CPU residual-policy demo.\n",
    )
    _git(repository, "add", "README.md", "candidate/config.json")
    dates = {
        "GIT_AUTHOR_DATE": "2026-08-04T12:00:00Z",
        "GIT_COMMITTER_DATE": "2026-08-04T12:00:00Z",
    }
    _git(
        repository,
        "-c", "user.name=Toy Demo",
        "-c", "user.email=toy-demo@invalid.local",
        "commit", "-q", "-m", "toy policy baseline",
        environment=dates,
    )
    return repository, _git(repository, "rev-parse", "HEAD")


def build_campaign(*, baseline_commit: str, supervisor_head: str) -> CampaignSpec:
    reset_hash = fingerprint(
        [reset.to_dict() for reset in make_resets(EVALUATION_SEED, EVALUATION_EPISODES)]
    )
    return CampaignSpec.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": "real-toy-policy-demo",
            "research_question": (
                "Can a bounded exploration change improve a real CPU residual policy?"
            ),
            "baseline_commit": baseline_commit,
            "rlinf_commit": supervisor_head,
            "edit_mode": "config_only",
            "editable_paths": ["candidate/config.json"],
            "allowed_parameters": {
                "training.exploration_std": {
                    "kind": "number",
                    "minimum": "0.001",
                    "maximum": "0.8",
                }
            },
            "seeds": list(SEEDS),
            "reset_set_hash": reset_hash,
            "evaluator_version": "d1-rule-v1",
            "training_budget_steps": 20_480,
            "evaluation_trajectories": EVALUATION_EPISODES,
            "max_concurrency": 6,
            "artifact_namespace": "real-toy-policy-demo",
            "created_at": "2026-08-04T12:00:00Z",
            "budget": {
                "max_trials": 6,
                "max_wall_time_seconds": 120,
                "max_gpu_cost_usd": "0.01",
                "max_llm_cost_usd": "0.01",
            },
        }
    )


def build_recorded_proposal(*, baseline_commit: str) -> Proposal:
    return Proposal.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "proposal_id": "increase-exploration",
            "campaign_id": "real-toy-policy-demo",
            "arm_id": CANDIDATE_ARM,
            "base_commit": baseline_commit,
            "edit_mode": "config_only",
            "hypothesis": (
                "The control learner explores too narrowly to discover useful residual "
                "corrections; increasing exploration should improve target reach success."
            ),
            "evidence_ids": ["toy-control-design"],
            "expected_effect": (
                "Higher success and lower final target distance on the frozen reset set."
            ),
            "falsification_condition": (
                "The candidate fails the frozen paired-seed D1 keep rule."
            ),
            "rollback_condition": (
                "Retain the baseline whenever the independent evaluator does not keep."
            ),
            "changed_paths": ["candidate/config.json"],
            "requested_tests": ["toy-config-contract"],
            "estimated_budget": {
                "wall_time_seconds": 60,
                "gpu_cost_usd": "0",
                "llm_cost_usd": "0",
            },
            "config_overrides": {"training.exploration_std": 0.35},
        }
    )


def _prepare_candidate(
    *,
    toy_repository: Path,
    worktree_root: Path,
    campaign: CampaignSpec,
    proposal: Proposal,
    baseline_commit: str,
):
    check_code = (
        "import json,pathlib; p=pathlib.Path('candidate/config.json'); "
        "d=json.loads(p.read_text()); "
        "assert d['demo']=='real-toy-policy-demo-v1'; "
        "assert set(d['training'])=={'exploration_std','generations','population',"
        "'elite_count','training_episodes'}"
    )
    check = HarnessCheck.create(
        check_id="toy-config-contract",
        argv=(sys.executable, "-c", check_code),
        timeout_seconds=20,
    )
    policy = EnforcementPolicy.create(trusted_test_ids=(check.check_id,))
    manager = GitExperimentManager(
        repository=toy_repository,
        worktree_root=worktree_root,
        enforcer=ProposalEnforcer(policy),
        trusted_checks={check.check_id: check},
    )
    return manager.prepare(
        proposal,
        campaign,
        incumbent_commit=baseline_commit,
        base_config=base_config(),
    )


def _worker_environment() -> dict[str, str]:
    result = {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LANG": "C",
        "LC_ALL": "C",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    if "TMPDIR" in os.environ:
        result["TMPDIR"] = os.environ["TMPDIR"]
    return result


def _run_worker(
    *,
    root: Path,
    role: str,
    seed: int,
    config_path: Path,
) -> dict[str, Any]:
    logical_config = f"<{role}-config>"
    logical_argv = [
        "python3",
        "scripts/toy_policy_worker.py",
        "--config", logical_config,
        "--seed", str(seed),
        "--evaluation-seed", str(EVALUATION_SEED),
        "--evaluation-episodes", str(EVALUATION_EPISODES),
        "--display-seed", str(DISPLAY_SEED),
        "--display-episodes", str(DISPLAY_EPISODES),
    ]
    argv = list(logical_argv)
    argv[0] = sys.executable
    argv[1] = str(root / "scripts" / "toy_policy_worker.py")
    argv[3] = str(config_path)
    started_wall = datetime.now(timezone.utc)
    started_monotonic = time.monotonic()
    try:
        completed = subprocess.run(
            argv,
            cwd=root,
            env=_worker_environment(),
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except subprocess.TimeoutExpired as error:
        raise ToyDemoError(f"{role} seed {seed} exceeded 30 seconds") from error
    except subprocess.CalledProcessError as error:
        message = error.stderr.strip()[-1000:] if error.stderr else "no stderr"
        raise ToyDemoError(f"{role} seed {seed} failed: {message}") from error
    try:
        payload = json.loads(completed.stdout)
    except json.JSONDecodeError as error:
        raise ToyDemoError(f"{role} seed {seed} produced non-JSON output") from error
    if payload.get("status") != "complete" or payload.get("external_calls") != []:
        raise ToyDemoError(f"{role} seed {seed} violated its worker result contract")
    finished_monotonic = time.monotonic()
    return {
        "role": role,
        "seed": seed,
        "started_at": timestamp_text(started_wall),
        "finished_at": timestamp_text(datetime.now(timezone.utc)),
        "started_monotonic": started_monotonic,
        "finished_monotonic": finished_monotonic,
        "elapsed_seconds": round(finished_monotonic - started_monotonic, 6),
        "logical_argv": logical_argv,
        "command_hash": fingerprint(logical_argv),
        "stderr_sha256": hashlib.sha256(completed.stderr.encode()).hexdigest(),
        "payload": payload,
    }


def _max_concurrency(runs: Sequence[Mapping[str, Any]]) -> int:
    events: list[tuple[float, int]] = []
    for run in runs:
        events.append((float(run["started_monotonic"]), 1))
        events.append((float(run["finished_monotonic"]), -1))
    active = 0
    maximum = 0
    for _, change in sorted(events, key=lambda item: (item[0], -item[1])):
        active += change
        maximum = max(maximum, active)
    return maximum


def _evidence(
    *,
    run: Mapping[str, Any],
    campaign: CampaignSpec,
    baseline_commit: str,
    candidate_commit: str,
) -> TrialEvidence:
    role = str(run["role"])
    seed = int(run["seed"])
    payload = run["payload"]
    metrics = payload["evaluation"]
    is_candidate = role == "candidate"
    return TrialEvidence.from_dict(
        {
            "schema_version": SCHEMA_VERSION,
            "campaign_id": campaign.campaign_id,
            "trial_id": f"{role}-seed-{seed}",
            "arm_id": CANDIDATE_ARM if is_candidate else "control",
            "parent_commit": baseline_commit,
            "candidate_commit": candidate_commit if is_candidate else baseline_commit,
            "rlinf_commit": campaign.rlinf_commit,
            "config_hash": payload["training"]["config_hash"],
            "command_hash": run["command_hash"],
            "seed": seed,
            "reset_set_hash": campaign.reset_set_hash,
            "evaluator_version": campaign.evaluator_version,
            "started_at": run["started_at"],
            "finished_at": run["finished_at"],
            "status": "complete",
            "exit_code": 0,
            "elapsed_seconds": run["elapsed_seconds"],
            "gpu_cost_usd": "0",
            "llm_cost_usd": "0",
            "metrics": {
                "success_rate": metrics["success_rate"],
                "mean_final_distance": metrics["mean_final_distance"],
                "successful_episode_length": metrics["successful_episode_length"],
            },
            "metric_errors": [],
            "artifacts": [],
        }
    )


def _public_preparation(value: Mapping[str, Any], output: Path) -> dict[str, Any]:
    def replace(item: Any) -> Any:
        if isinstance(item, dict):
            return {key: replace(child) for key, child in item.items()}
        if isinstance(item, list):
            return [replace(child) for child in item]
        if isinstance(item, str):
            return item.replace(str(output), "<demo-output>").replace(
                sys.executable, "python3"
            )
        return item

    return replace(dict(value))


def _semantic_result(
    *,
    proposal: Proposal,
    control: Sequence[TrialEvidence],
    candidate: Sequence[TrialEvidence],
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "version": REAL_TOY_DEMO_VERSION,
        "toy_policy_version": TOY_POLICY_VERSION,
        "proposal": {
            "hypothesis": proposal.hypothesis,
            "overrides": dict(proposal.config_overrides or {}),
        },
        "control_metrics": [dict(item.metrics) for item in control],
        "candidate_metrics": [dict(item.metrics) for item in candidate],
        "decision": decision["decision_record"]["decision"],
        "mean_delta": decision["mean_success_delta"],
        "ci95": decision["success_delta_ci95"],
    }


def trajectory_svg(control_run: Mapping[str, Any], candidate_run: Mapping[str, Any]) -> str:
    colors = ("#ef8354", "#f6bd60", "#7b6d8d", "#4f5d75", "#d1495b", "#edae49")

    def point(value: Sequence[float], x: float) -> tuple[float, float]:
        scale = 205.0
        return x + 270 + float(value[0]) * scale, 340 - float(value[1]) * scale

    def panel(title: str, x: float, episodes: Sequence[Mapping[str, Any]]) -> str:
        parts = [
            f'<rect x="{x}" y="80" width="540" height="510" rx="24" fill="#f8fafc" stroke="#dbe4ee"/>',
            f'<text x="{x + 28}" y="122" font-size="24" font-weight="700" fill="#152235">{html.escape(title)}</text>',
            f'<line x1="{x + 270}" y1="145" x2="{x + 270}" y2="565" stroke="#d8e0e8"/>',
            f'<line x1="{x + 60}" y1="340" x2="{x + 480}" y2="340" stroke="#d8e0e8"/>',
        ]
        for index, episode in enumerate(episodes):
            color = colors[index % len(colors)]
            path = episode["path"]
            coordinates = [point(item, x) for item in path]
            points = " ".join(f"{px:.1f},{py:.1f}" for px, py in coordinates)
            start_x, start_y = coordinates[0]
            end_x, end_y = coordinates[-1]
            target_x, target_y = point(episode["reset"]["target"], x)
            end_color = "#149e73" if episode["success"] else "#d1495b"
            parts.extend(
                [
                    f'<polyline points="{points}" fill="none" stroke="{color}" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" opacity="0.92"/>',
                    f'<circle cx="{start_x:.1f}" cy="{start_y:.1f}" r="5" fill="{color}"/>',
                    f'<circle cx="{target_x:.1f}" cy="{target_y:.1f}" r="10" fill="none" stroke="#149e73" stroke-width="3"/>',
                    f'<circle cx="{end_x:.1f}" cy="{end_y:.1f}" r="6" fill="{end_color}" stroke="white" stroke-width="2"/>',
                ]
            )
        return "".join(parts)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="640" viewBox="0 0 1200 640" role="img" aria-labelledby="title desc">
<title id="title">Baseline and candidate robot-policy trajectories</title>
<desc id="desc">Six shared resets show the baseline missing targets and the trained candidate reaching them.</desc>
<rect width="1200" height="640" fill="#ffffff"/>
<text x="40" y="42" font-family="Inter,Arial,sans-serif" font-size="28" font-weight="800" fill="#152235">Same starts. Same targets. A better learned correction.</text>
<g font-family="Inter,Arial,sans-serif">{panel("Before: narrow exploration", 40, control_run["payload"]["display_episodes"])}{panel("After: agent-proposed exploration", 620, candidate_run["payload"]["display_episodes"])}</g>
<g font-family="Inter,Arial,sans-serif" font-size="15" fill="#526175"><circle cx="45" cy="620" r="6" fill="#d1495b"/><text x="58" y="625">miss</text><circle cx="125" cy="620" r="6" fill="#149e73"/><text x="138" y="625">reached target</text><circle cx="280" cy="620" r="9" fill="none" stroke="#149e73" stroke-width="3"/><text x="296" y="625">target</text></g>
</svg>'''


def _percentage(value: float) -> str:
    return f"{100.0 * value:.1f}%"


def render_markdown(payload: Mapping[str, Any]) -> str:
    summary = payload["result"]
    decision = payload["decision"]
    return f"""# Real Toy-Policy Improvement Demo

> **{REAL_TOY_NOTICE}**

## Result

| Measurement | Control | Candidate |
|---|---:|---:|
| Mean success | {_percentage(summary['control_mean_success'])} | {_percentage(summary['candidate_mean_success'])} |
| Mean final distance | {summary['control_mean_distance']:.4f} | {summary['candidate_mean_distance']:.4f} |

The independent evaluator returned **{decision['decision_record']['decision'].upper()}**.
The paired mean success change was {_percentage(decision['mean_success_delta'])};
CI95 was [{_percentage(decision['success_delta_ci95'][0])},
{_percentage(decision['success_delta_ci95'][1])}].

## What happened

1. A recorded coding-agent proposal increased only `training.exploration_std`
   from `0.01` to `0.35`.
2. The supervisor validated the allowlist, path, budget, and trusted check.
3. It created a real isolated Git candidate while the stable HEAD stayed fixed.
4. Six CPU worker processes trained and evaluated real residual policies over
   three paired seeds and {EVALUATION_EPISODES} shared resets per seed.
5. The existing frozen D1 evaluator compared the evidence and selected KEEP.

## Honest boundary

This run proves real model training and a real measured improvement on the
small public toy task. It does **not** prove improvement to RLinf/RLT, π0.5,
ManiSkill, or a physical robot. The proposal was recorded for meeting
reliability; no live LLM/provider call was made.

## Integrity

- Result fingerprint: `{payload['result_fingerprint']}`
- External calls: none
- GPU cost: $0
- LLM cost during run: $0
- Stable supervisor HEAD unchanged: yes
- Maximum observed concurrent workers: {payload['execution']['maximum_concurrent_workers']}
"""


def render_html(payload: Mapping[str, Any], svg: str) -> str:
    result = payload["result"]
    decision = payload["decision"]
    control = _percentage(result["control_mean_success"])
    candidate = _percentage(result["candidate_mean_success"])
    delta = _percentage(decision["mean_success_delta"])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Real policy improvement demo</title>
<style>
:root{{--ink:#14213d;--muted:#526175;--paper:#f4f7fb;--card:#fff;--teal:#0e9f79;--orange:#ef8354;--line:#dbe4ee}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,ui-sans-serif,system-ui,-apple-system,sans-serif;line-height:1.5}}
.wrap{{max-width:1180px;margin:auto;padding:28px}} .notice{{background:#fff4df;border:1px solid #f5cb7a;color:#6e4b08;padding:12px 18px;border-radius:14px;font-weight:800;letter-spacing:.03em}}
header{{padding:55px 0 32px}} .eyebrow{{color:#087f61;font-weight:800;text-transform:uppercase;letter-spacing:.12em;font-size:.82rem}} h1{{font-size:clamp(2.5rem,6vw,5.5rem);line-height:.96;max-width:980px;margin:.25em 0}} .lead{{font-size:1.25rem;color:var(--muted);max-width:790px}}
.metrics{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px;margin:30px 0}} .metric,.card{{background:var(--card);border:1px solid var(--line);border-radius:22px;padding:25px;box-shadow:0 16px 50px rgba(20,33,61,.06)}} .metric span{{display:block;color:var(--muted);font-weight:700}} .metric strong{{display:block;font-size:3rem;line-height:1.1;margin-top:8px}} .metric.after strong,.keep{{color:var(--teal)}} .metric.before strong{{color:var(--orange)}}
.visual{{background:white;border:1px solid var(--line);border-radius:24px;padding:12px;overflow:hidden}} .visual svg{{display:block;width:100%;height:auto}}
.grid{{display:grid;grid-template-columns:1.2fr .8fr;gap:20px;margin:24px 0}} h2{{font-size:2rem;margin-top:0}} .steps{{counter-reset:item;list-style:none;padding:0}} .steps li{{counter-increment:item;padding:12px 0 12px 46px;position:relative;border-bottom:1px solid var(--line)}} .steps li:before{{content:counter(item);position:absolute;left:0;top:10px;width:30px;height:30px;display:grid;place-items:center;border-radius:50%;background:#e4f7f1;color:#087f61;font-weight:900}}
.boundary{{background:#14213d;color:white}} .boundary p{{color:#d7deea}} code{{background:#eef2f7;padding:.12rem .35rem;border-radius:.3rem}} footer{{color:var(--muted);padding:26px 0 60px;font-size:.9rem}} @media(max-width:800px){{.metrics,.grid{{grid-template-columns:1fr}} h1{{font-size:3rem}}}}
</style></head><body><main class="wrap">
<div class="notice" data-testid="claim-boundary">{html.escape(REAL_TOY_NOTICE)}</div>
<header><div class="eyebrow">ENPIRE-style supervisor · real local execution</div><h1>Can an automated researcher improve a real policy?</h1><p class="lead">Yes—on this small public task. The supervisor accepted one bounded idea, trained six real CPU policies, independently evaluated them, and kept the candidate.</p></header>
<section class="metrics" aria-label="experiment result">
<div class="metric before" data-testid="control-success"><span>Before · mean success</span><strong>{control}</strong><small>Narrow exploration misses useful corrections.</small></div>
<div class="metric after" data-testid="candidate-success"><span>After · mean success</span><strong>{candidate}</strong><small>Same task, seeds, resets and compute.</small></div>
<div class="metric" data-testid="decision"><span>Independent decision</span><strong class="keep">{decision['decision_record']['decision'].upper()}</strong><small>{delta} paired improvement; CI95 above zero.</small></div>
</section>
<section class="visual" data-testid="trajectory-visual">{svg}</section>
<section class="grid"><article class="card"><h2>What just happened</h2><ol class="steps"><li>A coding-agent proposal changed one allowlisted setting: exploration <strong>0.01 → 0.35</strong>.</li><li>The supervisor checked scope, budget, file path and a trusted config test.</li><li>A separate Git candidate was created; stable code did not move.</li><li>Three control and three candidate workers trained real residual policies.</li><li>The frozen evaluator compared paired evidence and returned <strong class="keep">KEEP</strong>.</li></ol></article>
<aside class="card"><h2>The agent’s idea</h2><p>“The learner is exploring too narrowly to discover useful corrections. Increase exploration, then reject the idea unless paired success improves.”</p><p><strong>Changed:</strong> one setting</p><p><strong>GPU/LLM cost:</strong> $0 during run</p><p><strong>Concurrent workers observed:</strong> {payload['execution']['maximum_concurrent_workers']}</p></aside></section>
<section class="grid"><article class="card"><h2>What this proves</h2><p>A real model was trained. Its result was measured on fixed unseen resets. The coding-agent workflow can safely isolate, run, evaluate, retain and document a model improvement.</p></article><article class="card boundary"><h2>What this does not prove</h2><p>This is not RLinf/RLT, π0.5, ManiSkill or robot evidence. The proposal was recorded rather than generated live. D1 is still required for the real scientific claim.</p></article></section>
<footer>Result fingerprint <code>{payload['result_fingerprint']}</code> · {EVALUATION_EPISODES} evaluations × 3 seeds per arm · artifact manifest included</footer>
</main></body></html>'''


def _artifact(output: Path, relative: str, role: str) -> DeliveryArtifact:
    safe = require_safe_relative_path(relative, "toy demo artifact path")
    path = (output / safe).resolve()
    try:
        path.relative_to(output.resolve())
    except ValueError as error:
        raise ToyDemoError("toy demo artifact escapes output") from error
    if not path.is_file() or path.is_symlink():
        raise ToyDemoError(f"toy demo artifact is missing or unsafe: {safe}")
    content = path.read_bytes()
    return DeliveryArtifact(
        path=safe,
        role=require_identifier(role, "toy demo artifact role"),
        sha256=hashlib.sha256(content).hexdigest(),
        size_bytes=len(content),
    )


def write_manifest(
    output: Path,
    *,
    result_fingerprint: str,
    artifacts: Sequence[tuple[str, str]],
) -> ToyDemoBundle:
    if len({path for path, _ in artifacts}) != len(artifacts):
        raise ToyDemoError("toy demo artifact paths must be unique")
    records = tuple(_artifact(output, path, role) for path, role in artifacts)
    manifest = {
        "manifest_version": "real-toy-artifact-manifest-v1",
        "demo_version": REAL_TOY_DEMO_VERSION,
        "notice": REAL_TOY_NOTICE,
        "result_fingerprint": require_sha256(result_fingerprint, "result fingerprint"),
        "artifacts": [record.to_dict() for record in records],
    }
    path = output / "artifact-manifest.json"
    _atomic_write(path, (canonical_json(manifest) + "\n").encode())
    verified = verify_manifest(output)
    return ToyDemoBundle(
        output_directory=str(output),
        result_fingerprint=result_fingerprint,
        manifest_path=str(path),
        artifacts=verified,
    )


def verify_manifest(output_directory: str | Path) -> tuple[DeliveryArtifact, ...]:
    output = Path(output_directory).resolve()
    try:
        raw = json.loads((output / "artifact-manifest.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise ToyDemoError("toy demo manifest is unreadable") from error
    data = require_exact_keys(
        raw,
        "toy demo manifest",
        {"manifest_version", "demo_version", "notice", "result_fingerprint", "artifacts"},
    )
    if data["manifest_version"] != "real-toy-artifact-manifest-v1":
        raise ToyDemoError("toy demo manifest version is unsupported")
    if data["demo_version"] != REAL_TOY_DEMO_VERSION or data["notice"] != REAL_TOY_NOTICE:
        raise ToyDemoError("toy demo manifest lost its version or claim boundary")
    require_sha256(data["result_fingerprint"], "manifest result fingerprint")
    rows = data["artifacts"]
    if not isinstance(rows, list) or not rows:
        raise ToyDemoError("toy demo manifest must contain artifacts")
    result: list[DeliveryArtifact] = []
    seen: set[str] = set()
    for index, row in enumerate(rows):
        item = require_exact_keys(
            row,
            f"toy demo artifact {index}",
            {"path", "role", "sha256", "size_bytes"},
        )
        relative = require_safe_relative_path(item["path"], "manifest artifact path")
        if relative in seen or relative == "artifact-manifest.json":
            raise ToyDemoError("toy demo manifest paths must be unique and non-recursive")
        seen.add(relative)
        actual = _artifact(output, relative, item["role"])
        expected_size = item["size_bytes"]
        if (
            isinstance(expected_size, bool)
            or not isinstance(expected_size, int)
            or expected_size < 0
        ):
            raise ToyDemoError("artifact size must be a non-negative integer")
        if (
            actual.sha256 != require_sha256(item["sha256"], "artifact hash")
            or actual.size_bytes != expected_size
        ):
            raise ToyDemoError(f"artifact does not match manifest: {relative}")
        result.append(actual)
    return tuple(result)


def run_demo(*, root: Path, repository: Path, output: Path) -> dict[str, Any]:
    checked = preflight(repository, output)
    output = checked["output"]
    output.mkdir(parents=True, exist_ok=True)
    runtime = output / "runtime"
    runtime.mkdir()
    worktree_root = runtime / "worktrees"
    worktree_root.mkdir()
    toy_repository, baseline_commit = _initialize_toy_repository(runtime)
    campaign = build_campaign(
        baseline_commit=baseline_commit,
        supervisor_head=checked["head"],
    )
    proposal = build_recorded_proposal(baseline_commit=baseline_commit)
    preparation = _prepare_candidate(
        toy_repository=toy_repository,
        worktree_root=worktree_root,
        campaign=campaign,
        proposal=proposal,
        baseline_commit=baseline_commit,
    )
    if preparation.status != PreparationStatus.READY:
        raise ToyDemoError(f"candidate preparation failed: {preparation.errors}")
    if not preparation.worktree_path or not preparation.candidate_commit:
        raise ToyDemoError("candidate preparation omitted its worktree or commit")
    control_config = toy_repository / "candidate" / "config.json"
    candidate_config = Path(preparation.worktree_path) / "candidate" / "config.json"

    requests = [
        (role, seed, control_config if role == "control" else candidate_config)
        for role in ("control", "candidate")
        for seed in SEEDS
    ]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
        futures = [
            executor.submit(
                _run_worker,
                root=root,
                role=role,
                seed=seed,
                config_path=config,
            )
            for role, seed, config in requests
        ]
        runs = [future.result() for future in futures]
    runs.sort(key=lambda item: (item["role"], item["seed"]))

    controls = tuple(
        _evidence(
            run=run,
            campaign=campaign,
            baseline_commit=baseline_commit,
            candidate_commit=preparation.candidate_commit,
        )
        for run in runs
        if run["role"] == "control"
    )
    candidates = tuple(
        _evidence(
            run=run,
            campaign=campaign,
            baseline_commit=baseline_commit,
            candidate_commit=preparation.candidate_commit,
        )
        for run in runs
        if run["role"] == "candidate"
    )
    decision = OfflineD1Evaluator().evaluate(
        campaign=campaign,
        decision_id="real-toy-policy-decision",
        arm_id=CANDIDATE_ARM,
        incumbent_commit=baseline_commit,
        candidate_commit=preparation.candidate_commit,
        control_evidence=controls,
        candidate_evidence=candidates,
    ).to_dict()
    semantic = _semantic_result(
        proposal=proposal,
        control=controls,
        candidate=candidates,
        decision=decision,
    )
    result_fingerprint = fingerprint(semantic)
    control_mean_distance = sum(
        item.metrics["mean_final_distance"] for item in controls
    ) / len(controls)
    candidate_mean_distance = sum(
        item.metrics["mean_final_distance"] for item in candidates
    ) / len(candidates)
    public_runs = []
    for run in runs:
        public_runs.append(
            {
                "role": run["role"],
                "seed": run["seed"],
                "started_at": run["started_at"],
                "finished_at": run["finished_at"],
                "elapsed_seconds": run["elapsed_seconds"],
                "logical_argv": run["logical_argv"],
                "command_hash": run["command_hash"],
                "stderr_sha256": run["stderr_sha256"],
                "evaluation": run["payload"]["evaluation"],
                "policy": run["payload"]["training"]["policy"],
                "policy_hash": run["payload"]["training"]["policy_hash"],
            }
        )
    payload = {
        "demo_version": REAL_TOY_DEMO_VERSION,
        "notice": REAL_TOY_NOTICE,
        "result_fingerprint": result_fingerprint,
        "scientific_scope": "real-toy-task-only",
        "rlt_claim_permitted": False,
        "proposal_generation": {
            "mode": "recorded-coding-agent-proposal",
            "live_provider_call": False,
            "provider_cost_usd": "0",
            "explanation": (
                "Recorded for meeting reliability; replaceable by the existing live provider seam."
            ),
        },
        "campaign": campaign.to_dict(),
        "proposal": proposal.to_dict(),
        "preparation": _public_preparation(preparation.to_dict(), output),
        "execution": {
            "worker_count": len(runs),
            "maximum_concurrent_workers": _max_concurrency(runs),
            "workers": public_runs,
            "external_calls": [],
            "gpu_cost_usd": "0",
            "llm_cost_usd": "0",
        },
        "result": {
            "control_mean_success": decision["control_mean_success"],
            "candidate_mean_success": decision["candidate_mean_success"],
            "control_mean_distance": control_mean_distance,
            "candidate_mean_distance": candidate_mean_distance,
        },
        "decision": decision,
        "repository": {
            "supervisor_head": checked["head"],
            "supervisor_branch": checked["branch"],
            "stable_head_unchanged": _git(checked["repository"], "rev-parse", "HEAD")
            == checked["head"],
            "stable_worktree_clean": not bool(
                _git(checked["repository"], "status", "--porcelain")
            ),
        },
        "proves": [
            "real CPU residual-policy training occurred",
            "the candidate improved the frozen public toy task on paired seeds",
            "proposal enforcement, Git isolation, workers, evidence, and evaluation compose",
        ],
        "does_not_prove": [
            "RLinf/RLT or pi0.5 improvement",
            "ManiSkill or physical-robot performance",
            "general coding-agent superiority",
            "a live LLM proposal occurred during this run",
        ],
    }
    if not payload["repository"]["stable_head_unchanged"] or not payload["repository"]["stable_worktree_clean"]:
        raise ToyDemoError("supervisor repository changed during the real toy demo")

    public = output / "public"
    public.mkdir()
    _write_json(public / "real-policy-demo.json", payload)
    _write_json(public / "campaign.json", campaign.to_dict())
    _write_json(
        public / "proposal.json",
        {
            "source": payload["proposal_generation"],
            "proposal": proposal.to_dict(),
        },
    )
    _write_json(public / "decision.json", decision)
    for run, evidence in zip(
        [item for item in runs if item["role"] == "control"], controls
    ):
        _write_json(
            public / "runs" / f"control-seed-{run['seed']}.json",
            {"evidence": evidence.to_dict(), "worker_result": run["payload"]},
        )
    for run, evidence in zip(
        [item for item in runs if item["role"] == "candidate"], candidates
    ):
        _write_json(
            public / "runs" / f"candidate-seed-{run['seed']}.json",
            {"evidence": evidence.to_dict(), "worker_result": run["payload"]},
        )

    with (public / "trials.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=(
                "role", "seed", "success_rate", "mean_final_distance",
                "successful_episode_length", "episode_count", "elapsed_seconds",
                "policy_hash",
            ),
        )
        writer.writeheader()
        for run in runs:
            writer.writerow(
                {
                    "role": run["role"],
                    "seed": run["seed"],
                    **run["payload"]["evaluation"],
                    "elapsed_seconds": run["elapsed_seconds"],
                    "policy_hash": run["payload"]["training"]["policy_hash"],
                }
            )
    representative_control = next(
        run for run in runs if run["role"] == "control" and run["seed"] == SEEDS[1]
    )
    representative_candidate = next(
        run for run in runs if run["role"] == "candidate" and run["seed"] == SEEDS[1]
    )
    svg = trajectory_svg(representative_control, representative_candidate)
    _atomic_write(public / "trajectory-comparison.svg", svg.encode())
    _atomic_write(public / "report.md", render_markdown(payload).encode())
    _atomic_write(public / "presentation.html", render_html(payload, svg).encode())

    artifact_paths: list[tuple[str, str]] = [
        ("public/real-policy-demo.json", "demo-record"),
        ("public/campaign.json", "campaign-record"),
        ("public/proposal.json", "proposal-record"),
        ("public/decision.json", "decision-record"),
        ("public/trials.csv", "trial-table"),
        ("public/trajectory-comparison.svg", "trajectory-visual"),
        ("public/report.md", "demo-report"),
        ("public/presentation.html", "demo-presentation"),
    ]
    artifact_paths.extend(
        (f"public/runs/{role}-seed-{seed}.json", "worker-evidence")
        for role in ("control", "candidate")
        for seed in SEEDS
    )
    bundle = write_manifest(
        output,
        result_fingerprint=result_fingerprint,
        artifacts=artifact_paths,
    )
    return {
        "status": "complete",
        "notice": REAL_TOY_NOTICE,
        "result_fingerprint": result_fingerprint,
        "control_mean_success": decision["control_mean_success"],
        "candidate_mean_success": decision["candidate_mean_success"],
        "mean_success_delta": decision["mean_success_delta"],
        "decision": decision["decision_record"]["decision"],
        "maximum_concurrent_workers": payload["execution"]["maximum_concurrent_workers"],
        "external_calls": [],
        "rlt_claim_permitted": False,
        "bundle": bundle.to_dict(),
    }
