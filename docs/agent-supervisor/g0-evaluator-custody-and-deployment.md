# G0 Evaluator Custody and Deployment Contract

Status: **local isolation rehearsal passed; production custody and deployment
remain unprovisioned and unauthorized**

Obsidian task: `MI5T8`

This contract separates evidence about local packaging from acceptance of an
independent scientific evaluator. It does not authorize evaluation, a campaign,
GPU use, paid execution, provider access, model egress, or promotion.

## Trust boundary

The proposer, candidate worktree, training worker, coordinator, and report
builder must be unable to read the final ordered reset IDs or modify evaluator
source, final inputs, official results, or the trusted ledger anchor. The
evaluator operator alone may consume final inputs. The independent reviewer
verifies public hashes and custody/deployment receipts without receiving the
ordered IDs.

Production acceptance requires all of the following:

- an evaluator OS principal distinct from every candidate/training principal;
- evaluator-only or immutable storage for the final reset artifact and source;
- no proposer, candidate, or training-worker access to final inputs;
- a hash-manifested evaluator bundle and frozen environment identity;
- append-only ledger storage separate from the candidate worktrees;
- a trusted head anchor under a different principal or failure domain from the
  ledger writer; and
- independent verification recorded before any scientific evaluation input is
  admitted.

POSIX mode bits owned by the same user are insufficient because that owner can
restore write permission. A same-user local check must therefore remain a
rehearsal even when every path and hash check passes.

## Implemented contracts

`supervisor/evaluator_deployment.py` provides three fail-closed boundaries:

1. A local rehearsal auditor that verifies the final artifact hash/count/role,
   owner-read-only modes, an entirely read-only evaluator bundle, external and
   separated paths, and non-authorizing claims. Its public receipt contains
   only hashes, counts, modes, and platform identity—never ordered reset IDs or
   their filesystem path.
2. A strict production custody-record schema requiring independent principal
   and failure-domain assertions, evaluator-only or immutable storage, an
   independent verifier, and false candidate/proposer/worker access.
3. A strict production deployment-record schema binding the evaluator bundle,
   environment, custody receipt, separated ledger and anchor identities, and
   false candidate modification/final-input access.

Both production records remain non-authorizing. They are prerequisites for the
separate human protocol-acceptance and activation gates.

The remaining runtime, cost, and human-acceptance records and their cross-hash
ordering are defined in
[`g0-production-acceptance-runbook.md`](g0-production-acceptance-runbook.md).

## Local rehearsal result

The private final artifact directory was tightened from mode `0755` to `0500`,
and its file from `0644` to `0400`. No artifact was copied, printed, or added to
the repository. The local rehearsal then:

- verified final artifact fingerprint
  `27165db099dfaddc66a6eced98156110acb2e877289eb1c503ae53a446d2fa97`;
- built and reverified a read-only external evaluator bundle;
- created distinct empty ledger and anchor roots;
- emitted no ordered final IDs or private path; and
- explicitly recorded that the same OS principal, mutable mount, and shared
  failure domain prevent production acceptance.

The current public non-authorizing receipt is
[`../../results/agent-supervisor/g0/evaluator-isolation-rehearsal-v2.json`](../../results/agent-supervisor/g0/evaluator-isolation-rehearsal-v2.json).
The earlier v1 receipt remains preserved as historical evidence.

The host later removed the temporary local final-reset directory. On
2026-09-18 the artifact was deterministically regenerated from the same clean
pinned RLinf and ManiSkill commits with NumPy 1.26.4. Its artifact fingerprint,
capture identity, count, and byte hash match the frozen records; ordered IDs
were not emitted. A fresh read-only evaluator bundle and local isolation
rehearsal also passed. One create-only rehearsal invocation failed because its
ledger directory had been pre-created and is preserved in the recovery record.
The recovery remains local only: no private object was uploaded, and this does
not establish production-independent custody under single-operator mode. See
[`../../results/agent-supervisor/g0/g0-private-input-recovery-v1.json`](../../results/agent-supervisor/g0/g0-private-input-recovery-v1.json).

## Reproducing the local rehearsal

Use a fresh external destination. The command is create-only and will refuse
existing output paths:

```bash
python3 scripts/run_g0_evaluator_isolation_rehearsal.py \
  --private-final /path/known-only-to-evaluator/final.json \
  --bundle-output /external/rehearsal/bundle \
  --ledger-root /external/rehearsal/ledger \
  --anchor-root /separate/rehearsal/anchor \
  --output /tmp/g0-evaluator-isolation-rehearsal.json
```

Do not place the private final artifact, its ordered IDs, or a production
receipt containing private paths in the repository. Do not run
`run_evaluator.py` during this rehearsal.

## Production handoff

The evaluator operator must provision the independent principal/storage and
return only two canonical public envelopes:

- `results/agent-supervisor/g0/final-reset-custody.json`, conforming to
  `validate_production_custody_record`; and
- `results/agent-supervisor/g0/production-evaluator.json`, conforming to
  `validate_production_deployment_record` and binding the accepted custody
  receipt hash.

Receipt assertions must be derived from actual controls, not copied from a
template. Invalid, missing, extra, reordered-by-substitution, hash-mismatched,
same-principal, shared-anchor, or authority-granting records fail closed. Even
valid records only remove two readiness blockers; they cannot activate G0.

## Remaining decisions

Before provisioning, a human must select:

1. the evaluator principal and operator;
2. the immutable/evaluator-only final-input storage identity;
3. the evaluator runtime or image identity;
4. the append-only ledger destination;
5. the independently controlled trusted-anchor destination; and
6. the independent verifier who will sign off on the public receipts.

Until these values exist and are independently verified, the final artifact
stays in temporary local hardened storage and G0 remains blocked.
