# F1 Fixed Modal Worker RPC

Status: **attempts 1 and 2 failed safely before GPU launch; the remaining broad
package-facade defect is corrected locally and requires a third immutable
preflight and explicit approval before redeployment**.

F1 replaces M7's mocked remote boundary with a Modal-native implementation of
the same provider-neutral `ExperimentWorker` interface. The provider transport
is Modal Function lookup because F0 selected Modal; no SSH daemon or agent-held
host is introduced. The fixed endpoint is
`enpire-f1-worker-rpc-v1::rpc`, and the only GPU target it can spawn in this
acceptance phase is the baked-in `bounded_gpu_probe` function.

## Authority boundary

The coding agent cannot supply an app name, function name, host, executable,
command, argv, shell text, image, GPU type, or resource count. The harness owns
all of those values. Requests contain only:

- the fixed worker and F0 runtime identities;
- one of `prepare`, `launch`, `status`, `heartbeat`, `cancel`,
  `fetch_evidence`, or `fetch_artifact`; and
- the typed contract, trial identity, or bounded artifact byte range required
  by that operation.

The complete request is canonically hashed, and the response must echo that
hash. Worker snapshots retain the immutable run-contract hash. Coordinator
restart constructs a new client from the durable scheduler's exact active
contracts; conflicting recovery identities fail closed.

## Remote implementation

[`../../modal_f1_worker.py`](../../modal_f1_worker.py) defines two deployed
functions:

1. `rpc` is a single-container serialized control endpoint backed by the
   existing `enpire-workspace` volume. It stores one immutable contract per
   trial, a detached Modal FunctionCall ID, heartbeat count, terminal evidence,
   and compact artifacts.
2. `bounded_gpu_probe` uses the F0 linux/amd64 CUDA-image digest and exact
   Python, Torch/CUDA, RLinf, ManiSkill, SAPIEN, Mesa, and Vulkan pins. It runs
   a fixed 15-second CUDA matrix workload, verifies llvmpipe Vulkan, records
   live GPU utilization/memory/power samples, and returns non-scientific
   engineering evidence.

Launch uses Modal's asynchronous FunctionCall identity. Status polling
reconstructs that identity, active cancellation requests container termination,
and cancelled state is terminal so a late provider result cannot overwrite it.
Modal documents `spawn`, later `get(timeout=0)` polling, reconstruction from a
FunctionCall ID, and cancellation as supported operations.

## Artifact and evidence handling

Terminal evidence lists exactly three compact artifacts: GPU telemetry, a
rate-times-runtime cost estimate, and the probe log. The server validates their
digests before persisting them. The client fetches at most 256 KiB per request,
caps a single artifact at 8 MiB, verifies every chunk's identity, size, and
full SHA-256, then materializes by atomic create-only rename and fsync.

The cost artifact is explicitly an estimate, not a provider invoice. Live F1
acceptance must also retain Modal's app-tagged billing record. The app is tagged
`project=enpire,phase=f1-worker-acceptance` for this purpose.

## Local verification

The F1 tests cover all lifecycle operations, active cancellation, cancelled
late-status behavior, exact coordinator-restart rebinding, conflicting recovery,
request/response and worker identity spoofing, forbidden actions, malformed or
oversized output, artifact corruption, and atomic transfer. The existing M7
scheduler suite remains the authority for worker loss, retry leases, and stale
late completion after replacement.

The deployment profile is
[`../../results/runtime-qualification/f1/profile.json`](../../results/runtime-qualification/f1/profile.json).
It permits at most two fixed probe calls, 600 aggregate GPU-function seconds,
USD `0.758832` maximum runtime-resource cost, and USD `2.00` maximum total
provider cost including build/control reserve. Promotion and scientific use are
permanently false.

## Live attempt 1

The user approved the exact `4cce0a35...6edb` source bundle and USD `2.00`
ceiling on 2026-09-03. Modal deployed version `v1` as app
`ap-Cp71jN9ObZWaMk1I8hD7IY`. The identity-spoof control was rejected, but the
valid `prepare` operation failed in the CPU control function because the image
copied `supervisor/` to `/opt/qualia` without adding that root to `PYTHONPATH`.
No `launch` request completed and no GPU probe ran.

The attempt also exposed a local client defect: resolving Homebrew's
virtual-environment `bin/python` symlink selected the base Python interpreter,
which did not contain Modal. The correction preserves the symlink and adds
`/opt/qualia` to both image environments. Regression tests now bind both
conditions.

Modal's tagged hourly billing record reports CPU USD `0.01700228`, memory USD
`0.00089371`, and accelerator USD `0.00000000`, for an actual attempt total of
USD `0.01789599`. This is below the approved USD `2.00` ceiling. The immutable
approval and complete compact attempt record are retained in
`results/runtime-qualification/f1/approval-attempt-1.json` and
`results/runtime-qualification/f1/attempt-1.json`.

## Live attempt 2

The user explicitly approved corrected source bundle `9362ec7f...b465b` and
the same bounded cost envelope on 2026-09-04. Modal deployed version `v2` from
commit `2492445`; the identity-spoof control again failed closed. Valid prepare
then exposed a separate import boundary: Python executes
`supervisor/__init__.py` before a `supervisor.*` submodule, and that broad facade
imports unrelated evaluator modules requiring the absent `agent` package.
Prepare failed in the CPU function, so no launch or GPU probe occurred.

The least-authority correction installs a marked minimal `supervisor` namespace
before importing only `canonical`, `contracts`, `workers`, and
`modal_worker_rpc`. It deliberately does not add the agent, evaluator, or
training stack to the image. A local Modal-interpreter probe confirms those F1
modules load while `agent` remains absent. Tagged attempt-2 billing is CPU USD
`0.01375946` plus memory USD `0.00063855`, totaling USD `0.01439801`; no
accelerator entry exists. The cumulative cost of attempts 1 and 2 is USD
`0.03229400`.

## Remaining gate

The clean no-launch preflight passed from implementation commit
`6a1809362b256ff3bd2fd0f83440c400d77abe8f`. It binds F0 runtime SHA-256
`26092812...6e0c`, profile SHA-256 `c4e29258...0522`, source-bundle SHA-256
`4cce0a35...6edb`, the fixed deployment command, and the two exact probe
contracts. The preflight artifact SHA-256 is `c4a57739...6f90`.

The first two preflights and approvals were consumed by their failed bundles
and do not authorize changed source. The minimal-namespace correction must pass
the full suite, be committed, receive a new clean preflight, and obtain explicit
approval before redeployment. Live acceptance must then prove the completed
lifecycle, restart recovery, verified transfer, cancellation/late-result
behavior, spoof rejection, actual telemetry, and tagged provider billing.

Passing those checks will complete F1. F2—not F1—will run bounded
Control-shaped and Candidate-shaped RLinf rehearsals.
