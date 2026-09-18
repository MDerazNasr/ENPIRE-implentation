# G0 Production Acceptance Runbook

Status: **single-operator AWS controls verified; private custody transfer,
fresh E1 preflight, and paid execution remain unauthorized**

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

The evaluator and audit accounts now contain the reviewed storage, application
roles, independent anchor failure domain, CloudTrail, and 30-day COMPLIANCE
retention controls. The dedicated receipt-verifier role has independently
verified their technical state. They remain under one human owner, so this is
the accepted single-operator protected boundary rather than
`production-independent` custody. The recovered private final-reset artifact
and evaluator bundle remain local and have not been uploaded.

The previously qualified Lambda host was an engineering qualification target,
is no longer reachable, and must not be treated as the scientific runtime. A
future preliminary E1 host requires a fresh binding to the final scientific
source commit, image, assets, durable evidence destination, timeout, UTC
window, and explicit retry-inclusive cost ceiling in a non-authorizing
preflight, followed by a separate exact paid/GPU approval.

The GPU-free AWS provisioning design is documented in
[`../../infra/aws-g0/README.md`](../../infra/aws-g0/README.md). Its two
CloudFormation templates created the currently verified audit and evaluator
stacks only after their recorded exact approvals. The templates and offline
checker still grant no private-upload, evaluator, GPU, evaluation, or promotion
authority by themselves.

## Focused completion order: protected evaluator, then baseline

The active scope is limited to completing meeting experiments 3 and 1, in that
dependency order:

1. Name an independent evaluator/custodian human and a different independent
   verifier human. Do not share credentials or reuse the candidate operator.
2. Create and verify their least-privilege Identity Center principals under a
   separate exact approval. The current administrator remains bootstrap-only.
3. Review the corrected evaluator template, including retained-version listing
   for `ReceiptVerifierRole`, then create a non-executed change set under a
   separate approval.
4. Separately approve and execute the evaluator stack, independently verify all
   three locked buckets, roles, CloudTrail, ledger/anchor separation, and remove
   temporary administrator access before claiming production custody.
5. Under a separate private-transfer approval, place the final reset artifact
   and evaluator bundle through the custody principal without exposing ordered
   IDs, paths, credentials, or model weights.
6. Produce and validate the canonical custody and production-deployment
   receipts. Only then resolve runtime/assets, cost/retention, and human
   protocol acceptance to reach `ready_for_e1_preflight_only`.
7. Create a separately approved E1 preflight for one uninterrupted seed-2026
   Stage-1 run to 2,000 steps, retaining checkpoints 250/500/1000/2000.
8. After a distinct paid/GPU authorization, run E1, evaluate only on the frozen
   development set, apply `g0-e1-stage1-horizon-v1`, and independently hash the
   selected non-degenerate actor. Final resets are not used for selection.

No item inherits authorization from the preceding item. Failed, interrupted,
reverted, and inconclusive evidence remains preserved.

## Interim single-operator protected mode

On 2026-09-15 the researcher selected an interim weaker boundary: retain the
separate evaluator and audit AWS accounts and least-privilege roles, but allow
one human owner to administer both. This is sufficient to test prevention of
automatic agent/worker interference and to run a preregistered preliminary E1
development baseline after separate infrastructure and paid-run approvals.

It does not satisfy `production-independent` custody. Do not create canonical
production custody/deployment receipts, expose or use hidden final resets,
enter E2, claim independent human evaluation, or promote a policy under this
mode. Administrator override risk must remain explicit in every report. A
later independent-human handoff can strengthen the boundary, but cannot
retroactively upgrade evidence collected under single-operator control.

As of 2026-09-17, the interim technical-identity step is complete. The existing
administrator holds separate coordinator, custodian, and evaluator-operator
permission sets, and the temporary verifier has evaluator-account verifier
access. Each permission set is limited to assuming its exact future role, and
none grants direct S3, CloudFormation, GPU, or evaluator authority. This does
not complete production steps 1 or 2 above because the humans remain under one
owner. The next separately authorized action may only be creation of a
non-executed evaluator CloudFormation change set for review.

That review-only step completed on 2026-09-17. Change set
`g0-evaluator-single-operator-review-v1` proposes exactly the expected eleven
resource additions and remains `CREATE_COMPLETE/AVAILABLE`; its placeholder
stack has zero resources. No Object Lock, bucket, application role, or trail
exists in the evaluator account. The next action is execution only after a new
exact approval acknowledging the three irreversible 30-day COMPLIANCE locks.

Execution was separately approved and completed on 2026-09-17. The stack and
all eleven resources reached `CREATE_COMPLETE`; administrator read-back passed
for the three retention-locked empty buckets, four least-authority roles, three
TLS-only policies, and active cross-account CloudTrail. This is not yet a
completed protected-evaluator acceptance: the dedicated receipt-verifier role
still needs a clean verifier-user login and independent read-only validation.
No private upload or evaluator/scientific execution is authorized.

The dedicated technical verifier check passed on 2026-09-18. The exact
`ENPIREG0VerifierAccess` principal assumed `enpire-g0-receipt-verifier` and
independently confirmed all three empty version inventories, enabled
versioning, non-public status, and 30-day COMPLIANCE retention. The technical
protected-infrastructure boundary is therefore complete under the accepted
single-operator mode. Independent human control and private final-input custody
remain incomplete, and no evidence collected under this mode may be upgraded
retroactively to independently controlled scientific evidence.
