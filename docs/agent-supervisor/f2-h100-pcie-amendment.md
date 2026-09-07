# F2 H100 PCIe Runtime Amendment

Status on 2026-09-07: **provisioning authorized; actor export and retry execution
not yet authorized for this instance**.

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
