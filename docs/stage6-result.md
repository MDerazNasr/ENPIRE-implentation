# Stage 6 Candidate-C Result

Status on 2026-08-24: the Modal Candidate-C execution completed cleanly, but
the scientific decision is `INCONCLUSIVE`. The candidate must not be promoted
from this run.

## Outcome

Candidate r3 completed its two bounded segments, reached global step 100,
evaluated all 256 fixed reset-state IDs, saved the final RLinf checkpoint, and
exited zero. No traceback, CUDA out-of-memory, simulator, adapter, or lifecycle
error appears in the final logs.

| Condition | Fixed-eval success | Wilson 95% interval | Candidate-minus-condition |
| --- | ---: | ---: | ---: |
| Reference A | `35/256` (`13.67%`) | not recomputed here | `-1.17` points |
| Control B | `18/256` (`7.03%`) | `4.49%`--`10.84%` | `+5.47` points |
| Candidate C r3 | `32/256` (`12.50%`) | `9.00%`--`17.11%` | -- |

The observed Candidate-minus-Control difference is `+5.46875` percentage
points. Candidate remained `-1.171875` points below the frozen Reference A.
This is a useful observation, not a valid `KEEP` result.

## Why the run is inconclusive

The segmented execution exposed an upstream RLinf resume limitation that the
small paid resume gate did not reveal. At the end of segment 1, global step 60
reported `rlt/update_step=16,400`. After native checkpoint resume, global step
61 reported `rlt/update_step=0`. Segment 2 ended at `15,600` with
`rlt/ready_for_online=0`.

The model, optimizer, target model, and approximately 29,300 replay entries
were restored, but the RLT update/warm-up schedule counter was not. Although
the two segments performed about 32,000 updates in total, the reset made the
second process start another warm-up. Candidate therefore used
`warmup_bc_weight=5.6` throughout and never exercised the intended
`online_bc_weight=2.0`. Control B did cross the 30,000-update gate and entered
its online schedule, so this execution is not a matched test of the
preregistered two-weight intervention.

Two other preregistered limitations remain:

- only seed 2026 exists, while the decision module requires three paired seeds
  and a 95% interval for the across-seed delta;
- Modal used Torch 2.8/CUDA 12.8, CPU PhysX, llvmpipe rendering, and a
  project-owned 16-process batching adapter, unlike Control B's runtime.

The formal D1 result is therefore `INCONCLUSIVE`, and the operational action is
to retain the prior configuration rather than promote Candidate C. Calling it
`REVERT` would overstate the evidence: the executed schedule did not faithfully
test the planned candidate.

## Execution and cost

| Segment | Steps | Elapsed | Launcher estimate | Result |
| --- | ---: | ---: | ---: | --- |
| Training-only | `1--60` | `15.83 h` | `$47.9604` | Complete |
| Resume + final evaluation | `61--100` | `14.64 h` | `$44.3446` | Complete |
| Combined | `1--100` | `30.46 h` | `$92.3051` | Complete execution |

At the final audit, the Modal workspace showed `$153.20` total metered usage
and `$123.08` billed after `$30.00` credits. That provider figure is the whole
workspace cycle and must not be attributed solely to Candidate r3. Modal has
no active app now, so no GPU compute is running; the persistent volume alone
continues to incur storage cost.

## Artifact integrity

The final `global_step_100` checkpoint contains and locally verifies:

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| DCP metadata | `60,017` | `d633244d13a7f88aa8b0595003fe5e890f5a1b8c6ba6702d327ecb5634d77def` |
| Candidate policy | `8,338,321` | `717b8cad468f24335ed35234a70575602e62e0b9a0d9de0195ceaf4b4e0a8d7c` |
| Target model | `8,340,023` | `362f09914fc5290df939d7ada23d2b82080eb64f8222f25a2ebae2e0b9333e3f` |
| Replay index | `8,157,488` | `6e4f2b1f18eba28d23ff90b1b92c275f7e2ed3506d6d8fe449d9ea013559a70c` |

Compact raw logs and these files are backed up locally under
`tmp/fresh-chain-20260807/evidence/stage6-candidate-r3-final/`. The tracked
machine-readable result is
`results/stage6-modal/stage6-candidate-c-modal-multiprocess-seed2026-r3/summary.json`.

## Next gate

Do not spend on another full Candidate run yet. First extend the native-resume
gate past the schedule transition or explicitly persist/restore the RLT
`update_step` and warm-up schedule state, then prove that `ready_for_online`
changes at the same cumulative update count across a process restart. Only
after that bounded test passes should the team choose between a scientifically
matched rerun and closing D1 with this provisional engineering result.
