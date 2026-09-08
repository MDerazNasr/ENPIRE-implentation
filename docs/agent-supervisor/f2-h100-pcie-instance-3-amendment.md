# F2 Replacement H100 PCIe Instance 3 Amendment

Status on 2026-09-08: **runtime qualified; actor export and paid attempt 3 are
not authorized**.

The user selected Lambda instance `e4907a39365a444c8ae47426f0380019` at
`209.20.158.134`, one NVIDIA H100 PCIe in Utah at `$3.29/hour`. Read-only
inspection found a fresh host with no ENPIRE workspace, source, image, actor,
or prior evidence: x86_64 Ubuntu 22.04.5, 26 CPUs, 221 GiB RAM, 968 GiB free
disk, driver 570.148.08, Docker and NVIDIA container support, and 81,559 MiB
GPU memory.

Attempt 2 on instance `488738cc7b404e7aa86ad2e02c70acdf` actually started,
completed rollout epoch 1 of 4 in 424.50 seconds, and entered epoch 2 before
the host became network-unreachable. Its outcome remains unknown. This fresh
host therefore uses new `attempt3` run/evidence IDs; no attempt-2 directory or
approval is reused.

The hardware class, scientific values, actor and norm hashes, pinned
RLinf/runtime inputs, fixed control/candidate/resume sequence, and 9,000-second
timeout remain unchanged. Only provider identity, IP, source provenance, and
attempt IDs change. Public provisioning is authorized by `connect and go`.
Sensitive actor export and paid execution require a new combined approval after
the source bundle, image identity, probes, tests, and preflight are frozen.

Public provisioning produced image
`sha256:e8e4d6f6f85ac73d2caae1574ff5382895d666c678fe4dd6f6fd92cff71fef55`
(`40,878,572,102` bytes). The exact Python, Torch, CUDA tensor, GPU identity and
memory, RLinf, ManiSkill, SAPIEN, Hydra, OmegaConf, Mesa llvmpipe, norm hash,
and pinned OpenPI norm-loader probes passed. The loader returned the required
`actions` and `state` keys.

The clean tested source is `65137bd37d14733874cff5036e2761830e50487c`;
its deterministic source bundle fingerprint is
`fcc4f3df864e9145b26f2327c08b0e648885eca581f5341e358056e3c5789798`.
The immutable no-launch preflight is
`results/runtime-qualification/f2/h100-pcie-instance-3-preflight.json`. It
keeps actor export and execution false pending the exact combined approval
recorded there.

At `$3.29/hour`, the 9,000-second in-container ceiling remains `$8.2250`. The
user-reported 5h34m auto-shutdown window corresponds to a maximum additional
instance exposure of `$18.3127`, excluding the displayed `$1.38` already spent.
