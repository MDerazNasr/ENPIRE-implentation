# M9 Final Demo and Delivery Contract

Status: implemented offline-first. Optional D1 integration is read-only replay;
live or paid execution remains under the M5 authorization contract.

## Purpose

M9 packages the already implemented supervisor into one Ludvig-facing
demonstration. It does not create a second orchestration path or change any
scientific rule. The unified command composes:

- M4: tool-free structured proposal, repair, scope validation, isolated Git
  candidate, worker evidence, deterministic decision, and retained result;
- M7: independent workers, leases, real thread overlap, loss/retry, stale-result
  rejection, and evaluator-only promotion; and
- M8: frozen three-arm preregistration, isolated incumbents, complete discovery
  allocation, deterministic selection, paired confirmation, and reports.

## Offline-first command

```bash
python3 scripts/run_m9_ludvig_demo.py \
  --output /tmp/enpire-m9-ludvig-demo
```

The command requires a clean supervisor repository and an output directory
outside it. It records the starting commit and branch, runs the three component
demos in order, rechecks the commit and worktree, normalizes only their bounded
summaries, and generates the final bundle. Component commands are fixed by the
harness; no agent-authored shell text is executed.

Offline mode makes no provider, GPU, SSH, W&B, RLinf, paid-service, robot, or
network call. Every generated report says that its numerical results are
synthetic control-plane fixtures.

## Optional D1 replay

```bash
python3 scripts/run_m9_ludvig_demo.py \
  --output /tmp/enpire-m9-with-d1 \
  --d1-repository /path/to/d1-worktree
```

This invokes the existing read-only D1 repository audit and evidence replay.
If the gate is blocked or invalid, the offline demo continues and reports the
reasons. This is the meeting-safe fallback.

Adding `--require-d1-ready` changes the behavior to fail closed before M4/M7/M8
if the D1 gate is not ready. It never converts the command into a training
launch. A real run still requires M5 campaign approval, ready equivalent gate,
explicit paid acknowledgement, exact worker contracts, and the agreed compute.

Even a ready D1 replay does not make the synthetic three-arm fixture a
scientific comparison. It proves only that the real D1 evidence seam is ready.

## Delivery payload

`m9-demo.json` contains:

- delivery version and semantic fingerprint;
- supervisor commit, branch, and clean-before/after proof;
- normalized M4/M7/M8 outcomes;
- optional D1 gate/replay status and hash;
- component command hashes and observed rehearsal duration;
- explicit lists of what the bundle proves and does not prove;
- the presenter sequence, limitations, and empty external-call record.

The semantic fingerprint excludes output paths and observed duration. Two runs
from the same supervisor commit and semantic component outcomes therefore
produce the same delivery fingerprint, while their raw artifact hashes still
preserve the exact run.

## Human-facing artifacts

- `presentation.html`: responsive static meeting page with no external assets;
- `architecture.svg`: accessible system/trust-boundary visual;
- `demo-report.md`: repository-friendly narrative and D1 fallback status;
- component M4 and M8 JSON/CSV/Markdown/HTML reports; and
- the M7 scheduler/evaluator JSON record.

The report intentionally contains no policy-performance chart because no real
policy experiment was run. Plotting synthetic arm success as research evidence
would weaken the claim boundary.

## Manifest and verification

`artifact-manifest.json` lists every curated artifact using an output-relative
path, role, raw-file SHA-256, and byte count. It excludes runtime Git objects,
worktrees, caches, and itself. Paths are traversal-checked, symlinks are
rejected, duplicates are rejected, and every file is re-read after manifest
creation.

Every curated text artifact also normalizes machine-local repository, bundle,
source, interpreter, and optional D1 roots to logical identifiers. Acceptance
tests scan the manifest-selected artifacts to prevent local-path disclosure.

```bash
python3 scripts/verify_m9_bundle.py /tmp/enpire-m9-ludvig-demo
```

Any deletion, replacement, byte change, size mismatch, path escape, or manifest
schema change fails verification.

## Acceptance boundary

M9 is accepted when a clean checkout can produce and verify the full bundle in
one command; repeated runs have the same semantic fingerprint; unavailable D1
has an honest fallback; strict D1 mode blocks before component work; the stable
commit remains unchanged; and all repository regressions pass.
