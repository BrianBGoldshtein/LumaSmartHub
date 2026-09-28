#!/usr/bin/env bash
# Build a GPL-3.0 wvkbd 0.15 derivative with one documented kiosk-layer change.
set -euo pipefail
KEYBOARD_ARCHIVE=${1:?Path to verified wvkbd_0.15.orig.tar.xz}
KEYBOARD_DEST=${2:?Destination directory for luma-keyboard}
KEYBOARD_SOURCE_DEST=${3:?Destination for corresponding source and licenses}
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
KEYBOARD_SHA=0b82a6497a1d886599d10695732dc3e4fac27eb8ca5d6469c27bd27b6c00e6f5
printf '%s  %s\n' "${KEYBOARD_SHA}" "${KEYBOARD_ARCHIVE}" | sha256sum -c -
KEYBOARD_WORK=$(mktemp -d /tmp/luma-wvkbd.XXXXXXXX)
tar -xJf "${KEYBOARD_ARCHIVE}" --strip-components=1 -C "${KEYBOARD_WORK}"
patch --batch --fuzz=0 -d "${KEYBOARD_WORK}" -p1 < "${SCRIPT_DIR}/wvkbd-overlay.patch"
make -C "${KEYBOARD_WORK}" -j2
install -d "${KEYBOARD_DEST}" "${KEYBOARD_SOURCE_DEST}"
install -m 0755 "${KEYBOARD_WORK}/wvkbd-mobintl" "${KEYBOARD_DEST}/luma-keyboard"
# Ship complete corresponding source, the exact modification, recipe and notices.
install -m 0644 "${KEYBOARD_ARCHIVE}" "${KEYBOARD_SOURCE_DEST}/wvkbd_0.15.orig.tar.xz"
install -m 0644 "${SCRIPT_DIR}/wvkbd-overlay.patch" "${SCRIPT_DIR}/build-keyboard.sh" "${KEYBOARD_SOURCE_DEST}/"
install -m 0644 "${KEYBOARD_WORK}/COPYING" "${KEYBOARD_WORK}/COPYING_WESTON" "${KEYBOARD_WORK}/LICENSE" "${KEYBOARD_SOURCE_DEST}/"
echo "Built fullscreen-compatible keyboard; temporary build retained at ${KEYBOARD_WORK}"
