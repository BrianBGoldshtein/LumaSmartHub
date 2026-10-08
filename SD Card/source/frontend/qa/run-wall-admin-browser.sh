#!/usr/bin/env bash
set -euo pipefail
qaRoot=$(cd "$(dirname "$0")" && pwd)
frontendRoot=$(cd "$qaRoot/.." && pwd)
backendRoot=${WALL_QA_BACKEND:-$(cd "$frontendRoot/../backend" && pwd)}
pythonRuntime=${1:?Pass the qualified Linux Python executable}
if ss -ltn | grep -Eq ':(18832|19227)\b'; then
  echo 'QA ports occupied; no processes were touched.' >&2
  exit 1
fi
qaDirectory=$(mktemp -d /tmp/luma-031-wall-admin.XXXXXXXX)
export WALL_QA_DATA="$qaDirectory/data" WALL_QA_FRONTEND="$frontendRoot/dist" PYTHONPATH="$backendRoot/src" WALL_QA_OUTPUT="$qaDirectory"
cd "$qaRoot"
"$pythonRuntime" -m uvicorn wall-admin-server:app --host 127.0.0.1 --port 18832 --no-access-log > "$qaDirectory/server.log" 2>&1 &
qaServer=$!
chromium --headless --no-sandbox --disable-gpu --no-proxy-server --user-data-dir="$qaDirectory/chromium" --remote-debugging-port=19227 about:blank > "$qaDirectory/chromium.log" 2>&1 &
qaBrowser=$!
trap 'kill "$qaServer" "$qaBrowser" 2>/dev/null || true' EXIT
for attempt in $(seq 1 60); do
  if curl -sf http://127.0.0.1:19227/json/version > /dev/null && curl -sf http://127.0.0.1:18832/api/v1/health > /dev/null; then break; fi
  sleep .25
done
if ! node wall-admin-browser.mjs > "$qaDirectory/result.json" 2> "$qaDirectory/test-error.txt"; then
  tail -n 30 "$qaDirectory/test-error.txt"
  tail -n 30 "$qaDirectory/server.log"
  printf 'QA directory: %s\n' "$qaDirectory"
  exit 1
fi
cat "$qaDirectory/result.json"
printf 'QA directory: %s\n' "$qaDirectory"
