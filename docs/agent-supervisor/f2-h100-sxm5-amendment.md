# F2 H100 SXM5 Runtime Amendment

Status on 2026-09-06: **authorized and provisioning; live gate not yet
passed**.

The user selected active Lambda instance
`7160d3af448d4925b149ab6e9655344d`, one NVIDIA H100 80 GB SXM5 in Georgia,
at `$4.29/hour`. This replaces the previously prepared Modal RTX PRO 6000 only
for the F2 engineering rehearsal. It does not silently alter the definitive
scientific runtime or authorize G1/G2 training.

Read-only inspection passed before setup: x86_64 Ubuntu host, NVIDIA H100 80GB
HBM3, 81,559 MiB, driver 580.105.08, and approximately 2.7 TB free disk. The
host had no prior `/workspace`, so the canonical actor and pinned environment
must be provisioned fresh.

The runtime uses the same immutable linux/amd64 Ubuntu 22.04 CUDA image digest,
Python 3.11.14, Torch 2.8.0+cu128, pinned RLinf/ManiSkill/SAPIEN, CPU PhysX,
Mesa llvmpipe, 16-process batching, disabled actor offload, CPU weight
transport, strict sidecar, Stage-1 actor hash, and norm-stat hash as F0. The
only intended runtime amendments are provider, H100 SXM5 GPU identity, the
80-GB minimum, and instance billing.

The fixed container runner accepts no arguments. It derives H100 profiles from
the reviewed F2 profiles while changing runtime provenance only, then performs
the same Control step, Candidate step, and two-process resume gate. A 9,000
second in-container bound is `$10.7250`; setup and the 9.3-GiB actor transfer
are also billable. The provider auto-shutdown shown at authorization bounded
the remaining worst-case exposure to 5h57m or `$25.5255`, excluding the
already displayed `$0.14`.

The instance may be switched off only after the result, compact logs,
manifests, generated configs, and hashes have been copied locally and verified.
The operator will notify the user immediately at that point.
