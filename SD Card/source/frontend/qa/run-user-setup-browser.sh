#!/usr/bin/env bash
set -euo pipefail
qaRoot=$(cd "$(dirname "$0")" && pwd)
frontendRoot=$(cd "$qaRoot/.." && pwd)
backendRoot=${USER_QA_BACKEND:-$(cd "$frontendRoot/../backend" && pwd)}
pythonRuntime=${1:?Pass the qualified Linux Python executable}
if ss -ltn | grep -Eq ':(18833|19228)\b'; then
  echo 'QA ports occupied; no processes were touched.' >&2
  exit 1
fi
qaDirectory=$(mktemp -d /tmp/luma-031-user-setup.XXXXXXXX)
export USER_QA_DATA="$qaDirectory/data" USER_QA_FRONTEND="$frontendRoot/dist" PYTHONPATH="$backendRoot/src" USER_QA_OUTPUT="$qaDirectory"
cd "$qaRoot"
"$pythonRuntime" -m uvicorn user-setup-server:app --host 127.0.0.1 --port 18833 --no-access-log > "$qaDirectory/server.log" 2>&1 &
qaServer=$!
chromium --headless --no-sandbox --disable-gpu --no-proxy-server --user-data-dir="$qaDirectory/chromium" --remote-debugging-port=19228 about:blank > "$qaDirectory/chromium.log" 2>&1 &
qaBrowser=$!
trap 'kill "$qaServer" "$qaBrowser" 2>/dev/null || true' EXIT
for attempt in $(seq 1 60); do
  if curl -sf http://127.0.0.1:19228/json/version > /dev/null && curl -sf http://127.0.0.1:18833/api/v1/health > /dev/null; then break; fi
  sleep .25
done
if ! node user-setup-browser.mjs > "$qaDirectory/result.json" 2> "$qaDirectory/test-error.txt"; then
  tail -n 30 "$qaDirectory/test-error.txt"
  tail -n 30 "$qaDirectory/server.log"
  printf 'QA directory: %s\n' "$qaDirectory"
  exit 1
fi
cat "$qaDirectory/result.json"
printf 'QA directory: %s\n' "$qaDirectory"
