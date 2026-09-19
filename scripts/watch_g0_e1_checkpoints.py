#!/usr/bin/env python3
"""Upload completed E1 grid checkpoints while the approved container runs."""

from __future__ import annotations

import argparse
import json
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


STEPS = (250, 500, 1000, 2000)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def container_running(name: str) -> bool:
    process = subprocess.run(
        ["sudo", "docker", "inspect", "-f", "{{.State.Running}}", name],
        check=False,
        capture_output=True,
        text=True,
    )
    return process.returncode == 0 and process.stdout.strip() == "true"


def find_checkpoint(root: Path, step: int) -> Path | None:
    matches = sorted(path for path in root.rglob(f"global_step_{step}") if path.is_dir())
    if len(matches) > 1:
        raise RuntimeError(f"multiple global_step_{step} checkpoint directories found")
    return matches[0] if matches else None


def append_event(path: Path, event: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, sort_keys=True, separators=(",", ":")) + "\n")
        handle.flush()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--container-name", required=True)
    parser.add_argument("--uploader", type=Path, required=True)
    parser.add_argument("--bucket", required=True)
    parser.add_argument("--campaign-prefix", required=True)
    parser.add_argument("--profile", required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--poll-seconds", type=float, default=60)
    parser.add_argument("--max-total-bytes", type=int, default=350 * 1024**3)
    args = parser.parse_args(argv)

    event_path = args.evidence_dir / "checkpoint-watcher.jsonl"
    append_event(event_path, {"at": utc_now(), "type": "watcher_started"})
    uploaded: set[int] = set()
    while True:
        running = container_running(args.container_name)
        discovered = {step: find_checkpoint(args.run_root, step) for step in STEPS}
        for index, step in enumerate(STEPS):
            if step in uploaded or discovered[step] is None:
                continue
            next_ready = index + 1 < len(STEPS) and discovered[STEPS[index + 1]] is not None
            final_ready = step == STEPS[-1] and not running
            if not next_ready and not final_ready:
                continue
            manifest = args.evidence_dir / f"global_step_{step}-upload-manifest.json"
            command = [
                "python3",
                str(args.uploader),
                "--checkpoint-dir",
                str(discovered[step]),
                "--step",
                str(step),
                "--bucket",
                args.bucket,
                "--campaign-prefix",
                args.campaign_prefix,
                "--profile",
                args.profile,
                "--manifest-out",
                str(manifest),
                "--max-total-bytes",
                str(args.max_total_bytes),
                "--execute",
                "--acknowledge-retained-upload",
            ]
            append_event(event_path, {"at": utc_now(), "step": step, "type": "upload_started"})
            process = subprocess.run(command, check=False)
            if process.returncode:
                append_event(
                    event_path,
                    {"at": utc_now(), "exit_code": process.returncode, "step": step, "type": "upload_failed"},
                )
                return process.returncode
            uploaded.add(step)
            append_event(event_path, {"at": utc_now(), "step": step, "type": "upload_complete"})

        if not running:
            missing = sorted(set(STEPS) - uploaded)
            status = "complete" if not missing else "container_stopped_with_missing_checkpoints"
            append_event(
                event_path,
                {"at": utc_now(), "missing_steps": missing, "type": status},
            )
            return 0 if not missing else 1
        time.sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
