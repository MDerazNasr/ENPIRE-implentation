# M5 D1 Backend Contract

Status: implementation complete; live scientific acceptance blocked by the D1
integration gate.

M5 replaces the M4 fake-worker boundary with a guarded adapter around the
project-owned `agent.d1_launcher`. It does not change the inner RL algorithm.
The supervisor still acts only between complete training/evaluation runs.

## Execution modes

| Mode | Process launched | Paid acknowledgement | Evidence label | Intended use |
| --- | --- | --- | --- | --- |
| `dry_run` | no | forbidden | non-synthetic plan only | inspect exact config, command, hashes, and caps |
| `fixture` | yes, local no-GPU fixture | forbidden | synthetic | test and demo the whole integration path |
| `paid` | yes, `agent.d1_launcher --execute` | required | non-synthetic | authorized D1/RLinf run after the gate is ready |

There is no implicit transition from dry-run or fixture mode into paid mode.
Paid authorization binds the exact campaign hash, approval envelope, D1 replay
gate, and acknowledgement timestamp.

## Config-to-command boundary

The candidate remains configuration-only. For each seed, the plan builder:

1. verifies the isolated candidate worktree is clean and at the exact candidate
   commit;
2. reads the one campaign-approved config path;
3. synchronizes allowlisted scientific values to the actual RLinf Hydra keys;
4. writes the seed into `actor.seed`;
5. resolves required environment placeholders for dry-run/paid plans;
6. requires the config trajectory count to equal the campaign contract;
7. writes a worker-owned, seed-specific config outside the candidate worktree;
8. hashes the exact config and logical RLinf command into an immutable
   `RunContract`.

The source proposal is never rewritten by this synchronization step. A change
to `scientific_values.online_bc_weight`, for example, changes
`algorithm.actor_weight_schedule.online_bc_weight` in the command actually
executed.

## Process and budget behavior

The local transport launches a new process group with the immutable per-trial
wall-time cap. On timeout it sends `SIGTERM`, waits briefly, then sends
`SIGKILL`. A timeout, missing terminal artifact, invalid manifest, or cost
overrun yields no invented evidence and cannot promote a candidate.

The D1 launcher remains responsible for its own run-cost cap. The M5 normalizer
also independently rejects a manifest whose terminal cost exceeds the
`RunContract` GPU cap. Distributed leases, remote cancellation, and concurrent
SSH workers remain M7.

## Evidence normalization

M5 accepts only a terminal `manifest.json` plus `run.log`. It verifies:

- project commit, expected and actual RLinf commits;
- exact derived-config and logical-command hashes;
- terminal status/exit-code consistency and valid timestamps;
- seed, fixed-reset declaration, and campaign trajectory count;
- per-run cost cap;
- one consistent W&B run URL for paid execution.

The primary metric is parsed from D1 evaluation success output. Episode length
is accepted only from an explicitly named successful-episode-length metric;
generic episode length is not silently reinterpreted. Local paths are replaced
by logical artifact URIs plus content hashes before evidence enters the
supervisor ledger.

## Coordinator seam

`RunContractFactory` is the only new seam in the M4 coordinator. With no
factory, all M4 behavior remains unchanged. With
`D1CoordinatorContractFactory`, each seed receives a seed-specific D1 plan
registered with `D1ProcessWorker`. The coordinator then uses the same worker,
ledger, evaluator, incumbent, and reporting contracts as before.

This keeps proposal/Git/evaluation policy independent of the process provider
and prevents live code from bypassing the already-tested M1–M4 gates.

## Current acceptance boundary

The subprocess fixture proves integration mechanics only. It is deliberately
labeled synthetic and uses a fixture W&B URL; it neither contacts W&B nor runs
RLinf/GPU work.

Paid mode cannot be authorized until the live D1 repository is clean and has a
reviewed Stage-7 pack containing non-degenerate Reference A, Control B, and
Candidate C evidence that replays equivalently through the frozen evaluator.
