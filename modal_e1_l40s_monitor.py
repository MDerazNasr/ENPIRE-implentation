"""Checkpoint-free status client for a detached E1 Modal FunctionCall."""

from __future__ import annotations

import json

import modal


app = modal.App("enpire-g0-e1-l40s-monitor-v1")


@app.local_entrypoint()
def main(function_call_id: str, wait: bool = False):
    if not function_call_id.startswith("fc-"):
        raise ValueError("--function-call-id must be a Modal fc-* identity")
    call = modal.FunctionCall.from_id(function_call_id)
    try:
        result = call.get(timeout=None if wait else 0)
    except TimeoutError:
        result = {
            "function_call_id": function_call_id,
            "status": "running",
        }
    print(json.dumps(result, indent=2, sort_keys=True))
