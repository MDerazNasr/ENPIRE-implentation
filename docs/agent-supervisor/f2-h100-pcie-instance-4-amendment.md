# F2 Replacement H100 PCIe Instance 4 Amendment

Status on 2026-09-09: **read-only host qualification passed; public
provisioning, source sync, actor export, and paid attempt-4 execution are not
authorized**.

The user selected Lambda instance `a5f648f727ab499087a54c598e975e97`
at `209.20.157.182`, one user-reported H100 PCIe in Utah at `$3.29/hour`.
The dashboard showed `$0.17` spent and 3h56m until auto-shutdown. That window
has a maximum additional exposure of `$12.9407`; it is shorter than the
transfer, integrity, and 9,000-second rehearsal envelope and should be extended
by at least six hours before any approved execution.

Three bounded SSH attempts initially timed out on port 22 before authentication
while the dashboard still reported `booting`. A fourth check connected at
`2026-09-09T10:51:10Z`. Read-only inspection confirmed x86_64 Ubuntu 22.04.5,
26 CPUs, 231,924,772 KiB RAM, 1,038,806,708,224 bytes free disk, NVIDIA H100
PCIe with 81,559 MiB and driver 570.148.08, plus Docker and NVIDIA container
tooling. The host is blank: neither `/home/ubuntu/enpire-workspace` nor
`/home/ubuntu/qualia` exists. It has zero running containers and zero GPU
compute processes.

The read-only host gate is complete. The corrected source freeze remains commit
`6ac01eb1f2d8e53f53da96d5da2466fa9588bfbe`, fingerprint
`171e07f7b5e9f29d8c5954b31f7aaa5ca5d8bedd4eba4bb0ede4696dfd1312e1`.

Instance 4 must now be bound into the runner, all 296 tests must pass, and the
host-specific source must be committed. Public source/norm sync, image build
and probes, actor export, and attempt-4 execution remain false. A fully
qualified no-launch preflight can be frozen only after public provisioning is
authorized and its exact image identity/probes pass. Paid execution still
requires separate approval of the exact source, bundle, instance, IP,
destination, fixed sequence, 9,000-second timeout, and cost ceiling.

The host-bound source is commit
`4c6b631ef1227f9b75b8e3282f52f5fcaf48f1b8`, with canonical operational
fingerprint
`e0341908b59b1bc1139a5036047f9842e92b512b7e3f755c259ff02973b72887`.
The non-authorizing public-provisioning gate is
`results/runtime-qualification/f2/h100-pcie-instance-4-preprovision.json`.
Its status is `host_bound_awaiting_public_provisioning_authorization`.
