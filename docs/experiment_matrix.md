# D1 Experiment Matrix

Status: Stage 0 contract. Values marked `resolve before run` are Stage 1/2
inputs and block paid scientific execution until recorded.

## Scientific conditions

| Field | Reference A | Control B | Candidate C |
| --- | --- | --- | --- |
| Purpose | Frozen-reference behavior | Upstream Stage-2 RLT baseline | One-factor BC sensitivity test |
| Stage-1 feature checkpoint | Same approved checkpoint | Same approved checkpoint | Same approved checkpoint |
| Environment control | VLA reference chunks only | Stage-2 actor under upstream control logic | Same as Control B |
| Warmup BC weight | Not applicable to control | `7.0` | `5.6` |
| Online BC weight | Not applicable to control | `2.5` | `2.0` |
| Warmup Q weight | Not applicable to control | `0.05` | `0.05` |
| Online Q weight | Not applicable to control | `0.45` | `0.45` |
| Expert takeover | Disabled | Disabled | Disabled |
| Training budget | No Stage-2 actor training | Same approved budget | Same as Control B |
| Stage-2 seeds | Not applicable; evaluation seeds/reset IDs recorded | Same approved three seeds | Same seeds as Control B |
| Evaluation reset IDs | Same fixed set | Same fixed set | Same fixed set |
| Primary endpoint | `eval/success_once` | `eval/success_once` | `eval/success_once` |

## Variables that must remain matched

The following are controls, not tuning variables:

- RLinf and project commits;
- pi0.5 model revision and trained Stage-1 checkpoint;
- full training dataset and normalization statistics;
- ManiSkill task, observation/state/action semantics, and episode horizon;
- training iterations, batch semantics, rollout count, and evaluation cadence;
- evaluation reset IDs and number of trajectories;
- evaluation execution batching (`64` parallel environments x `4` epochs);
- actor/critic architecture, optimizer, learning rate, Q weights, and dropout;
- precision and hardware class where practical;
- expert/intervention policy, logging, metric parser, and success definition.

If an operational failure forces one of these to differ, stop the comparison or
record it as a new condition. Do not silently continue under the same label.

## Required resolved inputs

| Input | Stage 0 decision | Resolution gate |
| --- | --- | --- |
| Project starting commit | `8c5abfcd04e8b4a155f82e8b3537169169ef8337` | Resolved |
| RLinf commit | `c90951a0c799a750cb5294ed10587c61cc2af8bf` | Resolved |
| Simulator family | RLinf RLT ManiSkill example | Resolved for D1 |
| Exact task/config name | Upstream RLT ManiSkill joint example | Record exact Hydra name before run |
| Base model revision | pi0.5 compatible with upstream example | Resolve immutable identifier |
| Dataset | Full official 400-success-episode data | Resolve path and identifier/hash |
| Normalization statistics | Dataset-matched `norm_stats.json` | Verify contents/path |
| Stage-1 budget/checkpoint | Determined after representative pilot | Explicit approval required |
| Stage-2 seeds | Provisionally three | Record exact integer values before run |
| Evaluation set | Upstream 256 fixed reset IDs | Verify and export IDs |
| Expert checkpoint | None; takeover disabled | Verify identical override |
| Shared tracker | W&B plus local JSONL/raw logs | Resolve project and authentication |
| Hardware | Smallest economical NVIDIA GPU, >=24 GB VRAM | Record model/price before launch |

## Decision table

| Baseline state | Candidate evidence | Decision |
| --- | --- | --- |
| Control success <90% | >=5-point mean success improvement and 95% interval for delta >0 | `KEEP` |
| Control success <90% | Valid complete evidence, but either keep condition fails | `REVERT` |
| Control success >=90% | Success non-inferior within 5 points and successful episode length improves >=10% | `KEEP` |
| Control success >=90% | Valid complete evidence, but either ceiling keep condition fails | `REVERT` |
| Any baseline | Missing seeds, mismatched evaluation, failed condition, or insufficient interval evidence | `INCONCLUSIVE` |

## Deliberate separation from the completed smoke

The existing smoke changed fixed `algorithm.bc_weight` from `1.0` to `0.8`,
forced actor control, used one replay transition, and evaluated one 20-step
trajectory. Its keep/revert rule selected only on immediate success. It remains
valid integration evidence but is not Reference A, Control B, or Candidate C
and must not be pooled with D1 results.
