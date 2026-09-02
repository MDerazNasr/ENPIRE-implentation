# C1 Real-Provider Acceptance

Status: **prepared but blocked before the provider call on 2026-09-02**.

The user authorized one paid Claude proposal slot capped at USD `0.5`. The
curated D1 input is complete and reproducible, but the selected direct
Anthropic credential is not present in the execution environment. The harness
therefore made no prompt submission and incurred no provider cost.

## Prepared input

The acceptance-only campaign is bound to C0 commit
`d151b404aaeff3507047835eff14f6fa55cb9af0` and pinned RLinf commit
`c90951a0c799a750cb5294ed10587c61cc2af8bf`. It permits one configuration
artifact and only these bounded keys:

- `warmup_bc_weight`, from `3.5` through `8.5`; and
- `online_bc_weight`, from `1` through `3.5`.

The 6,912-byte context includes only the corrected one-seed result and the
eleven current readiness blockers. It tells the provider that `17/256` versus
`18/256` is inconclusive, runtime-mismatched engineering evidence; it may not
make a causal or performance claim. It also fixes the arm, commit, evidence
IDs, target path, parameter names, and allowed test IDs.

| Artifact | Identity |
|---|---|
| Campaign | `results/provider-acceptance/c1/campaign.json` |
| Campaign hash | `dd68bb797a165011d87f3dc1525c026f0305aa87d9319991f38f338844ca8352` |
| Context | `results/provider-acceptance/c1/context.json` |
| Context hash | `9088f431d2274c5a350d703798aed32a279824a2227ac753b5af11587fb23bd1` |
| Credential-safe preflight | `results/provider-acceptance/c1/preflight.json` |

The campaign's worker budget fields describe a possible proposal and do not
approve a GPU run. `gpu_authorized` is explicitly `false`; C1 cannot launch
training or evaluation.

## Execution boundary

The runner defaults to preparation only. A real call requires both execution
flags:

```bash
python3 scripts/run_c1_provider_acceptance.py \
  --execute \
  --acknowledge-paid-provider-call
```

It then requires `ANTHROPIC_API_KEY`, exact regeneration of both tracked input
artifacts, and a clean repository. Missing credentials, artifact drift, dirty
Git state, or a missing acknowledgement blocks before constructing the
provider session.

During an authorized call, the runner uses the frozen C0 adapter and records
Git HEAD, index hash, and complete status hash immediately before and after
the provider session. Only after that comparison does it write `session.json`.
The report retains every structured proposal payload, including an invalid
initial payload, alongside the normal attempt audits. Malformed envelopes are
represented by their fail-closed audit because raw CLI stdout/stderr is never
committed.

## Current preflight result

The credential-safe check returned:

- direct Anthropic API credential: absent;
- provider call made: `false`;
- GPU authorized/used: `false`;
- credential value recorded: `false`; and
- status: `blocked`.

No login flow was started because authentication is a separate external
account action. Once the credential is configured in the launching shell, the
already authorized USD `0.5` slot can proceed through the command above.

