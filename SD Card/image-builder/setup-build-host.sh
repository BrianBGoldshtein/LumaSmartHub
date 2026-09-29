#!/usr/bin/env bash
set -euo pipefail
[[ ${EUID} -eq 0 ]] || { echo "Run this host-preparation script as Linux root." >&2; exit 1; }
SOURCE_ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
BUILD_USER=luma-build
BUILD_HOME=/home/luma-build
REF=dbd775d191a2e2cafec95bb218f2002213eff2ff
apt-get update
QEMU_PACKAGE=qemu-user-static
# Ubuntu 26.04 provides the registered user-mode emulators under this package;
# Debian and older Ubuntu releases continue to use qemu-user-static.
if ! apt-cache show "${QEMU_PACKAGE}" 2>/dev/null | grep -q '^Version:'; then
  QEMU_PACKAGE=qemu-user-binfmt
fi
DEBIAN_FRONTEND=noninteractive apt-get install -y git rsync xz-utils "${QEMU_PACKAGE}" binfmt-support debian-archive-keyring python3-venv device-tree-compiler unzip curl
if ! id "${BUILD_USER}" >/dev/null 2>&1; then
  useradd --create-home --shell /bin/bash "${BUILD_USER}"
fi
install -d -o "${BUILD_USER}" -g "${BUILD_USER}" "${BUILD_HOME}/luma" "${BUILD_HOME}/tools"
install -d -m 0700 -o "${BUILD_USER}" -g "${BUILD_USER}" "${BUILD_HOME}/keys"
if [[ ! -f "${BUILD_HOME}/keys/luma-pi-admin" ]]; then
  runuser -u "${BUILD_USER}" -- ssh-keygen -q -t ed25519 -N '' -C luma-pi-owner -f "${BUILD_HOME}/keys/luma-pi-admin"
fi
rsync -a --exclude .venv --exclude node_modules --exclude __pycache__ --exclude .pytest_cache --exclude work --exclude image --exclude '*.local' --exclude '.env*' "${SOURCE_ROOT}/" "${BUILD_HOME}/luma/"
chown -R "${BUILD_USER}:${BUILD_USER}" "${BUILD_HOME}/luma"
install -m 0644 "${BUILD_HOME}/keys/luma-pi-admin.pub" "${BUILD_HOME}/luma/source/system/luma-admin.pub"
if [[ ! -d "${BUILD_HOME}/tools/rpi-image-gen/.git" ]]; then
  runuser -u "${BUILD_USER}" -- git clone https://github.com/raspberrypi/rpi-image-gen.git "${BUILD_HOME}/tools/rpi-image-gen"
fi
runuser -u "${BUILD_USER}" -- git -C "${BUILD_HOME}/tools/rpi-image-gen" checkout --detach "${REF}"
DEBIAN_FRONTEND=noninteractive bash "${BUILD_HOME}/tools/rpi-image-gen/install_deps.sh"
loginctl enable-linger "${BUILD_USER}"
echo "Build host prepared. Application workspace: ${BUILD_HOME}/luma"
