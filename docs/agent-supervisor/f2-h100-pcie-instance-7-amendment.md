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
