# F1 Fixed Modal Worker RPC

Status: **implemented and locally verified; immutable no-launch preflight and
explicit paid approval pending**.

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

## Remaining gate

After this implementation is committed, the no-launch preflight will bind the
clean commit, F0 contract, deployment command, source bundle, and two exact run
contracts. Deployment and GPU execution still require explicit approval of
that preflight and cost ceiling. Live acceptance must then prove the completed
lifecycle, restart recovery, verified transfer, cancellation/late-result
behavior, spoof rejection, actual telemetry, and tagged provider billing.

Passing those checks will complete F1. F2—not F1—will run bounded
Control-shaped and Candidate-shaped RLinf rehearsals.
