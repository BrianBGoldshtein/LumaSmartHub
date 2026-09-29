#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
DELIVERY_ROOT=$(cd -- "${SCRIPT_DIR}/.." && pwd)
WORK_ROOT=${LUMA_BUILD_ROOT:-"${SCRIPT_DIR}/work"}
GENERATOR_REF=dbd775d191a2e2cafec95bb218f2002213eff2ff

if [[ $(uname -s) != Linux || ${EUID} -eq 0 ]]; then
  echo "Run as a normal user on Linux with rpi-image-gen dependencies installed." >&2
  exit 1
fi

command -v git >/dev/null
command -v xz >/dev/null
command -v sha256sum >/dev/null
command -v rsync >/dev/null
command -v python3 >/dev/null
[[ -f "${DELIVERY_ROOT}/source/frontend/dist/index.html" ]] || { echo "Build the frontend first." >&2; exit 1; }
APP_VERSION=$(python3 -c 'import pathlib,sys,tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text())["project"]["version"])' "${DELIVERY_ROOT}/source/backend/pyproject.toml")
BASE_VERSION=$(tr -d '[:space:]' < "${DELIVERY_ROOT}/source/tools/update-base-version.txt")
[[ "${APP_VERSION}" == "${BASE_VERSION}" ]] || { echo "Update base-version.txt to the application version included in this full image." >&2; exit 1; }
bash "${SCRIPT_DIR}/prepare-assets.sh"
install -d "${DELIVERY_ROOT}/image"
CANDIDATE="${DELIVERY_ROOT}/image/luma-pi4-UNVERIFIED.img.xz"
[[ ! -e "${CANDIDATE}" && ! -e "${CANDIDATE}.partial" ]] || { echo "Candidate exists; use fresh staging." >&2; exit 1; }
SOURCE_SHA=$(python3 "${SCRIPT_DIR}/source-manifest.py" "${DELIVERY_ROOT}" --output "${DELIVERY_ROOT}/image/source-manifest.json")

if [[ ! -d "${WORK_ROOT}/rpi-image-gen/.git" ]]; then
  install -d "${WORK_ROOT}"
  git clone https://github.com/raspberrypi/rpi-image-gen.git "${WORK_ROOT}/rpi-image-gen"
fi

git -C "${WORK_ROOT}/rpi-image-gen" fetch origin "${GENERATOR_REF}"
git -C "${WORK_ROOT}/rpi-image-gen" checkout --detach "${GENERATOR_REF}"

[[ $(git -C "${WORK_ROOT}/rpi-image-gen" rev-parse HEAD) == "${GENERATOR_REF}" ]]
chmod +x "${SCRIPT_DIR}/hooks/customize90-luma"
install -d "${WORK_ROOT}/output"
"${WORK_ROOT}/rpi-image-gen/rpi-image-gen" build -S "${SCRIPT_DIR}" -c "${SCRIPT_DIR}/luma.yaml" -B "${WORK_ROOT}/output"
RAW_IMAGE="${WORK_ROOT}/output/image-luma-pi4/luma-pi4.img"
[[ -s "${RAW_IMAGE}" ]] || { echo "Expected image was not generated: ${RAW_IMAGE}" >&2; exit 1; }
[[ $(python3 "${SCRIPT_DIR}/source-manifest.py" "${DELIVERY_ROOT}") == "${SOURCE_SHA}" ]] || { echo "Build inputs changed during assembly; do not publish this image." >&2; exit 1; }
xz -T2 -6 -c "${RAW_IMAGE}" > "${CANDIDATE}.partial"
xz -t "${CANDIDATE}.partial"
[[ $(python3 "${SCRIPT_DIR}/source-manifest.py" "${DELIVERY_ROOT}") == "${SOURCE_SHA}" ]] || { echo "Build inputs changed during compression; do not publish this image." >&2; exit 1; }
mv -- "${CANDIDATE}.partial" "${CANDIDATE}"
(cd -- "${DELIVERY_ROOT}/image" && sha256sum "$(basename -- "${CANDIDATE}")") > "${CANDIDATE}.sha256"
printf 'generator_commit=%s\nbuilt_utc=%s\nsource_sha256=%s\nboot_verified=false\n' "${GENERATOR_REF}" "$(date -u +%FT%TZ)" "${SOURCE_SHA}" > "${DELIVERY_ROOT}/image/build-manifest.txt"
echo "Candidate generated. Follow docs/HARDWARE_VALIDATION.md before calling it ready."
