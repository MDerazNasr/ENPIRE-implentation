# E1 v10 Named Stage-Secret Remediation

Status: offline implementation; **non-authorizing**

## Failure addressed

Stage v3 isolated its runtime imports, but its decorator constructed an
ephemeral `Secret.from_dict` through a helper that read local environment
variables. Modal re-imported the module while hydrating the remote function,
before those values were present, so hydration failed before the function body,
S3, or the volume.

## Corrected boundary

Stage v4 references one uniquely named Modal Secret with four required keys.
The wrapper mints the same one-hour verifier-role session, writes its values to
a mode-0600 temporary JSON file, creates the named secret with `--from-json`
while suppressing command output, and deletes the local file in `finally`.
Secret values never enter subprocess arguments or receipt output. The stage
function validates at least 30 minutes of remaining TTL before S3 access.

The named secret is create-only and must be deleted after the detached function
reaches a terminal state; if launch submission fails, the wrapper deletes it
immediately. Stage v4 and evaluator v10 use new create-only artifact identities.
All scientific inputs remain unchanged.

This document authorizes neither secret creation nor cloud execution. A fresh
approval must bind the source, one stage-v4 attempt, the `$1` cap, zero retry,
and mandatory secret cleanup. GPU shards require separate later authority.
