# G0 Seeds and Reset-Set Design

Status: **episode-seed artifacts exported and live CPU reset-confirmed; final
custody pending; no evaluation, campaign, GPU, paid, or model-egress authority**

Obsidian task: `MI5T8`

This design resolves the policy shape for training seeds and evaluation sets
without inventing reset IDs that have not been exported from the pinned
simulator. It supports E0 evaluator-integrity work and the later E1/E2 protocol
freeze. Human review and exact reset artifacts are still required.

## 1. Objectives

The design must:

- estimate Stage-2 condition variance with paired training seeds;
- compare every E2 condition from the same Stage-1 actor;
- retain continuity with the historical 256-reset evaluation while preventing
  development-set tuning from contaminating final confirmation;
- bind evaluation to explicit ordered reset IDs rather than a generator claim;
- keep final reset IDs outside agent-visible contexts; and
- fail closed on missing, duplicate, overlapping, reordered, or substituted IDs.

## 2. Proposed training seeds

Use the exact ordered Stage-2 seed set:

```text
[2026, 2027, 2028]
```

Rationale:

- three seeds satisfy the existing version-1 D1 evaluator contract;
- adjacent integers are transparent, fixed before new outcomes, and do not
  encode a result-dependent selection rule;
- seed 2026 preserves continuity with historical diagnostics; and
- seeds 2027 and 2028 add two unseen Stage-2 initializations.

Seed 2026 must be rerun for every approved E2 condition. Historical seed-2026
Control and Candidate results used different execution paths, so they remain
diagnostic evidence and cannot be inserted into the matched comparison.

No failed seed may be replaced after outcomes are observed. A missing seed
makes the corresponding paired comparison `INCONCLUSIVE` unless the frozen
retry policy produces a valid result under the same run identity contract.

## 3. Stage-1 lineage decision

For the first E2 causal comparison, use one E1-selected Stage-1 actor trained
with seed 2026 and hold its exact SHA-256 fixed across all Stage-2 seeds and
conditions. This isolates the scheduled-BC intervention and Stage-2 variance.

The first E2 campaign therefore does not estimate Stage-1 seed variance. State
that limitation explicitly. A multi-Stage-1-seed study is a separate factorial
experiment and must not be introduced silently into E2.

E1 may inspect checkpoints from one uninterrupted seed-2026 lineage on the
development set. It must select the horizon using a frozen plateau and
non-degeneracy rule. The selected actor must then be exported once and
independently size/hash verified before E2 contracts are generated.

## 4. Proposed evaluation sets

Create two explicit, ordered, disjoint sets:

| Set | Size | Generator namespace | Purpose | Agent visibility |
|---|---:|---|---|---|
| Development | 256 | pinned upstream fixed-reset generator, seed `2026` | E1 horizon selection and E2 diagnostics | bounded normalized summaries only |
| Final | 256 | same pinned generator and task, independent seed `2027` | one frozen confirmation evaluation | IDs and raw evaluator inputs hidden |

The development seed preserves continuity with the prior D1 evaluation route.
The final seed is fixed now, before new policy outcomes, and creates an
independent namespace. The seed values are protocol metadata; the exported
ordered ID artifacts—not generator prose—are authoritative.

The export procedure must run against the pinned task/simulator/runtime source
and produce, for each set:

- schema version and logical set ID;
- task, simulator, project, and RLinf identities;
- generator implementation hash and generator seed;
- exactly 256 ordered reset IDs;
- uniqueness count;
- canonical UTF-8 JSON bytes; and
- SHA-256 plus byte count.

Before acceptance, a GPU-free verifier must prove:

- each artifact contains exactly 256 unique IDs;
- development and final intersection size is zero;
- repeated export is byte-identical;
- task, generator, and source identities match the protocol;
- order changes alter the artifact hash and are rejected;
- set substitution and partial/duplicate input fail closed; and
- the evaluator binds the artifact hash into every result.

If the pinned simulator cannot deterministically export 512 disjoint valid
states under these namespaces, stop and amend G0. Do not fabricate IDs, reuse
the development set as final, or silently change the task/generator.

## 5. Access and storage

Development IDs live in a reviewed read-only evaluator input area. Proposers
may receive bounded aggregate development metrics but not raw trajectories or
an editable copy of the evaluator.

Final IDs live in a separate evaluator-owned read-only area excluded from:

- proposal context bundles;
- candidate branches and worktrees;
- worker-writable source trees;
- development reports; and
- agent or candidate logs.

The final artifact hash and count may be public in the protocol. The ordered
IDs remain unavailable to proposers until the campaign is terminal. Workers
receive only the fixed evaluator/run contract needed to execute confirmation.

Pinned-source audit established that RLinf's internal `reset_state_ids` are not
the actual initial state identities for this task. The artifacts therefore
record ManiSkill's expanded `_episode_seed` values. See
[`g0-reset-source-audit.md`](g0-reset-source-audit.md). A live CPU-only check
performed all 512 resets and matched both exported ordered sequences. Final
evaluator custody and the full scientific runtime identity are still required.

## 6. Pairing and evaluation semantics

Every Control/Candidate condition for a given training seed uses the identical
ordered development set and, during confirmation, the identical ordered final
set. Preserve episode-level outcomes keyed by reset ID so paired analysis can
be reconstructed; condition-level success means alone are insufficient when
episode-level evidence is available.

The existing primary endpoint remains `eval/success_once`. The current D1 rule
requires all three paired seed aggregates. The exact confidence procedure and
decision thresholds remain a separate G0 decision and are not approved by this
document.

Reference A may be evaluated once per frozen Stage-1 actor and reset-set
artifact because it has no Stage-2 training seed. Its result may be shared as
a descriptive reference across E2 conditions only when its actor, task,
runtime, evaluator, and reset-set hashes match exactly. It is not a substitute
for per-seed Control evidence and does not enter the paired Control/Candidate
interval as three duplicated observations.

## 7. Required artifacts before freeze

- [x] Canonical development reset-set JSON and SHA-256
- [ ] Canonical final reset-set JSON and SHA-256 under evaluator custody
- [x] Generator/source identity record
- [x] Byte-identical repeat-export record
- [x] Uniqueness and zero-overlap report
- [x] Agent-context exclusion test for final inputs
- [x] Evaluator binding and substitution-failure tests
- [ ] Human acceptance of seeds `[2026, 2027, 2028]`
- [ ] Human acceptance of one fixed seed-2026 Stage-1 actor for first E2
- [ ] Human acceptance of the Reference A sharing boundary

Until these boxes are reviewed and their real artifact hashes replace
placeholders in the G0 worksheet, this document grants no execution authority.
