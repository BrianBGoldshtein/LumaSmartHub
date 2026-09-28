#!/usr/bin/env bash
# Fresh commissioning snapshot only; never accesses a physical disk.
set -euo pipefail
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
STAGE=/home/luma-build/luma-commissioning-20260927
[[ $(id -un) == luma-build && ! -e "$STAGE" ]] || { echo 'Requires build user and a fresh staging path.' >&2; exit 1; }
mkdir "$STAGE"
mkdir "$STAGE/source" "$STAGE/image-builder"
for part in backend frontend system assets tests; do
  rsync -a --exclude .venv --exclude node_modules --exclude __pycache__ --exclude .pytest_cache --exclude '*.local' --exclude '.env*' "$SOURCE/source/$part/" "$STAGE/source/$part/"
done
rsync -a --exclude work --exclude .cache --exclude __pycache__ "$SOURCE/image-builder/" "$STAGE/image-builder/"
# Copy only the owner-approved PUBLIC recovery key.
install -m 0644 /home/luma-build/keys/luma-pi-admin.pub "$STAGE/source/system/luma-admin.pub"
mkdir "$STAGE/image-builder/.cache"
rsync -a /home/luma-build/luma-tailscale-20260926/image-builder/.cache/ "$STAGE/image-builder/.cache/"
echo "Staged $STAGE; no image built and no card accessed."
