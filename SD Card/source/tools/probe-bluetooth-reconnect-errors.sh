#!/usr/bin/env bash
# Passive, daemon-wide fallback when the correlated Python probe is not on the Pi.
# Emits only timestamps, fixed method/error names and known LE reason codes.
# No raw monitor output is saved; unrelated device errors cannot be attributed
# to the selected iPhone without the correlated Python probe.
set -u
filter() {
    LC_ALL=C sed -n -E '
s/^method call time=([0-9.]+).*member=(Connect|Disconnect)([;[:space:]].*)?$/\1 \2/p
s/^error time=([0-9.]+).*error_name=org\.bluez\.Error\.(InProgress|Failed|NotReady|AlreadyConnected|NotConnected|NotAvailable|NotSupported|InvalidArguments|AuthenticationFailed|AuthenticationRejected|AuthenticationTimeout|ConnectionAttemptFailed)([;[:space:]].*)?$/\1 \2/p
s/^[[:space:]]+string "(le-connection-(invalid-arguments|adapter-not-powered|not-supported|already-connected|bad-socket|memory-allocation|busy|refused|create-socket|timeout|concurrent-connection-limit|abort-by-remote|abort-by-local|link-layer-protocol-error|gatt-browsing|key-missing|unknown))"$/\1/p
'
}
if [[ "${1:-}" == --filter-only ]]; then
    filter
    exit
fi
if (( EUID != 0 )); then
    printf '%s\n' 'Run as root to observe the system bus.' >&2
    exit 1
fi
timeout 45s dbus-monitor --system \
    "type='error',sender='org.bluez'" \
    "type='method_call',destination='org.bluez',interface='org.bluez.Device1',member='Connect'" \
    "type='method_call',destination='org.bluez',interface='org.bluez.Device1',member='Disconnect'" | filter
