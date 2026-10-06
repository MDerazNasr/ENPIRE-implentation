# Research meeting transcript record — 2026-09-02

This record preserves the substantive content of the user-supplied meeting
transcript. Greetings, travel, weather, connection checks, and repeated speech
have been omitted; unclear automatic-transcription terms are normalized only
where the intended technical meaning is evident.

## Project update

- The work was split into a coding-agent/control layer and the reproducible
  baseline/improvement layer. The coding-agent layer is largely implemented
  and its parallel-task behavior has passed its tests, but the full integrated
  behavior still needs a live demonstration.
- The first baseline was trained for too few steps (roughly 250). During a move
  to a larger GPU, the old instance was terminated before all weights were
  preserved, forcing a proper retraining run. The discussion suggested judging
  training duration from dataset size and learning behavior rather than using
  500 or 1,000 steps as an arbitrary stopping point; for roughly 400 episodes,
  a substantially longer run may be warranted.
- A10-class GPUs with 24 GB VRAM were adequate for much of the lighter work.
  RTX 6000 was used to accelerate current training, while full VLA/OpenVLA
  fine-tuning may require an A100/H100-class device with much more memory.

## Agreed system shape

- One supervisor agent can manage multiple independent GPU trials. It should
  test several optimization hypotheses or hyperparameters in parallel and use
  their measured outcomes to choose the next generation of experiments.
- Each training trial normally needs its own adequately sized GPU; packing
  several large training jobs onto one GPU is likely to cause memory contention.
  One agent controlling three GPUs is sufficient for simple hyperparameter
  search; more subagents are justified only by genuinely complex investigations.
- Waiting should be exposed as a tool or scheduling choice, not a single fixed
  interval. The controller should select a bounded wait based on the run and
  hardware, then inspect progress rather than repeatedly interrupt training.
- Start close to the ENPIRE baseline. Avoid prematurely adding specialized
  analysis tools: a strong model can often infer useful conclusions from clean
  data, while narrow tools may overfit one optimization class. Let the coding
  agent build a tool only when an observed need justifies it.

## Evaluation and experiment-selection decision

- Agent self-reports are not trusted as performance evidence. Evaluation must
  live in a protected, immutable area that the agent cannot edit, and it must
  automatically record ground-truth results.
- The primary robotic metric is repeated-task success rate (for example, cup
  pickup success across fixed trials). Secondary metrics may include smoothness,
  spillage/retention, rollout cost, and learning speed.
- Treat optimization as a branching/evolutionary search: run several candidate
  branches from the same parent, evaluate every branch with the same frozen
  benchmark, programmatically select the highest valid score, and spawn the
  next candidates only from that winner. The agent proposes changes; hard-coded
  infrastructure evaluates and promotes them.
- Keep an immutable performance history and a visible branch/tree record so a
  temporarily discovered improvement cannot disappear when agent context is
  lost. Each result should bind metrics to the exact code branch/checkpoint.

## Immediate next work

1. Finish the baseline training and run an end-to-end demonstration of the
   existing coding-agent and improvement loop.
2. Build the protected evaluator, immutable metric store, and branch lineage
   view; verify that candidates cannot modify evaluation inputs or scoring.
3. Run parallel candidate trials, select winners programmatically, and analyze
   which changes caused measured improvement before expanding the method.

## Research practice

Use AI to accelerate implementation, then interrogate the produced solution:
ask how and why each component works and compare it against the papers. Retain
human ownership of the design choices and convert agent discoveries into
durable notes, because useful reasoning otherwise disappears with context.

