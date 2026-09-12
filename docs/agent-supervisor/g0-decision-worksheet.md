# G0 Scientific Protocol Decision Worksheet

Status: **draft for human review; no GPU, paid-provider, model-egress,
evaluation, promotion, or campaign-activation authority**

Obsidian task: `MI5T8`

This worksheet turns the G0 test program into explicit review decisions. It is
not an approval envelope and cannot authorize E1, E2, or any other paid run.
Complete it before implementing E0 or generating a paid scientific preflight.
Unknown values must remain `TBD`; do not infer them from historical results.

Authoritative design:
[`g0-scientific-experiment-test-program.md`](g0-scientific-experiment-test-program.md).
Current product boundary:
[`harness-product-and-operations-guide.md`](harness-product-and-operations-guide.md).
Proposed seed/reset design:
[`g0-seeds-and-reset-sets.md`](g0-seeds-and-reset-sets.md).
E0 integrity implementation:
[`g0-e0-independent-evaluator.md`](g0-e0-independent-evaluator.md).
Non-authorizing remaining-decision candidate:
[`g0-remaining-decisions-proposal.md`](g0-remaining-decisions-proposal.md).
Runtime/cost/retention freeze candidate:
[`g0-runtime-cost-retention-candidate.md`](g0-runtime-cost-retention-candidate.md).

## 1. Review identity

| Decision | Value |
|---|---|
| Protocol ID | `TBD` |
| Protocol schema version | `TBD` |
| Reviewed project commit | `TBD` |
| Reviewed supervisor commit | `TBD` |
| Pinned RLinf commit | `c90951a0c799a750cb5294ed10587c61cc2af8bf` (confirm) |
| Human reviewer | `TBD` |
| Review timestamp, UTC | `TBD` |
| Review disposition | `TBD: approve / revise / reject` |

Acceptance condition: every source identity is immutable and the review occurs
before E0 implementation results, proposals, or new policy outcomes are seen.

## 2. Claim decomposition and order

Confirm or revise the independent questions:

- [ ] E0: the independent evaluator is deterministic and isolated from candidates.
- [ ] E1: the selected Stage-1 horizon produces a non-degenerate starting actor.
- [ ] E2: scheduled BC reduction improves Stage-2 outcomes under a matched comparison.
- [ ] E3: deterministic three-child search behaves reproducibly.
- [ ] E4: the agentic proposer adds value over manual and random/grid search.
- [ ] E5: parallel scheduling reduces wall time without changing evidence or decisions.
- [ ] E6: secondary metrics are deterministic and non-agent-controllable.
- [ ] Approve order `E0 -> E1 -> E2 -> E3/E4 -> E5/E6`, with later work
  conditional on earlier gates.

Decision or amendment: `TBD`

## 3. Frozen scientific identities

| Identity | Decision / SHA-256 |
|---|---|
| Task and simulator version | Proposed: `PegInsertionSideWideClearance-v1`; RLinf `c90951a0...af8bf`; ManiSkill `33967b9e...f0907`; SAPIEN `3.0.1` |
| Base VLA/model | `TBD` |
| Stage-1 input lineage | `TBD` |
| Dataset | `TBD` |
| Normalization statistics | `TBD` |
| Runtime contract and image | **Accepted design preference:** Lambda H100 PCIe at `$3.29/hour`; instance `15c6fcfe...9b688`, clean source `bb52372...c050`, image `06232835...705fd`, and actor-free 16-process route passed, while storage/lifetime binding remains required |
| Training configuration base | `TBD` |
| Primary metric | Proposed: fixed-set `eval/success_once`; `TBD` |
| Secondary metrics | `TBD` |

- [ ] Canonical RLinf and base VLA weights remain immutable.
- [ ] Candidate worktrees cannot modify these identities.
- [ ] Every run and report records these identities.

## 4. Seeds, lineage, and historical evidence

| Decision | Value |
|---|---|
| Exact paired training seeds | **Accepted 2026-09-11:** `[2026, 2027, 2028]` |
| Stage-1 treatment in first E2 | **Accepted 2026-09-11:** one E1-selected seed-2026 actor fixed across all conditions and Stage-2 seeds |
| Stage-1 seed variance | **Accepted boundary:** out of scope for first E2; separate factorial study if later approved |
| Must historical seed 2026 be rerun? | **Accepted:** yes, because historical Control/Candidate runtime paths differed |
| Can one Reference A evaluation be shared across Stage-2 seeds? | **Accepted:** yes as a descriptive actor/reset-set reference when all identities match; never duplicate it as three paired observations |
| Historical one-seed evidence role | **Accepted:** diagnostics only; never part of the matched final comparison |

- [ ] No selective seed replacement is permitted after outcomes are observed.
- [ ] Failed, interrupted, retried, reverted, and inconclusive attempts remain retained.
- [ ] Duplicate-risk and unknown-run handling are frozen before dispatch.

## 5. Development and final evaluation sets

| Decision | Development | Final confirmation |
|---|---|---|
| Reset-set construction | **Source-derived and CPU reset-confirmed:** pinned ManiSkill episode-seed expansion, seed `2026` | **Source-derived and CPU reset-confirmed:** same expansion, seed `2027`; production custody pending |
| Reset count | Proposed: `256` | Proposed: `256` |
| Reset-set SHA-256 | `e5466ff22121cf1429a1f710639cc31ed14b67430e3c84f3760fd184a3a6e161` | `27165db099dfaddc66a6eced98156110acb2e877289eb1c503ae53a446d2fa97` |
| Visibility to proposer | Bounded normalized summaries only | No access |
| Evaluation cadence | E1 selection and approved development diagnostics; exact cadence `TBD` | Once on frozen selected candidates |

- [ ] Sets are disjoint.
- [ ] Final reset IDs and evaluator implementation are outside agent-visible context.
- [ ] Reset substitution, duplication, partial evaluation, and identity drift fail closed.
- [ ] Development evidence cannot be relabelled as final evidence.
- [ ] Both explicit ordered artifacts reproduce byte-identically and contain
  256 unique IDs with zero cross-set overlap.

## 6. E0 independent-evaluator integrity

| Decision | Value |
|---|---|
| Evaluator source root | `TBD: separate read-only root` |
| Evaluator version | `TBD` |
| Evaluator source SHA-256 | `TBD` |
| Evaluator environment/image SHA-256 | `TBD` |
| Canonical normalized-output schema | `TBD` |
| Ledger destination and trusted anchor | `TBD` |

Required adversarial fixtures:

- [x] Repeated fixture replay produces byte-identical normalized metrics and decisions.
- [x] Agent prose and fabricated success text have no effect on the fixture input contract.
- [x] Malformed/non-boolean trajectory metrics fail closed.
- [x] Missing trajectories and partial or duplicate seeds fail closed.
- [x] Development/final reset substitution, reordering, and overlap fail closed.
- [x] Candidate/evaluator source and environment identities are hash-bound;
  condition commit mismatch fails closed.
- [ ] Production evaluator tampering and path escape fail closed from the
  separate read-only root.
- [x] Fixture bundle inventory/hash tampering fails closed and repeated
  standalone replay is byte-stable.
- [x] Fixture ledger/anchor deletion mismatch and chain tampering fail closed.
- [x] Same-user local isolation rehearsal binds bundle/final hashes, separated
  ledger/anchor roots, and explicitly refuses production qualification.
- [x] Production custody and deployment receipt schemas fail closed on access,
  identity, authority, and ledger/anchor violations.
- [ ] Production OS identity or immutable mount, environment hash, ledger
  destination, and independently controlled anchor are reviewed and frozen.
- [ ] Candidate worktrees cannot modify evaluator inputs or ledger output.
- [x] Forbidden final evaluator/reset fields are rejected from nested fixture contexts.
- [ ] The actual production context-builder and worker path prove final-input exclusion.

Current E0 fixture preflight:
`results/agent-supervisor/g0/e0-preflight-lambda-h100-route-v1.json`. Its
envelope hash is recorded inside the artifact to avoid a self-referential
documentation hash. This is not an E0 pass artifact; production custody,
deployment, and actual context/worker exclusion remain blocked.

## 7. E1 Stage-1 horizon selection

| Decision | Value |
|---|---|
| Proposed checkpoint grid | **Accepted 2026-09-11:** `[250, 500, 1000, 2000]` |
| Pilot seed policy | **Accepted:** one uninterrupted seed-2026 lineage |
| Checkpoint cadence | **Accepted:** 250 steps; evaluate the four grid checkpoints |
| Non-degeneracy threshold | **Accepted:** complete 256-reset development evaluation and success `>=0.05` |
| Plateau/stopping rule | **Accepted:** highest development success, exact tie selects earlier; plateau is diagnostic only |
| Seed-dependence follow-up | **Accepted boundary:** outside first E2 |
| Timeout per run | `TBD` |
| Maximum E1 GPU cost | `TBD` |
| Checkpoint retention | `TBD` |

- [ ] Dataset size and batch semantics justify the checkpoint grid.
- [ ] One uninterrupted seed-2026 Stage-1 lineage is used for the first E1
  horizon decision, unless human review replaces this proposal.
- [ ] Selection uses development results only.
- [ ] Every candidate checkpoint loads without fallback and has complete ancestry.
- [ ] The selected actor receives an independent size and SHA-256 verification.
- [ ] A separate paid approval is required after this design is frozen.

## 8. E2 BC-schedule theory pilot

Proposed conditions:

| Condition | Warm-up BC | Online BC | Decision |
|---|---:|---:|---|
| Control | `7.0` | `2.5` | **Accepted** |
| Candidate | `5.6` | `2.0` | **Accepted** |
| Strong reduction | `4.2` | `1.5` | **Omitted from first E2** |

| Decision | Value |
|---|---|
| Number of conditions | **Accepted:** two |
| Paired seeds per condition | **Accepted:** three |
| Stage-2 horizon and checkpoint cadence | **Accepted:** 120 runner steps; validate/save at 120 |
| Maximum updates and transition schedule | **Accepted:** preserve accepted matched F2 mechanics |
| Q weights and other frozen fields | **Accepted:** `0.05/0.45`; all non-BC fields matched |
| Sequential or concurrent workers | **Accepted:** either, only with identical immutable runtime contracts |

- [ ] Static comparison permits only the approved BC differences.
- [ ] Every condition begins from the exact E1-selected actor.
- [ ] Schedule/replay sidecars satisfy the passed F2 contract.
- [ ] Simulator state is not claimed bitwise continuous across processes.
- [ ] All paired conditions receive identical evaluation and compute allocation.

Minimum run count: two conditions require six Stage-2 seed runs; three
conditions require nine. This tests the BC/RLT hypothesis, not agent value.

## 9. Metrics and deterministic decision rule

| Decision | Value |
|---|---|
| Primary endpoint | **Accepted:** paired final `eval/success_once` difference versus Control |
| Confidence/interval method | **Accepted:** paired seed deltas, two-sided Student-t 95%, df=2 |
| `KEEP` threshold | **Accepted:** mean delta `>=0.05` and lower bound `>0` |
| `REVERT` threshold | **Accepted:** upper bound `<0` |
| `INCONCLUSIVE` conditions | **Accepted:** all other valid outcomes and every integrity/failure condition below |
| Missing-seed rule | **Accepted:** fail closed as inconclusive |
| Runtime/non-finite failure rule | **Accepted:** fail closed as inconclusive |
| Tie-breaking role of secondary metrics | **Accepted:** none |

Secondary diagnostics to accept, reject, or define:

- [ ] Development learning curve and area under the curve
- [ ] Time, episodes, and samples to a frozen threshold
- [ ] Update, replay, and transition counters
- [ ] Wall time and GPU cost
- [ ] Peak VRAM/RAM and checkpoint size
- [ ] Failure and retry rate
- [ ] Task-quality metrics only after their E6 definitions pass

No metric may be added, reweighted, or promoted after results are observed.

## 10. Failure, retry, and retention rules

| Decision | Value |
|---|---|
| Maximum attempts per seed run | Proposed: `2` including original |
| Retryable failure classes | Proposed: preregistered infrastructure/transport failure before usable policy outcome only |
| Unknown remote status handling | Proposed: preserve as unknown; no silent duplicate |
| Duplicate-risk authorization rule | Proposed: new identity and explicit risk-bound approval |
| Timeout behavior | Proposed: terminate/block later dispatch, retain actual evidence, no automatic retry after workload start |
| Cost-overrun behavior | Proposed: record actual and block later dispatch |
| Compact evidence retention | Proposed: indefinite in Git |
| Large checkpoint/replay retention | Proposed: minimum 30 days after terminal reconciliation; deletion requires verified export and human approval |
| W&B/object-store role | Proposed: non-authoritative mirror only |

- [ ] Invalid proposals and failed/inconclusive runs consume their allocated slot.
- [ ] Corrections create superseding records; terminal evidence is not overwritten.
- [ ] Required failure diagnostics are retained before any ephemeral cleanup.
- [ ] Secrets, credentials, private transcripts, and unnecessary host details are excluded.

## 11. Run matrix and budget envelope

Complete this table before paid approval:

| Phase | Conditions | Seeds/runs | Runtime | Timeout/run | Max GPU cost | Max storage | Status |
|---|---:|---:|---|---:|---:|---:|---|
| E0 evaluator integrity | fixture/adversarial | GPU-free fixtures | local/read-only | local | `$0` | included below | rehearsals pass; production blocked |
| E1 horizon selection | one lineage | `1`, max 2 attempts | preferred Lambda H100 PCIe | proposed 24 h | proposed `$157.92` retry-inclusive compute | shared `500 GiB`, price/store TBD | unauthorized |
| E2 BC pilot | `2` | `6`, max 12 attempts | same freshly qualified runtime | proposed 48 h | proposed `$1,895.04` retry-inclusive compute | shared `500 GiB`, price/store TBD | unauthorized |

Additional envelope decisions:

- Maximum concurrency: proposed `3`
- Total wall-clock ceiling: proposed `864,000` seconds
- Total compute ceiling: proposed `$2,860`
- One-month storage ceiling: proposed `$45` / `500 GiB`
- Total program ceiling: proposed `$2,905`
- Cost notification thresholds: proposed 25%, 50%, 75%, 90%
- Auto-stop conditions: proposed time or compute cap, plus identity/evidence failure
- Provider billing lifecycle and terminal idle check: required before and after every attempt
- Artifact-storage cleanup gate: no automatic deletion; verified export and human approval required

This worksheet does not authorize any row. E1 and E2 each require a later
fingerprinted approval naming the exact source, assets, runtime, destination,
run IDs, timeout, budget, and UTC window.

## 12. Final G0 disposition

- [ ] Every `TBD` required for E0 has been resolved.
- [ ] E0 implementation is authorized, GPU-free only.
- [ ] Every E1/E2 scientific choice is frozen before outcomes are observed.
- [ ] Complete run matrix and worst-case cost are reviewed.
- [ ] Claim language is limited to the frozen task/runtime/protocol.
- [ ] The reviewer explicitly confirms that G0 is design approval, not paid-run approval.

Reviewer decision: `TBD`

Reviewer name: `TBD`

Reviewed protocol fingerprint: `TBD`

UTC timestamp: `TBD`

Required amendments: `TBD`
