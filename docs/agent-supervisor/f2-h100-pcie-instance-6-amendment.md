# F2 H100 PCIe Instance 6 Amendment

Status: **replacement instance booting; IP and remote state pending; attempt 6
not authorized** on 2026-09-10.

The user selected Lambda instance `268cdf9dce05458fadcf8f6c748f6d85`, one
H100 PCIe in Utah at `$3.29/hour`, with `$0.00` spent and 5h59m until automatic
shutdown. Lambda had not yet assigned a public IP, so no connection or remote
action was possible.

Attempt 5 never launched. Its old host became unreachable after all four actor
parts reached exact sizes; parts 0--2 passed two complete hashes, while part 3
passed one complete-length hash before the repeat connection reset. This new
instance does not inherit those files or the exact old-instance approval.

The runner now reserves fresh attempt-6 Control, Candidate, resume-source, and
resume-continuation IDs plus `attempt-6.json`. Once an IP is available, perform
read-only host qualification and determine whether storage is blank. Source
sync, image build, actor export, paid execution, scientific comparison,
evaluation, and promotion remain unauthorized. A blank replacement requires a
fresh source/bundle/image preflight and exact instance/IP-bound actor-export and
paid attempt-6 approval.

Machine-readable evidence is in
`results/runtime-qualification/f0/h100-pcie-instance-6-amendment.json`.
