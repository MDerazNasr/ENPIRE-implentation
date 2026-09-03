# E2 Bounded Objective Acceptance

Status: passed on 2026-09-03. This is a synthetic, no-GPU provenance test. It
does not evaluate robot-policy quality and cannot promote a candidate.

## Candidate and scope

The deterministic acceptance fixture adds one bounded term:

```python
return actor_loss + bc_weight * bc_loss + 0.1 * bc_loss
```

Its tracked source is
`examples/agent-supervisor/e2_actor_objective_candidate.py`; during acceptance
the standard Git manager applies that diff only to
`supervisor/objectives/actor_objective.py` in an isolated candidate worktree.
The exact source SHA-256 is
`8aef4f55ddb4c3ed7d3b0ab484752ed72dfb36f3981b5766d33468f7f49bba36`.
The proposal origin is explicitly
`deterministic-e2-acceptance-fixture`: no LLM or provider is credited.

The M6 validator accepted the source structure, AST allowlist, imports,
signature, loading, finite values, and gradients. Its dependency-free probe
changed values from `[2.75, 0.0]` to `[3.05, 0.05]` and the BC gradient from
`0.25` to `0.35`, while preserving all required gradient inputs.

## End-to-end route

`scripts/run_e2_objective_acceptance.py` created a clean minimal stable Git
repository and used the existing supervisor components rather than a parallel
mock protocol:

1. `ProposalEnforcer` accepted the bounded edit request.
2. `GitExperimentManager` applied the patch in a hypothesis worktree, ran the
   mandatory M6 check and two trusted fixture checks, and committed only the
   objective.
3. `D1PlanBuilder` bound the objective path, SHA-256, contract, logical RLinf
   command, execution argv, seed, candidate commit, configuration, and caps.
4. `D1ProcessWorker` ran the existing no-GPU fixture launcher and normalized
   its terminal evidence.
5. `probe_e2_objective_candidate.py` loaded the exact E0-hashed RLinf worker
   method, installed the candidate through the E1 live adapter, and performed
   real PyTorch 2.8 forward/backward on CPU.
6. `verify_e2_identity` reconciled the complete identity chain and failed the
   run unless every copy agreed.

The stable fixture HEAD remained unchanged. Candidate commit
`846e989228210a53d198963536c63221d8184587` and its worktree remain under
`/private/tmp/enpire-e2-acceptance-20260903` for inspection. These hashes name
the isolated acceptance repository, not a scientific project candidate.

## Identity proof

All ten required checks passed for the same objective SHA-256:

- plan objective hash and contract;
- logical command hash token;
- execution argv hash argument;
- manifest objective hash and contract;
- manifest validation source hash, behavior-change flag, and empty errors;
- runtime-probe source hash;
- runtime installation-marker source hash and contract; and
- normalized `actor-objective` evidence artifact.

The canonical acceptance record is
`results/agent-supervisor/e2/acceptance.json`. Its fingerprint is
`7c62a031bf31a113393aa73d1be43624503291da49cfbee2f2bf6748c441561b`;
the runtime attachment record SHA-256 is
`549f35680acf053c563405a46cdbe8877fcb8a0c90f4fd0e1b9c8eff2aaf776f`.

Independent unit tests mutate the plan, command, manifest, runtime record, and
evidence one at a time; each mismatch fails closed.

## Live effect and claim boundary

For a `[3,2,4]` float32 policy tensor, online Q/BC weights `0.45/2.5`, an
intervention mask, and accumulation factor four:

- native loss: `1.0456048250198364`;
- candidate loss: `1.0874290466308594`;
- finite value delta: `0.04182422161102295`; and
- maximum policy-gradient absolute delta: `0.0031249970197677612`.

This proves that the non-no-op code reached the live PyTorch combination and
changed its gradient. It does not prove the change is beneficial. The fixture
success value and W&B URL inside the inherited fixture manifest are synthetic
test fields; no W&B request occurred, and neither may be used as research
evidence. Training steps, GPU usage, provider calls, LLM cost, and GPU cost
were all zero. No evaluator or incumbent store was invoked.

## Preserved rejection

The same run submitted a negative-control candidate containing forbidden
`import os`. Candidate preparation failed with both `forbidden_import` and
`objective_import`; its complete failed preparation record, branch/worktree
identity, timestamps, and errors are retained inside the E2 acceptance record.
It was not executed or silently replaced.

## E2 conclusion

The bounded proposal-to-live-objective identity chain is complete, tamper-
checked, non-promotable, and independent of GPU availability. E2 passes. The
next workstream is F0: select one matched scientific runtime before qualifying
the full worker path.
