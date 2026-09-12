# G0 Production Acceptance Runbook

Status: **ready-transition validation implemented; production receipts remain
unprovisioned and no execution is authorized**

Obsidian task: `MI5T8`

This runbook defines the only supported path from the completed local G0
rehearsals to a frozen E1 preflight. It does not provision cloud resources and
does not authorize a GPU, provider call, private-model transfer, scientific
evaluation, campaign activation, selection, or promotion.

## Required separation

Use at least two independently controlled failure domains:

1. An evaluator principal that candidate, proposer, coordinator, and training
   worker principals cannot assume. This principal owns the final-reset object,
   read-only evaluator bundle, and append-only evaluator ledger.
2. A distinct anchor principal or service that the evaluator writer cannot
   rewrite. It stores or signs the ledger head.

Large training artifacts and checkpoints belong in a private, versioned,
off-host object store. They are not final evaluator inputs and must not grant
the training worker access to the final reset set or evaluator source. Enable
encryption, versioning, access logging, and retention of at least 30 days after
terminal reconciliation. Disable automatic deletion. Never put private model
weights in Git.

A separate bucket under the same unrestricted human/automation credential is
not independent custody. Receipt assertions must describe controls that
actually exist and must be verified by a principal distinct from the candidate
and worker operators.

## Canonical receipt order

Create records only after the corresponding external controls exist. Every
record is a canonical `{"payload": ..., "sha256": ...}` envelope and grants no
execution authority.

1. `results/agent-supervisor/g0/final-reset-custody.json`
   - Validate with `validate_production_custody_record`.
   - Publicly exposes only the final artifact fingerprint, count, storage
     identity hash, principals, timestamp, and control assertions.
   - Never includes the ordered IDs, private object URI, or credentials.
2. `results/agent-supervisor/g0/production-evaluator.json`
   - Validate with `validate_production_deployment_record`.
   - Binds the evaluator bundle, environment, custody receipt, ledger, and
     independently controlled anchor.
3. `results/agent-supervisor/g0/runtime-identities.json`
   - Validate with `validate_runtime_identity_record`.
   - Binds a fresh scientific source commit, fresh host/image/route receipts,
     evaluator environment, durable artifact-store identity, and all frozen
     public assets.
   - Keeps the E2 actor identity `pending-e1-output`.
4. `results/agent-supervisor/g0/cost-envelope.json`
   - Validate with `validate_cost_retention_record`.
   - Binds fresh compute/storage pricing evidence, an explicit egress ceiling,
     retry-inclusive E1/E2 arithmetic, the durable store, and retention rules.
5. `results/agent-supervisor/g0/protocol-acceptance.json`
   - Validate with `validate_protocol_acceptance_record`.
   - Cross-binds the preceding four receipts and records the exact human
     acceptance of seeds, E1 checkpoint selection, E2 allocation, final-reset
     use, and the independent decision rule.

The exact schemas are enforced in `supervisor/evaluator_deployment.py` and
`supervisor/g0_acceptance.py`. Do not copy assertions from a template and then
claim they were verified.

## Readiness check

Run locally without provider access:

```bash
python3 scripts/run_g0_readiness_gate.py
```

The gate fails closed if a receipt is missing, malformed, over-authorizing, or
cross-bound to the wrong predecessor. With all receipts valid, its status is
`ready_for_e1_preflight_only`. Every authority flag remains false.

That status permits drafting and reviewing a separate immutable E1 preflight.
It does not permit launching E1. A paid E1 run still requires a fresh explicit
approval naming the instance, IP, source commit and bundle, image, assets,
artifact destination, timeout, total cost ceiling, UTC window, and any private
model egress.

## Current blocker

No production evaluator principal, independently controlled anchor, or durable
artifact-store identity has been supplied. The previously qualified Lambda
host was an engineering qualification target and must not be treated as the
evaluator or durable store. A future scientific host requires a fresh binding
to the final scientific source commit and a new non-authorizing preflight.
