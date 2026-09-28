#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
ASSETS=${LUMA_ASSETS_DIR:-$(realpath -m "${SCRIPT_DIR}/../source/assets")}
CACHE=${LUMA_ASSET_CACHE:-"${SCRIPT_DIR}/.cache"}
OVERLAY_REF=d8370e5919f809e0f91afa2a2349535714676385
MODEL=vosk-model-small-en-us-0.15
MODEL_SHA=30f26242c4eb449f948e42cb302dd7a686cb29a3423a8367f99ff41780942498
KEYBOARD_SHA=0b82a6497a1d886599d10695732dc3e4fac27eb8ca5d6469c27bd27b6c00e6f5
TAILSCALE_VERSION=1.102.4
TAILSCALE_SHA=9dd1e6a592a014bbaea0103167ffe299adeda4ba14e078ce9c2895364f6c4c3f
TAILSCALE_LICENSE_SHA=a7ca6186a7963a0a60740f6047760eecd7a0234e8c38bd7e1e0bbcb324bda45b
command -v dtc >/dev/null
command -v unzip >/dev/null
install -d "${ASSETS}/overlays" "${ASSETS}/models" "${ASSETS}/licenses" "${ASSETS}/keyboard" "${ASSETS}/tailscale" "${CACHE}"
TAILSCALE_ARCHIVE="tailscale_${TAILSCALE_VERSION}_arm64.tgz"
if [[ ! -f "${CACHE}/${TAILSCALE_ARCHIVE}" ]]; then
  curl --fail --location --retry 3 "https://pkgs.tailscale.com/stable/${TAILSCALE_ARCHIVE}" -o "${CACHE}/${TAILSCALE_ARCHIVE}.partial"
  mv "${CACHE}/${TAILSCALE_ARCHIVE}.partial" "${CACHE}/${TAILSCALE_ARCHIVE}"
fi
printf '%s  %s\n' "${TAILSCALE_SHA}" "${CACHE}/${TAILSCALE_ARCHIVE}" | sha256sum -c -
install -m 0644 "${CACHE}/${TAILSCALE_ARCHIVE}" "${ASSETS}/tailscale/"
curl --fail --location --retry 3 "https://raw.githubusercontent.com/tailscale/tailscale/v${TAILSCALE_VERSION}/LICENSE" -o "${CACHE}/TAILSCALE-LICENSE.txt"
printf '%s  %s\n' "${TAILSCALE_LICENSE_SHA}" "${CACHE}/TAILSCALE-LICENSE.txt" | sha256sum -c -
install -m 0644 "${CACHE}/TAILSCALE-LICENSE.txt" "${ASSETS}/licenses/"
if [[ ! -f "${CACHE}/wvkbd_0.15.orig.tar.xz" ]]; then
  curl --fail --location --retry 3 https://deb.debian.org/debian/pool/main/w/wvkbd/wvkbd_0.15.orig.tar.xz -o "${CACHE}/wvkbd_0.15.orig.tar.xz.partial"
  mv "${CACHE}/wvkbd_0.15.orig.tar.xz.partial" "${CACHE}/wvkbd_0.15.orig.tar.xz"
fi
printf '%s  %s\n' "${KEYBOARD_SHA}" "${CACHE}/wvkbd_0.15.orig.tar.xz" | sha256sum -c -
install -m 0644 "${CACHE}/wvkbd_0.15.orig.tar.xz" "${ASSETS}/keyboard/"
if [[ ! -d "${CACHE}/seeed/.git" ]]; then
  git clone https://github.com/Seeed-Studio/seeed-linux-dtoverlays.git "${CACHE}/seeed"
fi
git -C "${CACHE}/seeed" checkout --detach "${OVERLAY_REF}"
[[ $(git -C "${CACHE}/seeed" rev-parse HEAD) == "${OVERLAY_REF}" ]]
make -C "${CACHE}/seeed" overlays/rpi/respeaker-2mic-v1_0-overlay.dtbo
install -m 0644 "${CACHE}/seeed/overlays/rpi/respeaker-2mic-v1_0-overlay.dtbo" "${ASSETS}/overlays/respeaker-2mic-v1_0.dtbo"
install -m 0644 "${CACHE}/seeed/overlays/rpi/respeaker-2mic-v1_0-overlay.dts" "${ASSETS}/overlays/respeaker-2mic-v1_0.dts"
if [[ ! -f "${CACHE}/${MODEL}.zip" ]]; then
  curl --fail --location --retry 3 "https://alphacephei.com/vosk/models/${MODEL}.zip" -o "${CACHE}/${MODEL}.zip.partial"
  mv "${CACHE}/${MODEL}.zip.partial" "${CACHE}/${MODEL}.zip"
fi
printf '%s  %s\n' "${MODEL_SHA}" "${CACHE}/${MODEL}.zip" | sha256sum -c -
if [[ ! -d "${ASSETS}/models/vosk/am" ]]; then
  unzip -q -o "${CACHE}/${MODEL}.zip" -d "${CACHE}"
  cp -a "${CACHE}/${MODEL}" "${ASSETS}/models/vosk"
fi
curl --fail --location --retry 3 https://www.apache.org/licenses/LICENSE-2.0.txt -o "${ASSETS}/licenses/VOSK-APACHE-2.0.txt"
printf 'overlay_commit=%s\nmodel=%s\nmodel_archive_sha256=%s\nkeyboard_archive_sha256=%s\n' "${OVERLAY_REF}" "${MODEL}" "${MODEL_SHA}" "${KEYBOARD_SHA}" > "${ASSETS}/manifest.txt"
printf 'tailscale_version=%s\ntailscale_arm64_sha256=%s\n' "${TAILSCALE_VERSION}" "${TAILSCALE_SHA}" >> "${ASSETS}/manifest.txt"
echo "Pinned overlay and offline English model prepared."
