#!/usr/bin/env bash
# Disposable synthetic-phone TLS lab, never the owner's browser or Pi.
set -euo pipefail
qaRoot=$(cd "$(dirname "$0")" && pwd)
frontendRoot=$(cd "$qaRoot/.." && pwd)
backendRoot=$(cd "$frontendRoot/../backend" && pwd)
pythonRuntime=${1:?Pass the qualified Linux Python executable}
if ss -ltn | grep -Eq ':(443|19226)\b'; then
  echo 'QA ports already occupied; no processes were touched.' >&2
  exit 1
fi
qaDirectory=$(mktemp -d "${REMOTE_QA_PARENT:-/tmp}/luma-030-mobile.XXXXXXXX")
openssl req -x509 -newkey rsa:2048 -nodes -keyout "$qaDirectory/key.pem" -out "$qaDirectory/cert.pem" -days 1 -subj '/CN=luma.example-tail.ts.net' > "$qaDirectory/certificate.log" 2>&1
export REMOTE_QA_DATA="$qaDirectory/data" REMOTE_QA_FRONTEND="$frontendRoot/dist" PYTHONPATH="$backendRoot/src"
cd "$qaRoot"
"$pythonRuntime" -m uvicorn remote-server:app --host 127.0.0.1 --port 443 --ssl-keyfile "$qaDirectory/key.pem" --ssl-certfile "$qaDirectory/cert.pem" --no-access-log > "$qaDirectory/server.log" 2>&1 &
qaServer=$!
chromium --headless --no-sandbox --disable-gpu --no-proxy-server --ignore-certificate-errors --host-resolver-rules='MAP luma.example-tail.ts.net 127.0.0.1' --user-data-dir="$qaDirectory/chromium" --remote-debugging-port=19226 about:blank > "$qaDirectory/chromium.log" 2>&1 &
qaBrowser=$!
trap 'kill "$qaServer" "$qaBrowser" 2>/dev/null || true' EXIT
for attempt in $(seq 1 60); do
  if curl -sf http://127.0.0.1:19226/json/version > /dev/null && curl -k -sf --noproxy '*' --resolve luma.example-tail.ts.net:443:127.0.0.1 https://luma.example-tail.ts.net/remote/ > /dev/null; then break; fi
  sleep .25
done
export REMOTE_QA_OUTPUT="$qaDirectory"
if ! node remote-browser.mjs > "$qaDirectory/result.json" 2> "$qaDirectory/test-error.txt"; then
  tail -n 30 "$qaDirectory/test-error.txt"
  tail -n 30 "$qaDirectory/server.log"
  printf 'QA directory: %s\n' "$qaDirectory"
  exit 1
fi
cat "$qaDirectory/result.json"
printf 'QA directory: %s\n' "$qaDirectory"
