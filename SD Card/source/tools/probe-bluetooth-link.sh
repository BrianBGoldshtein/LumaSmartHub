#!/usr/bin/env bash
# Passive controller-wide HCI evidence. Never persist/emit the raw stream.
# Only fixed event/role labels and two-digit status/reason bytes reach stdout.
# This is not a selected-phone trace; correlate with its D-Bus evidence before
# attributing a controller event to the owner's iPhone.
set -u
filter() {
    LC_ALL=C awk '
/^[[:space:]]*[<>@=]/ {capture=0}
/HCI Event: Disconnect Complete/ {capture=1; print "Disconnect event"}
/HCI Event: Encryption Change/ {capture=1; print "Encryption event"}
/^[[:space:]]+LE (Enhanced )?Connection Complete/ {capture=1; print "LE link event"}
capture && /^[[:space:]]+(Status|Reason):/ {
    if (match($0, /\(0x[0-9a-fA-F][0-9a-fA-F]\)/)) print $1, substr($0,RSTART,RLENGTH)
}
capture && /^[[:space:]]+Role: Central/ {print "Pi role: Central"}
capture && /^[[:space:]]+Role: Peripheral/ {print "Pi role: Peripheral"}
'
}
if [[ "${1:-}" == --filter-only ]]; then
    filter
    exit
fi
if (( EUID != 0 )); then
    printf '%s\n' 'Run as root to observe Bluetooth controller events.' >&2
    exit 1
fi
timeout 45s btmon | filter
