#!/usr/bin/env bash
set -euo pipefail
SOURCE=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../source/backend" && pwd)
QA_ROOT=${LUMA_QA_ROOT:-/home/luma-build/qualification}
install -d "${QA_ROOT}/backend"
rsync -a --exclude .venv --exclude __pycache__ --exclude .pytest_cache "${SOURCE}/" "${QA_ROOT}/backend/"
[[ -x "${QA_ROOT}/venv/bin/python" ]] || python3 -m venv "${QA_ROOT}/venv"
"${QA_ROOT}/venv/bin/pip" install "${QA_ROOT}/backend[test,voice]"
cd "${QA_ROOT}/backend"
"${QA_ROOT}/venv/bin/python" -m pytest -q
