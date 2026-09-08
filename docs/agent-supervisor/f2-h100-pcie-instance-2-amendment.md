# F2 Replacement H100 PCIe Instance Amendment

Status on 2026-09-08: **public provisioning authorized; actor export and paid
retry not authorized for this instance**.

The user selected Lambda instance `488738cc7b404e7aa86ad2e02c70acdf` at
`209.20.158.151`, one NVIDIA H100 PCIe in Utah at `$3.29/hour`. Read-only
inspection found a fresh host with no ENPIRE workspace or actor: x86_64 Ubuntu
22.04, 26 CPUs, 221 GiB RAM, 968 GiB free disk, driver 570.148.08, Docker and
NVIDIA container support, and 81,559 MiB GPU memory.
The exact pinned CUDA base-image digest was then pulled and passed its
in-container GPU identity probe with the same GPU, memory, and driver values.

The hardware class, fixed scientific values, canonical actor and norm hashes,
pinned RLinf/runtime inputs, fixed sequence, and 9,000-second timeout remain
unchanged. Only the provider instance identity, IP, source provenance, and
fresh storage differ. The earlier actor-export and execution approval named a
different instance and IP and therefore does not transfer.

At `$3.29/hour`, the maximum 9,000-second in-container cost remains `$8.2250`.
The displayed 4h32m auto-shutdown window bounded additional instance exposure
at `$14.9147`, excluding the already displayed `$4.78`. Exact source and image
identities must be frozen after provisioning, followed by a new combined
instance-specific actor-export and paid-retry approval.
