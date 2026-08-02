#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 CONFIG RUN_ID [--execute --acknowledge-paid-run]" >&2
  exit 2
fi

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="$1"
RUN_ID="$2"
shift 2

cd "${REPO_ROOT}"
exec python3 -m agent.d1_launcher \
  --config "${CONFIG}" \
  --run-id "${RUN_ID}" \
  "$@"

