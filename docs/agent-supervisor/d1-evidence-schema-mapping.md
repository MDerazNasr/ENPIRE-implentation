# D1 Source Evidence to Supervisor Schema Mapping

Date: 2026-09-02

Status: B0 inventory and mapping complete; canonical publication remains
blocked

## Scope and conclusion

This review maps the current `results/d1-evidence-pack/` checkpoint into the
strict version-1 contract implemented by `supervisor/d1_gate.py`. It does not
create `results/d1-stage7/evidence_pack.json`, fill unknown values, approve new
seeds, or strengthen the scientific conclusion.

All ten files in the source directory are tracked and total 53,449 bytes. They
are useful, internally consistent compact evidence, but they are not a valid
supervisor pack. Some gaps are mechanical packaging work; others require new
matched experiments or an explicit scientific approval and cannot be repaired
by transforming the existing files.

## Complete source-directory inventory

| File | Bytes | SHA-256 | Evidence carried | Mapping note |
| --- | ---: | --- | --- | --- |
| `artifact-index.json` | 6,274 | `302296f72614f34008d142b456d8bd7fe61322fb2882a505f2cd7290bac1127c` | Fourteen tracked, local, remote, historical, and interrupted evidence references | Source index, not a version-1 `ArtifactRef` list; it does not index itself, the two tables, or the two SVGs. One entry lacks size/hash and two `/workspace` entries are not locally present. |
| `cost-resources.csv` | 7,418 | `3c9395784cca8470746d8d52c433fe95b503feb01e7f8f4973b8577c76cc1ae4` | 25 training, evaluation, recovery, and workspace-cost rows | Best source for the `cost-report` role. It honestly distinguishes launcher estimates, run-attributed cost, and workspace billing, but several fields are unavailable. |
| `fixed-eval-success.svg` | 3,996 | `aaf44f60df6ee99f769a42fa8f7d50ee1b228d89c65c4896b43eafd3a54315a3` | Seed-2026 fixed-evaluation results and Wilson intervals | Direct input to `plots`; includes invalid r3 with an explicit invalid label. |
| `raw/candidate-c-corrected-final-summary.json` | 2,672 | `67a2723a6e3da8ea8dca5551a12c8cfb25bd11236ab0cb29e89091f903519d41` | Corrected Candidate final metric, checkpoint audit, final-segment cost, hashes, and limitations | Strong compact Candidate source, but it lacks full-chain timestamps, per-segment project commits, a canonical command hash, successful-episode length, and a local complete artifact. |
| `raw/control-b-completion-summary.md` | 1,781 | `95df522da5255870dc62f2357eb05966fc53557290236e154e09536aa0a45266` | Control result, elapsed time, cost, episode length, update state, and archive/checkpoint hashes | Human-readable corroboration. The local archive contains the exact manifest, command, logs, metrics, resources, checkpoint material, and offline W&B run. |
| `raw/control-b-gate-report.json` | 593 | `eff6759f4f15bc9f61857a9de38e7ee7fd631f5e8c1a00cbf0f34d791d0506f4` | Control terminal status, timestamp, elapsed time, costs, update and evaluation gates | Machine-readable corroboration, but not a complete `D1ConditionRun`. |
| `raw/reference-a-matched-metrics.log` | 6,785 | `f421ed16f302cfd569352717e876e8b8fec57baca12cefeacce96278a500ce6b` | Matched Reference A `35/256` result and episode length | Metrics are present, but the compact export lacks an exact run ID, manifest, command, source commit, timestamps, elapsed time, and attributable cost. |
| `raw/stage6r-schedule-resume-gate.json` | 17,701 | `3ab830ce67cb6a058b7de8c3d1ee8a5a8f97048f4b1e1719a62726135078d828` | Passing resume-counter, replay-RNG, schedule, and checkpoint-sidecar audit | Supports Candidate validity and `limitations`; it is a smoke/gate record, not a Reference/Control/Candidate condition run. |
| `resume-counter.svg` | 3,082 | `bbc845b57234bdffee35f08d70e7431d98f3320e61bf831fc87a18b82c07235f` | r3 counter discontinuity and corrected monotonic-resume evidence | Direct input to `plots`; it explains why r3 is invalid and why the corrected chain is admissible as segmented engineering evidence. |
| `run-table.csv` | 3,147 | `dee91c6aa861abf50c1d9ef8c8d961ff9381640d7b83a84b75b4a563f32afb25` | Seven Reference, Control, invalid/interrupted, resume-gate, and corrected-Candidate rows | Best source for `run-table`, but it is intentionally broader and looser than `D1ConditionRun`; string placeholders, aggregate run IDs, and missing provenance prevent direct ingestion. |

The hashes above were recomputed from the integrated worktree. No ignored or
untracked file exists inside this directory.

## Seven required artifact roles

| Required ID | Existing source material | Coverage | What B1 may package | Remaining blocker |
| --- | --- | --- | --- | --- |
| `commands` | Control archive `command.sh`; tracked D1 profiles and launchers; Candidate summary contains a final manifest hash | Partial | A deterministic bundle of exact retained commands plus source references | Matched Reference exact command is absent. Corrected Candidate exact per-segment commands/manifests are not locally packaged; hashes alone are not their contents. |
| `configs` | Five tracked D1 profiles, tracked norm stats, Control resolved config in its archive, Candidate schedule fingerprints | Partial | Hash a reviewed config bundle and retained resolved configs | Reference has no retained resolved manifest. Candidate per-segment resolved configs are not packaged. Current file hashes cannot silently stand in for historical executed hashes. |
| `tracker` | W&B was configured offline; Reference log names offline run `ui1f8mrm`; Control archive contains offline run `62tqjjtx` | Partial, not hosted | Index retained offline material as supplementary and name local JSON/log evidence as authority | There is no hosted W&B URL or complete portable tracker export for every eligible run. No tracker artifact currently covers the corrected Candidate chain. |
| `run-table` | `run-table.csv` plus compact raw summaries | Partial | Generate a strict normalized table from validated source fields | The existing CSV lacks required commits, config/command hashes, timestamps, elapsed/cost fields, and canonical IDs on several eligible rows. Only one paired seed exists. |
| `plots` | `fixed-eval-success.svg`; `resume-counter.svg` | Present for current evidence | Package both tracked SVGs with their actual sizes and hashes | They describe only seed 2026 and cannot supply missing paired-seed results. |
| `cost-report` | `cost-resources.csv`; Control and Candidate compact summaries | Present with explicit missingness | Package the ledger without converting estimates into provider billing | Reference cost is unattributed, some hourly/provider fields are absent, and Candidate totals combine multiple recovery segments. |
| `limitations` | `docs/d1-evidence-pack.md`, both plots, run-table validity fields, Candidate summary, and resume-gate record | Present | Package a reviewed limitations document that preserves one-seed and runtime mismatch boundaries | A reviewer must approve the final text; packaging cannot remove the limitations. |

“Present” means source material can support the artifact role. It does not mean
the role already has a strict `ArtifactRef`, nor that the pack can pass the
gate.

## Indexed evidence outside the compact directory

The source index contains fourteen entries. Read-only existence checks against
the protected original D1 worktree produced the following classification:

| Index entry | Location/state | B0 disposition |
| --- | --- | --- |
| `stage1-matched-step500-actor` | Local untracked, 10,015,912,759 bytes, hash recorded | Required scientific input; external Tier-2 artifact, not suitable for Git. |
| `official-norm-stats` | Tracked and hash verified | Include in config provenance. |
| `reference-a-fresh-metrics` | Tracked and hash verified | Eligible Reference metric source. |
| `reference-a-fresh-run-log` | Local untracked and hash recorded | Supplementary Reference log; contains the offline W&B run ID. |
| `control-b-completion-summary` | Tracked and hash verified | Eligible compact Control source. |
| `control-b-gate-report` | Tracked and hash verified | Eligible compact Control terminal record. |
| `control-b-policy` | Local untracked, 8,337,914 bytes, hash recorded | Tier-2 Control policy. |
| `control-b-complete-archive` | Local untracked, 589,529,267 bytes, hash recorded | Strongest Control source; contains manifest, command, metrics, logs, resources, checkpoint evidence, and offline W&B data. |
| `candidate-r3-policy` | Local untracked and marked do-not-promote | Retain only as invalid historical evidence. |
| `candidate-r3-summary` | Tracked elsewhere, but index size/hash absent | Historical invalid result; B1 should compute its real metadata if it remains referenced. |
| `stage6r-resume-gate` | Tracked and hash verified | Candidate validity evidence, not a condition run. |
| `candidate-r4-interrupted-attempt` | Remote absolute path absent; no checkpoint/hash | Preserve as an explicit failed/interrupted record, never as successful evidence. |
| `candidate-c-corrected-policy` | Remote absolute path absent locally; remote hash recorded | Candidate policy reference is not presently locally reproducible. |
| `candidate-c-corrected-summary` | Tracked and hash verified | Eligible compact corrected-Candidate source. |

The four large local artifacts above remain under the protected 20 GB `tmp/`
tree in the original D1 worktree. B0 did not copy, modify, hash again, or
delete them.

## Strict pack-field availability

| Contract area | Available now | Unavailable or not approved |
| --- | --- | --- |
| Pack review | Honest `INCONCLUSIVE` conclusion and evidence checkpoint commit `eed314f` exist | `pack_id`, reviewer identity, UTC review time, and a reviewed pack commit do not exist yet. |
| Git binding | Control project commit is `59bd897a4d2c64cf7fc2b3c3fa8024d31d449c67`; integration history contains the evidence | A single approved `known_good_commit`, distinct incumbent/candidate commits, and exact corrected-Candidate per-segment project commits are not bound in the compact evidence. `eed314f` cannot be assigned to all fields merely because it publishes the summary. |
| Research identity | Question, RLinf commit `c90951a...8bf`, configuration-only intervention, 100 training steps, 256 evaluations, and seed 2026 are documented | Exact approved three-seed values, reset-ID artifact/hash, evaluator version identifier, artifact namespace, campaign creation time, max concurrency, and frozen GPU/LLM budget envelope are absent. Test-fixture seeds `2026/2027/2028` are not scientific approval. |
| Baseline assertion | Matched Reference is non-zero and Control performed real actor/critic updates | `baseline_non_degenerate: true` still requires explicit pack review; it does not cure runtime mismatch. |
| Reference run | Seed, status, success `35/256`, episode length, config profile/hash, actor hash, and offline W&B trace exist | Exact run ID, project commit, exact command hash, timestamps, elapsed time, attributable GPU cost, and reset-set hash are missing. |
| Control run | Seed, run ID, project/RLinf commits, exact config hash, exact command and manifest, UTC times, elapsed time, cost, `18/256`, episode length, and terminal status exist in the local archive | These fields are not yet normalized into a strict run record; no other approved seeds exist. |
| Corrected Candidate run | Seed, final/aggregate run identity, RLinf commit, status, exit code, `17/256`, final-segment elapsed/cost, policy and source hashes, and limitations exist | Full-chain start/finish and elapsed/cost normalization, exact source commit per segment, canonical config/command hashes, successful-episode length, local final policy/archive, and other approved seeds are missing. |
| Decision replay | Legacy outcome is explicitly `INCONCLUSIVE`; seed-2026 delta is `-0.390625` percentage points | The strict evaluator requires matched Control/Candidate records for every campaign seed. Runtime/simulator/renderer/batching differ, so the current pair is not a strict one-factor comparison. |

## W&B authority by source run

| Source row | W&B state | Authority classification |
| --- | --- | --- |
| Historical Reference A (`33/256`) | No tracker reference in the compact pack | Unavailable for this handoff; historical local summary only. |
| Matched Reference A (`35/256`) | W&B offline run `ui1f8mrm` appears in the protected local run log; no offline run bundle or hosted URL is packaged | Supplementary trace only; tracked metrics plus the hashed local log are authoritative. |
| Control B seed 2026 | Manifest has `wandb_run_url: null`; verified local archive contains offline run `62tqjjtx` | Supplementary and locally retained; manifest, raw logs/metrics, and compact summaries are authoritative. |
| Historical Candidate r3 | Modal configured W&B offline; no tracker identifier/export appears in the compact summary | Unavailable as a pack artifact; tracked invalid summary and hashed local backup are authoritative. |
| Stage-6R resume gate | No tracker identity in the gate result | Not applicable to scientific metrics; the tracked gate JSON is authoritative. |
| Interrupted Candidate r4 | No retained checkpoint or tracker reference | Unavailable; interruption record is authoritative and must remain a failure. |
| Corrected Candidate chain | Modal configured W&B offline; no hosted URL or portable offline export is in the compact evidence | Unavailable as a canonical tracker artifact; the tracked final summary, cost ledger, gate evidence, and recorded remote hashes are authoritative. |

W&B is therefore not authoritative for any current D1 condition. B1 must not
invent URLs or imply that offline run names are hosted objects.

## Packaging gaps versus scientific gaps

### Packaging gaps B1 can address without a GPU

- Build a deterministic readiness report and strict publisher with separate
  incomplete/ready outputs.
- Recompute sizes and hashes for tracked material and locally available
  approved external sources.
- Normalize complete Control fields from its verified archive.
- Bundle the two plots, cost report, and reviewed limitations with strict
  `ArtifactRef` records.
- Represent unavailable fields as explicit blockers in the readiness report;
  never place placeholders in the strict pack.
- Fail closed on absolute remote paths, missing sources, duplicate roles,
  missing hashes, and evidence that does not match the frozen campaign.

### Scientific or approval gaps B1 cannot manufacture

- The two additional matched Control/Candidate seeds do not exist, and their
  exact integer identities have not been approved in project evidence.
- Control and corrected Candidate used different runtime, simulator, renderer,
  and batching paths.
- The exact 256 reset IDs and their SHA-256 are not exported.
- Reference provenance is incomplete, and corrected Candidate provenance is
  not bound to exact per-segment project commits.
- There is no frozen evaluator-version identifier or approved campaign budget
  envelope.
- The corrected Candidate policy remains remote-only according to the index.
- A human has not reviewed and signed a canonical pack.

## B0 gate result

**Passed on 2026-09-02.** Every file in the existing source directory is
inventoried; all seven required roles are mapped; absent fields are explicit;
W&B authority is classified per source run; and packaging gaps are separated
from scientific/approval gaps. The honest current result remains one-seed
`INCONCLUSIVE`. B1 must build a deterministic validator/readiness report that
fails closed on these blockers; it must not publish a gate-ready pack from the
current evidence.
