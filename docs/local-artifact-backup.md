# Local Artifact Backup Contract

Every irreplaceable weight artifact must be downloaded to Mohamed's local
machine and hash-verified as soon as it becomes usable. A remote checkpoint or
provider volume is not considered preserved.

## Progressive gates

1. After the Stage-1 step-250 actor is complete, download its inference actor
   and verify local size and SHA-256 against the remote source.
2. After the Stage-1 step-500 actor is complete, repeat the local download and
   verification before starting long Stage-2 training.
3. After Control B finishes, download and verify its final policy/checkpoint
   plus compact run evidence before starting Candidate C.
4. After Candidate C finishes, download and verify its final policy/checkpoint
   and compact evidence before applying the final shutdown gate.
5. Before terminating the instance, generate a local `SHA256SUMS` inventory
   covering the Stage-1 actors, both Stage-2 policies, norm stats, resolved
   configs, manifests, cost ledger, and evidence archives.

Failure or interruption of any download blocks the next destructive action.
The paid instance may continue useful independent work, but its workspace must
not be terminated until the corresponding local hash matches.

## What is copied

- Stage-1 step-250 and step-500 inference actors (about 10 GB each);
- final Control-B and Candidate-C policies/checkpoints;
- matching norm statistics;
- resolved configs, commands, manifests, metrics, resource/cost ledgers, and
  compact W&B/raw-log evidence.

The approximately 30 GB Stage-1 distributed optimizer shard, base pi0.5 model,
official dataset, RLinf environment, and caches are reproducible and are not
part of the local backup. They remain on the live workspace only as long as
needed. This keeps the expected local backup within the currently available
disk budget; free space must be checked again before every transfer.

## Transport and verification

Prefer direct TCP SSH with SCP or rsync support. Do not stream binary weights
through RunPod's PTY-only SSH proxy. If direct TCP is unavailable, use a stable
range-resumable HTTP/object-storage route and retain partial downloads for
resume.

For each artifact:

1. record the remote byte size and SHA-256;
2. transfer into a run-specific directory under the local untracked `tmp/`
   backup root;
3. record the local byte size and SHA-256;
4. require exact equality before marking the backup gate complete;
5. list the verified path/hash in Obsidian memory and the experiment evidence.

Stage-2 mid-run checkpoints do not make the pinned RLT schedule safely
resumable because its worker counters are not persisted. The local Control-B
and Candidate-C backups are therefore taken after each uninterrupted run
completes; they preserve results and evaluation, not an unsupported mid-run
resume claim.
