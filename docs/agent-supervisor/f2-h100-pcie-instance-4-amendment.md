# F2 Replacement H100 PCIe Instance 4 Amendment

Status on 2026-09-09: **user reports booting; SSH qualification pending; no
source sync, actor export, or paid attempt-4 execution authorized**.

The user selected Lambda instance `a5f648f727ab499087a54c598e975e97`
at `209.20.157.182`, one user-reported H100 PCIe in Utah at `$3.29/hour`.
The dashboard showed `$0.17` spent and 3h56m until auto-shutdown. That window
has a maximum additional exposure of `$12.9407`; it is shorter than the
transfer, integrity, and 9,000-second rehearsal envelope and should be extended
by at least six hours before any approved execution.

Three bounded SSH attempts timed out on port 22 before authentication while
the dashboard still reported `booting`. No remote command executed. Nothing
was copied, no actor bytes left the local machine, and no container or GPU
workload was launched.

The candidate host remains unqualified until read-only inspection confirms its
OS, architecture, CPU, RAM, disk, exact GPU identity and memory, driver, Docker
and NVIDIA container support, source/workspace state, and absence of running
containers or GPU processes. The corrected source freeze remains commit
`6ac01eb1f2d8e53f53da96d5da2466fa9588bfbe`, fingerprint
`171e07f7b5e9f29d8c5954b31f7aaa5ca5d8bedd4eba4bb0ede4696dfd1312e1`.

After SSH qualification, instance 4 must be bound into the runner and runtime
amendment, all 296 tests must pass, and a new host-specific no-launch preflight
must be frozen. Source sync, actor export, and attempt-4 execution remain false
until the user separately approves that exact source, bundle, instance, IP,
destination, fixed sequence, 9,000-second timeout, and cost ceiling.
