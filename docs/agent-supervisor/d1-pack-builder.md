# D1 Canonical Pack Builder and Readiness Report

Date: 2026-09-02

Status: B1 implemented; current D1 evidence deterministically reports blocked

## Purpose

`scripts/build_d1_evidence_pack.py` separates two outputs that must never be
confused:

1. `results/d1-stage7/readiness.json` is a deterministic diagnostic envelope.
   It inventories available evidence and names every current blocker. It does
   not claim that a canonical pack exists.
2. `results/d1-stage7/evidence_pack.json` is written only when a reviewed
   source specification passes every strict publication gate.

The implementation is in `supervisor/d1_pack_builder.py` and reuses the
version-1 `D1EvidencePack`, `CampaignSpec`, `D1ConditionRun`, and `ArtifactRef`
contracts. It does not introduce a permissive parallel schema.

## Current readiness command

```bash
python3 scripts/build_d1_evidence_pack.py --repository .
```

Exit code `0` means the strict source can build a valid pack. Exit code `2`
means publication is blocked. The command always writes the readiness envelope
atomically. It writes no canonical pack unless `--publish` is also supplied
and all gates pass.

The 2026-09-02 current-evidence run exits `2`, writes a byte-stable report, and
leaves `evidence_pack.json` absent. Its report hash is
`2259d0aeea3192869d303913be286cb1eeaf609a0fdb4f48953be98274461c97`.
The envelope also contains a canonical SHA-256 over its payload so offline
modification is detectable.

## Reviewed source specification

Canonical publication expects a tracked, clean
`results/d1-stage7/evidence_pack.source.json` with exactly these top-level
fields:

```json
{
  "schema_version": 1,
  "pack": {
    "schema_version": 1,
    "pack_id": "reviewed-pack-id",
    "known_good_commit": "<full ancestor commit>",
    "incumbent_commit": "<full ancestor commit>",
    "candidate_commit": "<different full ancestor commit>",
    "campaign": "<complete CampaignSpec object>",
    "baseline_non_degenerate": true,
    "legacy_decision": "keep-or-revert",
    "reviewed_by": "<reviewer>",
    "reviewed_at": "<UTC ISO-8601 timestamp>",
    "conclusion": "<reviewed conclusion>",
    "runs": "<strict Reference/Control/Candidate run array>"
  },
  "runtime_identity_hashes": {
    "reference": "<sha256>",
    "control": "<same sha256>",
    "candidate": "<same sha256>"
  },
  "artifact_sources": [
    {
      "artifact_id": "commands",
      "kind": "stage7-evidence",
      "path": "<tracked relative bundle path>"
    }
  ]
}
```

The abbreviated strings above describe types; they are not a valid source
file. The real `campaign`, `runs`, and seven artifact-source entries must be
complete strict objects. No draft source is checked in today because the
missing scientific values are not known.

## Publication gates

The builder refuses publication unless all of the following hold:

- the source specification is strict version-1 JSON, tracked by Git, and
  unchanged from its tracked version;
- Reference, Control, and Candidate runtime-identity hashes are present and
  identical;
- artifact IDs are unique and exactly equal `commands`, `configs`, `tracker`,
  `run-table`, `plots`, `cost-report`, and `limitations`;
- every artifact source is a regular, nonsymlink, repository-relative, tracked,
  clean file and is neither the source specification nor output pack;
- artifact sizes and SHA-256 values are computed from actual source bytes;
- the strict campaign has exactly three distinct paired seeds;
- all Reference, Control, and Candidate run records satisfy the existing
  schema, seed matrix, commit mapping, finite-number, status, and metric rules;
- the baseline is explicitly non-degenerate;
- the legacy decision is resolved to `KEEP` or `REVERT`, never
  `INCONCLUSIVE` or `FAILED`; and
- known-good, incumbent, and candidate commits exist and are ancestors of the
  repository `HEAD`.

Missing fields, unknown fields, duplicate roles or runs, non-finite metrics or
costs, partial seeds, mismatched commits, dirty inputs, untracked inputs,
runtime drift, and absent artifacts all fail closed.

## Git binding without self-reference

The source specification names reviewed scientific source commits that already
exist. The builder verifies they are ancestors of `HEAD`. It does not place the
future containing commit hash inside `evidence_pack.json`; doing so would
change that hash. The safe publication sequence is:

1. materialize and review the seven compact artifact bundles;
2. commit those bundles;
3. write the strict source specification using already-existing reviewed
   source commits and commit it;
4. run the publisher from that clean input state;
5. review the computed pack and readiness envelope; and
6. commit the generated pack. That containing Git commit immutably binds the
   pack without appearing inside its own contents.

Re-running the publisher against unchanged inputs produces byte-identical pack
and readiness files.

## Current blocked result

The tracked readiness report records ten source files, 53,449 bytes, fourteen
indexed references, all seven source-role mappings, and the one matched seed
`2026`. It reports these blocker classes:

- missing reviewed canonical source specification;
- one of three paired seeds complete and two seed values not approved;
- Control/Candidate runtime identity mismatch;
- missing reset-set export/hash;
- incomplete campaign, Reference, and corrected-Candidate provenance;
- incomplete offline tracker coverage;
- remote-only corrected Candidate policy; and
- missing reviewer signature and resolved `KEEP`/`REVERT` decision.

These match the B0 audit. No current blocker was converted into a placeholder,
and no GPU, provider, W&B API, network service, or RLinf process is needed to
generate or verify the diagnostic.
