# ADR 0010: Freeze the Live RLT Objective Attachment

- Status: accepted
- Date: 2026-09-03

## Context

ADR 0003 selected a project-owned objective overlay before the exact D1 worker
was available. Pinned RLinf now exposes the concrete integration seam only as a
hard-coded expression inside `RLTACLossMixin.forward_actor`; it still has no
external objective hook. The existing M6 plugin ABI accepts the already
weighted actor term, BC loss, and BC weight.

## Decision

Retain `m6-actor-objective-v1`. Attach it through an explicit, fail-closed
`sitecustomize` installer that patches only the pinned mixin method at runtime.
The harness-owned replacement preserves the frozen method plumbing and changes
the combination line to invoke the adapter with
`actor_loss=-q_weight * qf_pi.mean()`.

Before installation, verify the RLinf commit and exact worker/config source
hashes. Emit and persist the plugin, adapter, seam, upstream, and installed-
target identities. Apply the same inherited mixin implementation to synchronous
and asynchronous RLT workers. Never edit the RLinf checkout.

## Consequences

- The default v1 plugin can be directly equivalent to pinned upstream.
- One narrow runtime patch is reviewable and opt-in, while canonical RLinf
  stays byte-for-byte pinned.
- The adapter must duplicate the frozen `forward_actor` plumbing, so every
  upstream change requires a new hash, compatibility review, and seam version.
- Source validation alone is insufficient; E1 must prove PyTorch forward and
  gradient equivalence, and E2 must reconcile runtime installation proof with
  the launcher manifest.

## Alternatives rejected

- Modify or commit a patch to the RLinf checkout: violates the immutable
  upstream boundary.
- Shadow the complete upstream worker module: duplicates substantially more
  worker and replay infrastructure than the one required method.
- Change the v1 plugin to accept Q tensors and both weights: unnecessary for
  the frozen expression and would invalidate completed M6 provenance.
- Rewrite upstream source text during import: smaller in line count but opaque,
  harder to test, and less reviewable than an explicit adapter method.
