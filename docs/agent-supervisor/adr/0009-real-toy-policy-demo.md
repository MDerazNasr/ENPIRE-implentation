# ADR 0009: Add a Real Toy Policy Without Weakening the RLT Claim Boundary

Status: accepted on 2026-08-04.

## Decision

Add a dependency-free CPU residual-policy task as a separate meeting demo. Run
its recorded config proposal through the existing proposal enforcement, Git
candidate manager, subprocess worker, `TrialEvidence`, D1 evaluator, and
artifact-integrity boundaries.

Label every public artifact as real toy-task evidence and explicitly forbid an
RLinf/RLT, π0.5, ManiSkill, robot, or live-provider inference.

## Why

M9 proves the control plane with fixtures but does not visually demonstrate a
model learning. A tiny real policy makes the loop understandable today without
waiting for D1 or pretending that toy evidence is robotics evidence.

## Rejected alternatives

- Re-label M9 fixture scores as model improvement: false and rejected.
- Rush an incomplete D1 run: unreliable and scientifically misleading.
- Depend on Gym, PyTorch, a GPU, network, or live Claude call: unnecessary
  presentation failure modes.
- Use only a hard-coded before/after score: would not train a real model.

## Consequences

The demo can prove real local model improvement and supervisor composition. It
adds no evidence about the target RLT system, and the recorded proposal must
always be disclosed as non-live.
