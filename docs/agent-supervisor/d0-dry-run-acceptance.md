# D0 Configuration Dry-Run Acceptance

Status: **passed on 2026-09-02 without an external process**.

C1 produced no accepted Claude proposal, so D0 uses a deterministic fixture
proposal through the same proposal, enforcement, Git, and D1-plan contracts.
This proves integration mechanics only. It is not Claude output, scientific
evidence, or authorization to execute RLinf.

## Accepted fixture

The fixture changes only
`scientific_values.online_bc_weight` from the frozen Control value `2.5` to
`2.25`, within the campaign range `1` through `3.5`. It targets only
`candidates/config_override.json`, requests the registered `config-contract`
and `dry-run` checks, and makes no performance claim.

The proposal passed `ProposalAttemptController` through
`FakeProposalProvider` with USD `0`, then passed independent M3 scope, budget,
and materialization enforcement.

| Identity | Value |
|---|---|
| Stable base | `486e293bf79935350d1bc1bdc7dba2897122f58c` |
| Campaign hash | `56eb5b8a3ea2b7652fe05c6b24c8abd22b9e4abf9506613ae2845fea8af5d078` |
| Context hash | `7035c346dd3a56722b399ef6eb6b52bf178d58bacf582fd5ba7d656ebd2b2fcf` |
| Proposal | `d0-fixture-config-01` |
| Hypothesis branch | `hypothesis/d0-config-dry-acceptance/d0-fixture-config-01` |
| Candidate commit | `a2222498c0f1ab0543f27c5d96b90816314b8ac0` |
| Derived config hash | `a4e41f19c0c140aebe1b7763621334775e99640378cbb36ce17ac0a22f5d5fdd` |
| Logical command hash | `1786ac26e4b3215b15f7892db6be276e55237c6e34538a30227c7479c3fe92a9` |
| Plan hash | `872e423c80f2679766df8af7315491a76f71615b8db51170335dd63d01a14004` |

The complete machine record is
[`../../results/provider-acceptance/d0/dry-run.json`](../../results/provider-acceptance/d0/dry-run.json).

## Harness-owned checks

Both checks run in the isolated hypothesis worktree with a reduced environment
and hashed stdout/stderr:

1. `config-contract` parses and validates the materialized D1 configuration.
2. `dry-run` substitutes inert `/opt/enpire-d0/...` placeholders and resolves
   the complete logical RLinf command without launching it.

Both returned exit `0`. The dedicated checker always records
`process_launched=false`.

## Worker-owned plan

`D1PlanBuilder` generated the seed-2026 resolved configuration under
`/private/tmp/enpire-d0-results/.plans/`, outside the candidate worktree. The
logical command binds the pinned RLinf entrypoint, exact config name, fixed
evaluation settings, `actor.seed=2026`, Control warm-up BC weight `7`, and
fixture online BC weight `2.25`.

The execution argument vector contains neither `--execute` nor
`--acknowledge-paid-run`. `D1ExperimentBackend` received a dry-run
authorization and a transport that raises if called. Its result is `planned`,
with `process=null` and no evidence invented.

## Isolation proof

- Stable HEAD, index hash, and empty status hash match before and after.
- Every pre-existing branch ref is unchanged.
- Exactly one expected hypothesis branch was added.
- The candidate worktree is clean at its recorded commit.
- Derived worker configuration is outside the candidate worktree.
- Provider call, external process, paid flag, and GPU use are all false.

The first sandboxed run stopped before branch creation because Git metadata
writes were denied. The same dry-only command was rerun with narrowly scoped
permission to create the isolated worktree; no execution authority changed.

## Reproduction boundary

The retained hypothesis worktree and worker plan are audit artifacts in
`/private/tmp`; they are not portable Git evidence. The tracked JSON record
contains their exact paths and hashes. Re-running the command intentionally
fails if its branch, worktree, result, or plan paths already exist, preventing
silent overwrite.

Next, D1 may exercise the existing local no-GPU subprocess fixture. It must
continue to label all resulting evidence synthetic and prove failures cannot
reach evaluation or promotion.

