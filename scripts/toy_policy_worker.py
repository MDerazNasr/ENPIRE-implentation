#!/usr/bin/env python3
"""Run one real CPU residual-policy training/evaluation worker."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from supervisor.toy_policy import (  # noqa: E402
    TrainingConfig,
    evaluate_policy,
    make_resets,
    train_policy,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--evaluation-seed", type=int, required=True)
    parser.add_argument("--evaluation-episodes", type=int, default=256)
    parser.add_argument("--display-seed", type=int, default=90_900)
    parser.add_argument("--display-episodes", type=int, default=6)
    arguments = parser.parse_args()
    started = time.monotonic()
    try:
        config = TrainingConfig.from_dict(
            json.loads(arguments.config.read_text(encoding="utf-8"))["training"]
        )
        training = train_policy(config, arguments.seed)
        evaluation, _ = evaluate_policy(
            training.policy,
            make_resets(arguments.evaluation_seed, arguments.evaluation_episodes),
        )
        _, display = evaluate_policy(
            training.policy,
            make_resets(arguments.display_seed, arguments.display_episodes),
        )
    except (OSError, KeyError, ValueError, json.JSONDecodeError) as error:
        print(f"toy worker failed: {error}", file=sys.stderr)
        return 2
    payload = {
        "status": "complete",
        "seed": arguments.seed,
        "training": training.to_dict(),
        "evaluation": evaluation.to_dict(),
        "display_episodes": [episode.to_dict() for episode in display],
        "elapsed_seconds": round(time.monotonic() - started, 6),
        "external_calls": [],
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
