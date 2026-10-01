#!/usr/bin/env bash
# One-shot, signed 0.2.5 application test from the Pi's FAT BOOT partition.
# This runs only after the owner physically arms the card. It leaves persistent
# settings under /var/lib/luma alone and restores cmdline before installation.
set -euo pipefail

BOOT=/boot/firmware
ORIGINAL="$BOOT/cmdline.luma-v025-original.txt"
CMDLINE="$BOOT/cmdline.txt"
BUNDLE="$BOOT/luma-update-0.2.5.lup"
SCRIPT="$BOOT/luma-v025-run.sh"
RESULT="$BOOT/luma-v025-result.log"
[[ $(id -u) -eq 0 ]] || exit 1
exec >"$RESULT" 2>&1
on_exit() {
  local code=$?
  printf 'Luma 0.2.5 supervised update exit status: %s\n' "$code"
  sync -f "$RESULT" || true
}
trap on_exit EXIT
printf 'Luma 0.2.5 supervised update started\n'

for file in "$ORIGINAL" "$CMDLINE" "$BOOT/luma-v025-cmdline.sha256"; do
  [[ -f "$file" && ! -L "$file" ]] || {
    printf 'Required BOOT file is missing or unsafe: %s\n' "$file"
    exit 1
  }
done
[[ $(sha256sum "$ORIGINAL" | cut -d' ' -f1) == "$(tr -d '\r\n' < "$BOOT/luma-v025-cmdline.sha256")" ]] || {
  printf 'Original boot command-line checksum mismatch; no change made.\n'
  exit 1
}
grep -Fq 'systemd.run=' "$CMDLINE" || {
  printf 'This card was not armed; no change made.\n'
  exit 1
}

# Ensure every later boot is normal, including after a power loss or failed
# health check. An error here aborts before the application is touched.
cp -- "$ORIGINAL" "$CMDLINE"
sync -f "$CMDLINE"
cmp -s "$ORIGINAL" "$CMDLINE" || {
  printf 'Normal boot command line could not be restored; update aborted.\n'
  exit 1
}
printf 'Normal boot command line restored.\n'

for file in "$BUNDLE" "$SCRIPT" "$BOOT/luma-v025-bundle.sha256"; do
  [[ -f "$file" && ! -L "$file" ]] || {
    printf 'The update payload is missing or unsafe; normal boot was restored and no update was attempted: %s\n' "$file"
    exit 1
  }
done

api_ok() {
  local expected=$1
  local body
  body=$(/usr/bin/curl --fail --silent --max-time 2 http://127.0.0.1:8742/api/v1/health) || return 1
  /usr/bin/python3 -c 'import json,sys; data=json.load(sys.stdin); sys.exit(not (data.get("status")=="ok" and data.get("database")=="ok" and data.get("version")==sys.argv[1]))' "$expected" <<<"$body" 2>/dev/null
}
ready=0
for _ in $(seq 1 120); do
  if api_ok 0.2.4; then
    ready=1
    break
  fi
  sleep 2
done
[[ $ready -eq 1 ]] || {
  printf 'Healthy Luma 0.2.4 was not found within four minutes; update aborted.\n'
  exit 1
}
printf 'Current 0.2.4 API and database are healthy.\n'
[[ $(sha256sum "$BUNDLE" | cut -d' ' -f1) == "$(tr -d '\r\n' < "$BOOT/luma-v025-bundle.sha256")" ]] || {
  printf 'Bundle transfer checksum mismatch; update aborted.\n'
  exit 1
}
/opt/luma/venv/bin/luma-update verify "$BUNDLE"
printf 'Signed 0.2.5 bundle verified; applying.\n'
/opt/luma/venv/bin/luma-update apply "$BUNDLE"
for _ in $(seq 1 30); do
  if api_ok 0.2.5; then
    printf 'SUCCESS: Luma 0.2.5 API and database are healthy.\n'
    exit 0
  fi
  sleep 2
done
printf 'The installer returned, but the 0.2.5 API check failed. Inspect the Luma software page and report this log.\n'
exit 1
