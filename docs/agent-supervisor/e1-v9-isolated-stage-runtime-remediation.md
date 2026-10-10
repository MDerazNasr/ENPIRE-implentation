# E1 v9 Isolated Stage-Runtime Remediation

Status: offline implementation; **non-authorizing**

## Failure addressed

Stage v2 packaged `supervisor/`, but importing
`supervisor.e1_staged_checkpoint` necessarily executed
`supervisor/__init__.py`. That initializer eagerly imports the coordinator,
which imports `agent.d1_rules`; the intentionally minimal CPU staging image did
not contain `agent/`. Modal therefore failed during function hydration with
`ModuleNotFoundError: agent` before the function body, S3, or volume access.

## Corrected boundary

Stage v3 imports a top-level `e1_staged_checkpoint_runtime.py` containing only
Python-standard-library receipt, hashing, and bounded-error helpers. The image
copies that single file and no longer imports `supervisor` or `agent`. An
isolated-Python regression test imports the runtime with repository paths
disabled. Stage v3 uses a new app, role-session name, checkpoint path, and
receipt path. Evaluator v9 consumes only the corresponding verified artifact.

All scientific identities and shard boundaries remain unchanged. This document
does not authorize a stage-v3 launch or any GPU evaluation. Fresh explicit
authorization is required after the correction and its receipt are committed,
tested, and pushed.
