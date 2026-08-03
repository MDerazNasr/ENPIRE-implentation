#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 6 ]]; then
  echo "usage: $0 LAUNCHER_PID MANIFEST SOURCE_WEIGHTS DEST_WEIGHTS RECLAIM_WEIGHTS LOG" >&2
  exit 2
fi

launcher_pid="$1"
manifest="$2"
source_weights="$3"
dest_weights="$4"
reclaim_weights="$5"
log="$6"

while kill -0 "${launcher_pid}" 2>/dev/null; do
  sleep 30
done

if ! grep -q '"status": "complete"' "${manifest}" || \
   ! grep -q '"exit_code": 0' "${manifest}"; then
  echo "training did not complete cleanly; persistent actor left unchanged" >>"${log}"
  exit 1
fi

source_size="$(stat -c %s "${source_weights}")"
if (( source_size < 9000000000 )); then
  echo "source actor is unexpectedly small (${source_size}); persistent actor left unchanged" >>"${log}"
  exit 1
fi

source_sha="$(sha256sum "${source_weights}" | awk '{print $1}')"
mkdir -p "$(dirname "${dest_weights}")"
rm -f "${reclaim_weights}" "${dest_weights}" "${dest_weights}.partial"
cp "${source_weights}" "${dest_weights}.partial"
sync

dest_size="$(stat -c %s "${dest_weights}.partial")"
dest_sha="$(sha256sum "${dest_weights}.partial" | awk '{print $1}')"
if [[ "${source_size}" != "${dest_size}" || "${source_sha}" != "${dest_sha}" ]]; then
  echo "persistent copy verification failed; source remains in RAM" >>"${log}"
  exit 1
fi

mv "${dest_weights}.partial" "${dest_weights}"
printf 'preserved size=%s sha256=%s path=%s\n' \
  "${dest_size}" "${dest_sha}" "${dest_weights}" >>"${log}"
