# Final Research Handoff: RLT Coding-Agent Supervisor

Date: 2026-08-04

Implementation branch: `feature/d2-agent-supervisor`

Reconciliation note (2026-09-02): D1 subsequently advanced to `eed314f` and
now has a Stage-7 evidence directory plus one corrected Control/Candidate seed.
The next work is to build a canonical strict pack, complete matched approved
seeds, and attach the live objective/worker paths. References below to the
earlier degenerate D1 state are historical.

## Deliverable

The repository now contains an audited ENPIRE-inspired outer loop for improving
RLT policies. A short-lived coding agent can propose either bounded RLT
configuration changes or a change to one project-owned actor-objective
function. Harness code owns validation, Git isolation, execution, evidence,
evaluation, budgets, scheduling, and promotion.

This is intentionally narrower than ENPIRE's long-term vision of implementing
arbitrary research ideas. It provides a reliable RLT-specific baseline from
which physical-AI-specific research can proceed.

## Implemented system

| Layer | Implemented result |
|---|---|
| Campaign/evidence | canonical contracts, approval, decimal budgets, separate campaign/trial state, hash-chained ledger |
| Proposal | provider-neutral interface, Claude-first tool-free session, bounded context, structured output, one repair |
| Enforcement | config/code allowlists, AST/diff/path policy, trusted tests, isolated branch/worktree, stable-HEAD proof |
| Execution | fake workers plus guarded real subprocess adapter; dry-run default and explicit paid authorization |
| Code mode | exact project-owned objective ABI with forward/gradient behavioral validation and provenance |
| Evaluation | frozen D1 paired rule, fail-closed evidence normalization, evaluator-only per-arm promotion |
| Distribution | independent workers, fixed RPC, capability/budget scheduling, leases, restart/loss recovery, stale rejection |
| Study | fixed rule vs Claude config vs Claude code, three discovery slots each, isolated lineages, paired confirmation |
| Delivery | unified offline demo, optional D1 replay, static presentation, architecture view, artifact manifest |

## Demonstrated result

The M9 fixture demonstrates the entire control plane from proposal through
study/reporting. It includes an invalid proposal/repair, isolated candidate,
central decision, two-worker overlap, worker loss/retry, stale-result
rejection, nine three-arm discovery records, three confirmation records, two
invalid study outcomes, and one failed candidate.

These are deterministic fixtures. The correct conclusion is that the
orchestration and authority boundaries behave as specified. There is no
evidence yet that RLT improved the VLA or that any proposer arm is better.

## Reproduction

```bash
python3 -m pytest -q
python3 scripts/run_m9_ludvig_demo.py \
  --output /tmp/enpire-m9-ludvig-demo
python3 scripts/verify_m9_bundle.py \
  /tmp/enpire-m9-ludvig-demo
```

See `ludvig-demo-runbook.md` for the presentation sequence and fallback.

## D1 compatibility seam

The separate D1 workstream must supply:

- a clean reviewed Stage-7 pack and known-good commit;
- non-degenerate Reference A and paired Control B/Candidate evidence;
- exact baseline/RLinf/reset/evaluator/config/command identities;
- stable result artifact and W&B semantics;
- real runtime/cost/resource behavior; and
- the exact PyTorch actor-loss attachment point and tensor/autograd contract.

The existing gate replays the D1 decision through both legacy and supervisor
evaluators. M9 can show that replay read-only. Live work must continue through
M5 authorization and M7 exact worker contracts; incompatibilities belong in a
versioned harness adapter, not silent RLinf edits or weaker validation.

## Recommended next experiment

1. Reconcile D1 `eed314f` with this supervisor and generate the strict Stage-7
   pack; do not start the arm comparison from the unmatched one-seed result.
2. Perform one configuration and one objective attachment acceptance run.
3. Activate the exact M8 preregistration before receiving study results.
4. Run three discovery candidate experiments per arm with matched worker caps.
5. Select mechanically within each arm and independently rerun each selected
   commit on the paired confirmation seeds.
6. Report per-seed outcome, frozen decision/CI, failures, wall/GPU/LLM cost,
   tokens, invalid proposals, and interventions.
7. Only then decide whether to study new physical-AI proposal strategies,
   visual diagnosis, VLA fine-tuning from residual interventions, or alternative
   coding-agent providers.

## Explicit limitations

- No real Claude call, RLinf training, GPU/SSH worker, W&B API, robot, or paid
  service was used by the final supervisor branch.
- E2 proved the non-fixture PyTorch/RLinf attachment, exact default CPU
  equivalence, and bounded candidate identity through plan, command, manifest,
  runtime marker, and evidence. CUDA/full-worker qualification remains open.
- Remote helper deployment, detached-process recovery, active remote
  cancellation, artifact transfer, and real utilization collection require the
  live infrastructure handoff.
- AST validation is defense in depth; untrusted Python still requires the
  bounded worker/process isolation already specified.
- Three paired seeds support the approved engineering rule, not broad
  significance or universal agent rankings.
- The system is RLT-specific and does not claim automatic implementation of an
  arbitrary paper.

## Final conclusion

The coding-agent supervisor is ready as a reproducible control-plane prototype
and meeting demo. Its central research idea is precise: use a constrained agent
to supervise complete RL improvement experiments while deterministic evidence,
not agent confidence, controls promotion. The next legitimate claim depends on
real D1-backed execution under the frozen study—not further synthetic polish.
