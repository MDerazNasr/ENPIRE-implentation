# Control B Completion Summary

- Run: `stage5d-control-b-h100-recovery-offload-disabled-seed2026-20260809-r2`
- Status: complete, exit code 0
- Finished: 2026-08-10 19:10:25 UTC
- Runtime: 100,639.17 seconds (27.96 hours)
- Run-attributed cost: $91.9730
- Cumulative tracked cost: $189.8249
- Training: 100/100 runner steps; replay approximately 45,000 transitions
- Online gate: `update_step=30,800`; `ready_for_online=1`
- Evaluation: 18/256 successes (7.03125%), mean episode length 470.30
- Wilson 95% interval: 4.49% to 10.84%
- Matched Reference A: 35/256 (13.671875%)
- Control-minus-reference: -6.640625 percentage points

## Local verification

- Complete evidence archive size: 589,529,267 bytes
- Complete evidence archive SHA-256:
  `c399ebad392c82bb7c13e0be91955c7e5bc72a980ab0fefcab46672a0a978dfc`
- Complete remote checkpoint size: 2,098,689,720 bytes
- Compact policy size: 8,337,914 bytes
- Compact policy SHA-256:
  `0090d1f6c9fb1feb43ea459570872d93eeed92e9c2e1cff871ba3e6050cafd34`
- DCP shard SHA-256:
  `2be04c29fb845e710e8c60ab0e2949eab980383f659cd5712e4af69e6aab2c96`
- DCP metadata SHA-256:
  `73d41e4d61d00d0038a62ac8950b0865651d32cef9ee60d1e927c503cb69aed2`
- Target model SHA-256:
  `ac6ab822027692ce2687f8b2f041e4d9296e1c28915e904cd76fc8ace9264bc1`
- Replay index SHA-256:
  `386cc896b0f76a85b9d56e9d1aff0d9034318c450778c88628aeefc3d9ad764e`

The archive checksum matches the remote source exactly. The compact policy
checksum also matches and the file deserializes successfully using the pinned
RLinf PyTorch environment. The full replay/checkpoint remains compressed in
the verified archive; compact policy, manifest, command, logs, metrics,
resource ledger, and checkpoint metadata were selectively extracted locally.

Candidate C was not launched.
