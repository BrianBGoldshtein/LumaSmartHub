#!/usr/bin/env bash
# One-shot, physical-SD recovery for the r13 -> r14 application update.
# Invoked only by systemd's kernel-command-line unit. The signed updater,
# not this FAT partition, decides what application code may be installed.
set -euo pipefail
BOOT=/boot/firmware
ORIGINAL="$BOOT/cmdline.luma-r14-original.txt"
CMDLINE="$BOOT/cmdline.txt"
BUNDLE="$BOOT/luma-update-0.2.2.lup"
RESULT="$BOOT/luma-r14-result.log"

[[ $(id -u) -eq 0 ]] || exit 1
exec >"$RESULT" 2>&1
printf 'Luma r14 recovery started\n'
[[ -f "$ORIGINAL" && ! -L "$ORIGINAL" && -f "$CMDLINE" && -f "$BUNDLE" ]] || {
  printf 'Required recovery file missing; no change made.\n'; exit 1;
}
[[ -f "$BOOT/luma-r14-cmdline.sha256" && -f "$BOOT/luma-r14-bundle.sha256" ]] || {
  printf 'Recovery checksum missing; no change made.\n'; exit 1;
}
[[ $(sha256sum "$ORIGINAL" | cut -d' ' -f1) == "$(tr -d '\r\n' < "$BOOT/luma-r14-cmdline.sha256")" ]] || {
  printf 'Original boot command line has changed; no change made.\n'; exit 1;
}
grep -Fq 'systemd.run=' "$CMDLINE" || {
  printf 'Recovery was not armed; no change made.\n'; exit 1;
}

# Make the NEXT boot normal before touching the application. If power fails
# during installation, the signed updater keeps the previous release or its
# atomically selected new one; we never loop a startup installation.
cp -- "$ORIGINAL" "$CMDLINE"
sync -f "$CMDLINE"
cmp -s "$ORIGINAL" "$CMDLINE" || {
  printf 'Could not confirm normal boot command line; update aborted.\n'; exit 1;
}
printf 'Original boot command line restored.\n'

# This unit is started alongside the normal graphical boot. Wait until the
# already-installed application and database are healthy before asking the
# updater to stop/restart its services.
ready=0
for _ in $(seq 1 120); do
  if /usr/bin/curl --fail --silent --max-time 2 http://127.0.0.1:8742/api/v1/health \
      | /usr/bin/grep -Fq '"status":"ok","database":"ok"'; then
    ready=1
    break
  fi
  sleep 2
done
[[ $ready -eq 1 ]] || { printf 'Existing Luma API was not healthy; update aborted.\n'; exit 1; }
printf 'Existing Luma API is healthy.\n'

[[ $(sha256sum "$BUNDLE" | cut -d' ' -f1) == "$(tr -d '\r\n' < "$BOOT/luma-r14-bundle.sha256")" ]] || {
  printf 'Signed bundle checksum mismatch; update aborted.\n'; exit 1;
}
/opt/luma/venv/bin/luma-update verify "$BUNDLE"
/opt/luma/venv/bin/luma-update apply "$BUNDLE"
printf 'Signed update applied; checking running API.\n'
for _ in $(seq 1 30); do
  if /usr/bin/curl --fail --silent --show-error --max-time 2 http://127.0.0.1:8742/api/v1/health \
      | /usr/bin/grep -Fq '"version":"0.2.2"'; then
    printf 'SUCCESS: Luma 0.2.2 is running with a healthy API.\n'
    sync -f "$RESULT"
    exit 0
  fi
  sleep 2
done
printf 'Update returned but API version check did not pass; see Luma software status.\n'
exit 1
