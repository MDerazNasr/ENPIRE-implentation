# F2 H100 PCIe Runtime Amendment

Status on 2026-09-07: **authorized; actor transfer interrupted because the
instance became unreachable; retry not started**.

The user selected Lambda instance `be7f43492c014409ad94d42371ff86d4`,
one NVIDIA H100 PCIe in Utah at `$3.29/hour`, after the prior H100 SXM5 host
auto-shut down before attempt 2 launched. This is a new engineering runtime
identity, not a silent continuation of the SXM5 approval.

Read-only inspection passed: x86_64 Ubuntu 22.04, 26 CPUs, 221 GiB RAM,
968 GiB free disk, driver 570.148.08, Docker and NVIDIA container support, and
81,559 MiB GPU memory. The exact pinned CUDA image digest ran successfully and
reported `NVIDIA H100 PCIe` inside the container.

The fixed runner retains the canonical actor and norm-stat hashes, pinned RLinf
commit, Python/Torch/CUDA stack, CPU PhysX, Mesa llvmpipe, 16-process batching,
disabled actor offload, CPU weight transport, strict sidecar, scientific arm
values, and 9,000-second timeout. It changes only the provider-instance
identity, GPU model/form factor, region, price, generated paths, and new
attempt-2 run IDs. Evaluation and promotion remain forbidden.

At `$3.29/hour`, the 9,000-second in-container ceiling is `$8.2250`. The
displayed 5h23m auto-shutdown window bounded additional instance exposure at
`$17.7102`, excluding the already displayed `$1.98`. Provisioning public code
and dependencies does not authorize exporting the private Stage-1 actor or
starting the paid retry. Both require a new immutable preflight and explicit
instance-specific approval.

The user supplied that exact combined approval at `2026-09-07T16:34:18Z`,
binding the 10,015,912,759-byte actor and its `b5bf9384...363f3` digest to the
named instance and destination, and binding execution to source
`513b139...30490`, bundle `1ad3a363...cdc4d`, the frozen attempt-2 sequence,
9,000-second timeout, and `$8.2250` in-container ceiling. This approval does
not authorize scientific inference, G1/G2, evaluation, or promotion. See
`results/runtime-qualification/f2/h100-pcie-approval-attempt-2.json`.

The transfer preserved 5,272,633,344 prefix bytes across four separate part
files at the last successful check (`2026-09-07T18:12:19Z`). The instance then
failed three bounded SSH checks. No container, rollout, update, evaluation, or
promotion ran. Resume requires confirming the restarted host/IP and persistent
part sizes, completing the export, and passing the exact approved whole-file
size and SHA-256 gate before the already-authorized fixed command may start.
