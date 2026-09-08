# F2 Replacement H100 PCIe Instance Amendment

Status on 2026-09-08: **actor export and fixed paid retry authorized; transfer
pending**.

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

Provisioning completed with image
`sha256:db5450dad1ffc5639abb521ac83d4a4dc0e24673ca682e721e111d0c9a49d2bf`
(`40,873,682,860` bytes). The exact in-image runtime, CUDA tensor, RLinf,
ManiSkill, SAPIEN, Hydra, OmegaConf, norm-loader, and Mesa llvmpipe probes all
passed. The clean tested source is `b487396c...8a630`; immutable preflight is
`results/runtime-qualification/f2/h100-pcie-instance-2-preflight.json`.

The user supplied the exact combined actor-export and paid-retry authorization
at `2026-09-08T12:49:33Z`. It binds the canonical actor, this instance and IP,
source `b487396c...8a630`, bundle `cb94d3fc...acacd6`, the fixed attempt-2
sequence, 9,000-second timeout, and `$8.2250` in-container ceiling. It does not
authorize scientific inference, G1/G2, evaluation, or promotion.
