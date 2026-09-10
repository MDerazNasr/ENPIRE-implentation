# F2 H100 PCIe Instance 7 Amendment

Status: **replacement host qualified; actor-free provisioning authorized;
attempt 7 not yet authorized** on 2026-09-10.

Attempt 6 did not cross the sensitive boundary. Its local actor rehash passed,
but the remote pre-transfer gate timed out twice before authentication. No
actor bytes were exported and no container or F2 workload started. The user
then selected Lambda instance `2ce50e8669184f9f9b95566eabb3d7b0` at
`209.20.157.88`, one H100 PCIe in Utah at `$3.29/hour`.

Read-only qualification passed at `2026-09-10T16:00:32Z`: Ubuntu 22.04.5
x86_64, 26 CPUs, 237,490,958,336 bytes RAM, 1,038,806,708,224 bytes free,
NVIDIA H100 PCIe with 81,559 MiB, driver 570.148.08, Docker 28.3.1, and NVIDIA
container tooling 1.17.8. The host is blank and idle, with no source,
workspace, attempt-6 storage, actor, containers, or GPU compute processes.

The runner reserves fresh attempt-7 Control, Candidate, resume-source, and
resume-continuation IDs plus `attempt-7.json`. Actor-free source/norm sync,
image build, and public qualification are allowed. Actor export, paid
execution, scientific comparison, evaluation, and promotion remain disabled
until the new source, bundle, image, and host envelope is frozen.

Machine-readable evidence is in
`results/runtime-qualification/f0/h100-pcie-instance-7-amendment.json`.

## Actor-free public preflight

Source `d0f9f90433dddd21e91f34c0fb2acc40d3633b25` and bundle
`ee43f1594a88c446eb5986c3e3feb0d1eb5cefae291eeaf05edac336ff1ce943`
were installed without the actor. All 15 remote source hashes match. Exact
image `sha256:5b801ebd5582ae064ea1f678833b5400c3b7225d1a316d8d0d98eeb13f1cd1dc`
is 40,882,743,007 bytes. The public GPU/import probe passed every pinned
runtime contract. The exact-image suite passed 294 tests and 141 subtests;
three archive-only Modal/Git integration checks remain inapplicable. The host
then had no actor, running container, or GPU compute process.

The fixed attempt-7 envelope and the narrow standing-authorization
reconciliation boundary are frozen in
`results/runtime-qualification/f2/h100-pcie-instance-7-preflight.json`.

The subsequent sensitive-egress review rejected carrying the earlier
instance-specific approval onto this new external host. The transfer was
blocked before launch: zero actor bytes were exported and no F2 execution
started. An explicit approval naming this instance/IP and the frozen attempt-7
envelope is required.

The user supplied that exact new-host approval and confirmed the provider
lifetime was extended at `2026-09-10T16:50:18Z`. It binds the private actor,
destination, source, bundle, image, fixed attempt-7 sequence, 9,000-second
timeout, and USD `8.2250` in-container cap. Scientific evaluation and
promotion remain unauthorized.

The fixed four-part transfer completed despite intermittent SSH resets; every
resume followed an exact local/remote prefix hash. All four parts passed two
complete remote hash checks. Ordered assembly, full 10,015,912,759-byte size
and SHA-256 verification, and atomic installation completed at
`2026-09-10T21:01:20Z`. Paid execution has not yet started.
