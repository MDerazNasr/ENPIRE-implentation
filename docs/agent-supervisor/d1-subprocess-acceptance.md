# D1 Bounded Subprocess Acceptance

Status: **passed on 2026-09-02 with local synthetic subprocesses only**.

D1 exercised the integrated proposal, Git, run-plan, worker, subprocess,
artifact-normalization, coordinator, evaluator, ledger, and incumbent-store
path. It used no GPU, provider, network, SSH, W&B service, or paid resource.
The fixture emits a syntactically valid tracker URL for parser coverage but
does not contact W&B.

This is an engineering acceptance result. It is not RLinf execution, Claude
output, or scientific evidence that a candidate improves RLT.

## Frozen implementation

The passing run used integration commit
`a3ece0bff928401ddd489ec3b56ec47550655d4d`. The harness consists of:

- `scripts/run_d1_subprocess_acceptance.py`, which creates a fresh isolated
  Git repository and candidate worktree for each scenario and drives the real
  coordinator;
- `scripts/d1_adversarial_fixture_launcher.py`, which wraps the normal M5
  fixture and injects one named terminal fault;
- `D1ProcessWorker.fetch_result`, a read-only terminal-result accessor used to
  record the backend classification without weakening evidence access; and
- `tests/test_d1_subprocess_acceptance.py`, which proves fault selection and
  mutation remain explicit and bounded.

The canonical machine record is
[`../../results/provider-acceptance/d1/subprocess.json`](../../results/provider-acceptance/d1/subprocess.json),
SHA-256
`5585e23ebfc83ecc145efbabc01f0262bb3abc4f726119fb33a4cbcf78023d0c`,
41,917 bytes.

## Acceptance matrix

| Scenario | Backend | Coordinator | Evaluation | Incumbent |
|---|---|---|---|---|
| happy | `complete` | `decided` | `inconclusive` | unchanged |
| timeout | `timed_out` | `worker_failed` | not reached | unchanged |
| missing artifact | `failed` | `worker_failed` | not reached | unchanged |
| config-hash mismatch | `invalid_evidence` | `worker_failed` | not reached | unchanged |
| cost overrun | `invalid_evidence` | `worker_failed` | not reached | unchanged |
| normalized process failure | `failed` | `decided` / `failed` | `failed` | unchanged |

The happy path produced a real process outcome, manifest, log, normalized
evidence, ledger transitions, and deterministic evaluation. One seed is
intentionally insufficient for the frozen D1 decision rule, so its correct
result is `INCONCLUSIVE`, not a synthetic promotion.

The timeout subprocess exceeded its immutable one-second wall-time cap and was
terminated by the real process-group timeout path. Missing terminal artifacts,
a mismatched resolved-config hash, and reported cost above the immutable run
cap produced no normalized evidence. The coordinator therefore did not invoke
the evaluator and did not change the incumbent in any of those four cases.

The failure-normalization case is distinct: its manifest and process exit code
consistently report failure, so it is valid negative evidence. The coordinator
may give that retained evidence to the deterministic evaluator, which returns
`FAILED`; the incumbent remains unchanged. This preserves failure evidence
without treating it as a promotable success.

## Isolation and authority proof

- Every scenario began from a fresh temporary Git repository and received its
  own allowlisted proposal, hypothesis branch, clean candidate commit, and
  detached worktree.
- Harness-owned `config-contract` and `dry-run` checks passed before any
  subprocess was authorized.
- Resolved worker configurations and run artifacts were written outside the
  candidate worktrees.
- The stable integration HEAD, index, status, and branch refs were identical
  before and after execution.
- Fixture authorization was explicit and marked synthetic. No paid flags or
  live-provider credentials were involved.
- Invalid or absent evidence could not reach evaluation or promotion.
- Valid failed evidence was retained, deterministically failed, and could not
  advance the incumbent.

## Retained setup and gate failures

Two setup attempts stopped before fixture execution: the first used a zero
campaign LLM budget, which the positive budget-envelope contract rejected; the
second had not created the required worktree-root directory. Both defects were
fixed in separate commits before execution continued.

The first complete six-scenario run is retained as
[`../../results/provider-acceptance/d1/attempt-01-blocked.json`](../../results/provider-acceptance/d1/attempt-01-blocked.json),
SHA-256
`d844f0a7dd3dab4b854defaed45bd2560bec796c356f0204e4e0b85756f2c049`,
41,919 bytes. Its subprocess behavior was correct, but its happy-path assertion
incorrectly expected a one-seed `KEEP`. The frozen evaluator returned
`INCONCLUSIVE`; the acceptance expectation was corrected without changing the
evaluator.

## Reproduction boundary

The passing command was:

```text
python3 scripts/run_d1_subprocess_acceptance.py \
  --acceptance-root /private/tmp/enpire-d1-subprocess-acceptance-v4
```

The runner refuses to overwrite its output or acceptance directory. The
temporary repositories and raw run directories are retained locally at the
recorded paths; the tracked JSON contains the canonical hashes and normalized
records.

The next gate is D2: define and explicitly approve a minimal paid
configuration attachment profile, then execute it on one qualified worker.
