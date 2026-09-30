#!/usr/bin/env bash
# Recover only compression after a completed, checked raw-image build.
# Operator must first confirm the old builder/compressor is no longer running.
set -euo pipefail
STAGE=$(realpath "${1:?Pass the immutable completed Linux staging directory}")
RAW="${STAGE}/image-builder/work/output/image-luma-pi4/luma-pi4.img"
IMAGE_DIR="${STAGE}/image"
CANDIDATE="${IMAGE_DIR}/luma-pi4-UNVERIFIED.img.xz"
PARTIAL="${CANDIDATE}.recovery.partial"
[[ $(uname -s) == Linux && -s "${RAW}" && -f "${IMAGE_DIR}/source-manifest.json" ]] || { echo 'Completed raw image and original source manifest required.' >&2; exit 1; }
[[ ! -e "${CANDIDATE}" && ! -e "${PARTIAL}" && ! -e "${CANDIDATE}.sha256" && ! -e "${IMAGE_DIR}/build-manifest.txt" ]] || { echo 'Recovery/final output already exists; refusing to overwrite.' >&2; exit 1; }
EXPECTED=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_sha256"])' "${IMAGE_DIR}/source-manifest.json")
[[ ${EXPECTED} =~ ^[a-f0-9]{64}$ ]] || exit 1
SOURCE_SHA=$(python3 "${STAGE}/image-builder/source-manifest.py" "${STAGE}")
[[ ${SOURCE_SHA} == "${EXPECTED}" ]] || { echo 'Staged inputs differ from the original manifest.' >&2; exit 1; }
GENERATOR=$(git -C "${STAGE}/image-builder/work/rpi-image-gen" rev-parse HEAD)
[[ ${GENERATOR} == dbd775d191a2e2cafec95bb218f2002213eff2ff ]] || { echo 'Unexpected generator revision.' >&2; exit 1; }
RAW_SHA=$(sha256sum "${RAW}")
RAW_SHA=${RAW_SHA%% *}
# noclobber makes concurrent recovery attempts fail before overwriting output.
# Preserve the original interrupted .partial file for the diagnostic record.
set -o noclobber
xz -T2 -6 -c "${RAW}" > "${PARTIAL}"
xz -t "${PARTIAL}"
[[ $(python3 "${STAGE}/image-builder/source-manifest.py" "${STAGE}") == "${EXPECTED}" ]] || { echo 'Inputs changed during compression.' >&2; exit 1; }
AFTER_SHA=$(sha256sum "${RAW}")
[[ ${AFTER_SHA%% *} == "${RAW_SHA}" ]] || { echo 'Raw image changed during compression.' >&2; exit 1; }
# Exact generated output only, no recursive operations or replacement.
mv -T -n -- "${PARTIAL}" "${CANDIDATE}"
[[ ! -e "${PARTIAL}" ]] || { echo 'Final path appeared concurrently; recovery retained.' >&2; exit 1; }
(
  cd "${IMAGE_DIR}"
  sha256sum luma-pi4-UNVERIFIED.img.xz > luma-pi4-UNVERIFIED.img.xz.sha256
  printf 'generator_commit=%s\nbuilt_utc=%s\nsource_sha256=%s\nraw_image_sha256=%s\ncompression_recovered=true\nboot_verified=false\n' \
    "${GENERATOR}" "$(date -u +%FT%TZ)" "${EXPECTED}" "${RAW_SHA}" > build-manifest.txt
)
echo 'Compression recovered and XZ integrity checked. Hardware qualification is still required.'
