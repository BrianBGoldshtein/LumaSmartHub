#!/usr/bin/env bash
# Resume the stopped r2 candidate: its interruption preceded filesystem assembly.
set -euo pipefail
STAGE=/home/luma-build/luma-commissioning-20260927-r2
WORK="$STAGE/image-builder/work"
[[ $(id -un) == luma-build ]] || exit 1
[[ ! -e "$WORK/output/image-luma-pi4/luma-pi4.img" ]] || { echo 'Raw image already exists; inspect it instead.' >&2; exit 1; }
[[ $(git -C "$WORK/rpi-image-gen" rev-parse HEAD) == dbd775d191a2e2cafec95bb218f2002213eff2ff ]] || exit 1
EXPECTED=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source_sha256"])' "$STAGE/image/source-manifest.json")
[[ $(python3 "$STAGE/image-builder/source-manifest.py" "$STAGE") == "$EXPECTED" ]] || { echo 'Inputs changed.' >&2; exit 1; }
"$WORK/rpi-image-gen/rpi-image-gen" build -S "$STAGE/image-builder" -c "$STAGE/image-builder/luma.yaml" -B "$WORK/output"
[[ $(python3 "$STAGE/image-builder/source-manifest.py" "$STAGE") == "$EXPECTED" ]] || exit 1
bash "$STAGE/image-builder/finish-candidate.sh" "$STAGE"
