#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${RLINF_HOME:-}" ]]; then
  echo "error: RLINF_HOME must point to the RLinf checkout" >&2
  exit 2
fi
if [[ -z "${MODEL_PATH:-}" ]]; then
  echo "error: MODEL_PATH must point to the pi0.5/RLT feature model" >&2
  exit 2
fi
if [[ -z "${DATASET_PATH:-}" ]]; then
  echo "error: DATASET_PATH must contain norm_stats.json" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RESULTS_ROOT="${RESULTS_ROOT:-${REPO_ROOT}/results}"
SESSION_ID="${SESSION_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
PYTHON_BIN="${PYTHON_BIN:-${RLINF_HOME}/.venv/bin/python}"

cd "${REPO_ROOT}"
exec "${PYTHON_BIN}" -m agent.policy_improvement \
  --config configs/phase1_overrides.yaml \
  --results-root "${RESULTS_ROOT}" \
  --session-id "${SESSION_ID}"
