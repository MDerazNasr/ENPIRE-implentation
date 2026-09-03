# M6 Code-Enabled Objective Contract

Status: synthetic implementation complete; E0 froze the exact live RLinf seam
and attachment design. E1 implementation and PyTorch equivalence remain open.

M6 adds genuine training-code proposals without granting an agent general
repository or RLinf editing authority. The only editable code surface is the
project-owned actor-objective plugin.

## Versioned ABI

Contract: `m6-actor-objective-v1`

```python
def combine_actor_objective(actor_loss, bc_loss, bc_weight):
    ...
```

The module may contain one docstring, direct module-scope `import math` or
`import torch` statements, and exactly this function. It may not use
from-import aliases; define helpers, classes, decorators, or defaults; accept
variable arguments; or use global/nonlocal state, Python control flow, context
managers, async code, or arbitrary calls. Calls are limited to a short
pure-math/tensor allowlist.

The default remains:

```python
return actor_loss + bc_weight * bc_loss
```

Canonical RLinf, the VLA, critic, replay, rollout, simulator, evaluator,
orchestration, budgets, and reporting remain immutable.

## Mandatory candidate proof

Every code candidate receives a non-agent-selectable
`m6-objective-contract` check in addition to its requested trusted checks. The
check runs in a separate bounded Python process with bytecode writing disabled.
It verifies:

- exact module structure and function signature;
- successful import and execution;
- finite forward values;
- preserved gradients for actor loss, BC loss, and BC weight;
- a measurable difference from the frozen default in at least one approved
  forward value or gradient.

A comment-only, formatting-only, dead-code, or algebraically equivalent patch
therefore fails as a no-op. Runtime exceptions, disconnected gradients, and
non-finite output also fail preparation.

The local validator uses dependency-free differentiable dual scalars. The same
script and ABI are ready for a PyTorch/RLinf compatibility probe, but this
machine does not have PyTorch installed and M6 does not pretend otherwise.

## Git and execution provenance

M3 still applies the patch in an exact-incumbent hypothesis worktree, reruns
static checks before and after trusted commands, commits only the declared
plugin, and proves stable `HEAD` did not move.

For an executable code trial, M6 binds these additional plan fields:

- objective path;
- SHA-256 of exact objective source;
- objective contract version;
- logical command entries containing the same contract and source hash.

The fixture launcher independently revalidates the hash and behavior, writes
the objective validation record into the D1-shaped manifest, and the evidence
normalizer requires exact agreement. The objective source becomes a separately
hashed `actor-objective` evidence artifact.

## Live compatibility boundary

The code-enabled fixture path is executable now. Non-fixture objective plans
continue to fail with an explicit compatibility-handoff error until E1 and E2
implement and bind the E0 design. Pinned RLinf has no native external objective
hook; E0 selected a fail-closed, project-owned `sitecustomize` overlay of
`RLTACLossMixin.forward_actor` without changing this v1 ABI.

E0 determined and recorded:

- the exact actor-loss combination site;
- actual PyTorch tensor shapes, reductions, dtype, device, and autograd graph;
- how the harness-owned adapter is invoked without editing canonical RLinf;
- the manifest field proving which objective was loaded.

The frozen details, upstream hashes, tensor ABI, and required runtime marker are
in `e0-live-objective-seam.md` and ADR 0010. E1/E2 may not silently weaken the
ABI, source hash, mandatory validation, or immutable RLinf boundary.
