#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash "SD Card/source/tools/publish-update-release.sh" \
    --notes-file /path/to/release-notes.md [--key /offline/path/key.pem] \
    [--output /path/to/luma-update-X.Y.Z.lup] \
    [--voice-assets-dir /path/to/pinned-voice-files] \
    [--voice-output /path/to/luma-voice-kristin-X.Y.Z.lva] \
    [--keyword-assets-dir /path/to/pinned-keyword-files] \
    [--keyword-output /path/to/luma-keyword-X.Y.Z.lka] \
    [--keyword-arm64-root /path/to/isolated-arm64-root] [--publish]

Without --publish this builds signed local assets without uploading them. Publishing additionally
requires the exact main commit to be clean, current, and green in GitHub Actions,
then asks for a typed confirmation before creating a stable GitHub Release.
EOF
}

die() { printf 'Release blocked: %s\n' "$*" >&2; exit 1; }

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
DELIVERY_ROOT="$(cd -- "${SCRIPT_DIR}/../.." && pwd -P)"
REPO_ROOT="$(git -C "${DELIVERY_ROOT}" rev-parse --show-toplevel)"
REPOSITORY="BrianBGoldshtein/LumaSmartHub"
KEY_PATH="/home/luma-build/keys/luma-update-ed25519.pem"
NOTES_FILE=""
OUTPUT=""
VOICE_ASSETS_DIR=""
VOICE_OUTPUT=""
KEYWORD_ASSETS_DIR=""
KEYWORD_OUTPUT=""
KEYWORD_ARM64_ROOT=""
PUBLISH=0

while (($#)); do
  case "$1" in
    --key) (($# >= 2)) || { usage >&2; exit 2; }; KEY_PATH="$2"; shift 2 ;;
    --notes-file) (($# >= 2)) || { usage >&2; exit 2; }; NOTES_FILE="$2"; shift 2 ;;
    --output) (($# >= 2)) || { usage >&2; exit 2; }; OUTPUT="$2"; shift 2 ;;
    --voice-assets-dir) (($# >= 2)) || { usage >&2; exit 2; }; VOICE_ASSETS_DIR="$2"; shift 2 ;;
    --voice-output) (($# >= 2)) || { usage >&2; exit 2; }; VOICE_OUTPUT="$2"; shift 2 ;;
    --keyword-assets-dir) (($# >= 2)) || { usage >&2; exit 2; }; KEYWORD_ASSETS_DIR="$2"; shift 2 ;;
    --keyword-output) (($# >= 2)) || { usage >&2; exit 2; }; KEYWORD_OUTPUT="$2"; shift 2 ;;
    --keyword-arm64-root) (($# >= 2)) || { usage >&2; exit 2; }; KEYWORD_ARM64_ROOT="$2"; shift 2 ;;
    --publish) PUBLISH=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 2 ;;
  esac
done

[[ -n "${NOTES_FILE}" ]] || die "provide a concise release-notes file"
[[ -f "${NOTES_FILE}" && ! -L "${NOTES_FILE}" ]] || die "release notes must be a regular file"
[[ -s "${NOTES_FILE}" ]] || die "release notes must not be empty"
NOTES_FILE="$(realpath -- "${NOTES_FILE}")"
case "${NOTES_FILE}" in "${REPO_ROOT}"/*) die "keep release notes outside the repository" ;; esac

BRANCH="$(git -C "${REPO_ROOT}" branch --show-current)"
[[ "${BRANCH}" == "main" ]] || die "signing releases is allowed only from main"
[[ -z "$(git -C "${REPO_ROOT}" status --porcelain --untracked-files=all)" ]] || die "the main checkout must be clean"
git -C "${REPO_ROOT}" fetch --quiet origin main --tags
HEAD_SHA="$(git -C "${REPO_ROOT}" rev-parse HEAD)"
MAIN_SHA="$(git -C "${REPO_ROOT}" rev-parse refs/remotes/origin/main)"
[[ "${HEAD_SHA}" == "${MAIN_SHA}" ]] || die "local main must exactly match origin/main before signing"

VERSION="$(python3 -c 'import pathlib,sys,tomllib; print(tomllib.loads(pathlib.Path(sys.argv[1]).read_text(encoding="utf-8"))["project"]["version"])' \
  "${DELIVERY_ROOT}/source/backend/pyproject.toml")"
[[ "${VERSION}" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || die "the package version must be stable X.Y.Z"
BASE_VERSION="$(tr -d '[:space:]' < "${DELIVERY_ROOT}/source/tools/update-base-version.txt")"
[[ "${BASE_VERSION}" =~ ^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] || die "the image's recorded base version is invalid"
QUALIFY_FROM="${BASE_VERSION}"
if [[ "${VERSION}" == "0.2.4" ]]; then
  # The owner's live card received 0.2.3 through boot-partition recovery,
  # even though the last full-image base version remains 0.2.0.
  QUALIFY_FROM="0.2.3"
elif [[ "${VERSION}" == "0.2.5" ]]; then
  # The owner's installed beta is 0.2.4; qualify the next switch from it.
  QUALIFY_FROM="0.2.4"
elif [[ "${VERSION}" == "0.2.6" ]]; then
  # The owner's installed beta is 0.2.5; exercise that exact upgrade path.
  QUALIFY_FROM="0.2.5"
elif [[ "${VERSION}" == "0.2.7" ]]; then
  # Exercise the next beta against the 0.2.6 app release, not the old image.
  QUALIFY_FROM="0.2.6"
elif [[ "${VERSION}" == "0.2.8" ]]; then
  QUALIFY_FROM="0.2.7"
elif [[ "${VERSION}" == "0.2.9" ]]; then
  QUALIFY_FROM="0.2.8"
elif [[ "${VERSION}" == "0.2.10" ]]; then
  QUALIFY_FROM="0.2.9"
elif [[ "${VERSION}" == "0.2.11" ]]; then
  QUALIFY_FROM="0.2.10"
elif [[ "${VERSION}" == "0.3.0" ]]; then
  QUALIFY_FROM="0.2.11"
elif [[ "${VERSION}" == "0.3.1" ]]; then
  QUALIFY_FROM="0.3.0"
elif [[ "${VERSION}" == "0.3.2" ]]; then
  QUALIFY_FROM="0.3.1"
elif [[ "${VERSION}" == "0.3.3" ]]; then
  QUALIFY_FROM="0.3.2"
elif [[ "${VERSION}" == "0.3.4" ]]; then
  QUALIFY_FROM="0.3.3"
elif [[ "${VERSION}" == "0.3.5" ]]; then
  QUALIFY_FROM="0.3.4"
fi
python3 -c 'import sys; a=tuple(map(int,sys.argv[1].split("."))); b=tuple(map(int,sys.argv[2].split("."))); raise SystemExit(a <= b)' \
  "${VERSION}" "${BASE_VERSION}" || die "the update must be newer than the last full-image version ${BASE_VERSION}"
TAG="v${VERSION}"
ASSET="luma-update-${VERSION}.lup"
[[ -n "${OUTPUT}" ]] || OUTPUT="/home/luma-build/${ASSET}"
[[ "$(basename -- "${OUTPUT}")" == "${ASSET}" ]] || die "output filename must be ${ASSET}"
OUTPUT="$(realpath -m -- "${OUTPUT}")"
case "${OUTPUT}" in "${REPO_ROOT}"|"${REPO_ROOT}"/*) die "keep signed archives outside the repository" ;; esac
[[ ! -e "${OUTPUT}" && ! -L "${OUTPUT}" ]] || die "output already exists; choose a new path"
if [[ "${VERSION}" == "0.2.4" && -z "${VOICE_ASSETS_DIR}" ]]; then
  die "0.2.4 requires its separately signed offline voice asset"
fi
if [[ "${VERSION}" == "0.2.9" && -z "${KEYWORD_ASSETS_DIR}" ]]; then
  die "0.2.9 requires its separately signed acoustic wake asset"
fi
if [[ -n "${KEYWORD_ASSETS_DIR}" ]]; then
  [[ -d "${KEYWORD_ASSETS_DIR}" && ! -L "${KEYWORD_ASSETS_DIR}" ]] || die "keyword source directory is missing or linked"
  [[ -d "${KEYWORD_ARM64_ROOT}" && ! -L "${KEYWORD_ARM64_ROOT}" ]] || die "keyword publishing requires the isolated ARM64 qualification root"
  KEYWORD_ASSETS_DIR="$(realpath -- "${KEYWORD_ASSETS_DIR}")"
  KEYWORD_ARM64_ROOT="$(realpath -- "${KEYWORD_ARM64_ROOT}")"
  KEYWORD_VERSION="$(PYTHONPATH="${DELIVERY_ROOT}/source/backend/src" python3 -c 'from luma.keyword_asset import ASSET_VERSION; print(ASSET_VERSION)')"
  [[ "${KEYWORD_VERSION}" == "${VERSION}" ]] || die "the keyword sidecar must match the source-pinned asset release version"
  [[ -n "${KEYWORD_OUTPUT}" ]] || KEYWORD_OUTPUT="/home/luma-build/luma-keyword-${VERSION}.lka"
  [[ "$(basename -- "${KEYWORD_OUTPUT}")" == "luma-keyword-${VERSION}.lka" ]] || die "keyword output filename must match the release version"
  KEYWORD_OUTPUT="$(realpath -m -- "${KEYWORD_OUTPUT}")"
  case "${KEYWORD_OUTPUT}" in "${REPO_ROOT}"|"${REPO_ROOT}"/*) die "keep signed keyword archives outside the repository" ;; esac
  [[ ! -e "${KEYWORD_OUTPUT}" && ! -L "${KEYWORD_OUTPUT}" ]] || die "keyword output already exists; choose a new path"
elif [[ -n "${KEYWORD_OUTPUT}" || -n "${KEYWORD_ARM64_ROOT}" ]]; then
  die "keyword output/qualification options require keyword sources"
fi
if [[ -n "${VOICE_ASSETS_DIR}" ]]; then
  [[ -d "${VOICE_ASSETS_DIR}" && ! -L "${VOICE_ASSETS_DIR}" ]] || die "voice source directory is missing or linked"
  VOICE_ASSETS_DIR="$(realpath -- "${VOICE_ASSETS_DIR}")"
  [[ -n "${VOICE_OUTPUT}" ]] || VOICE_OUTPUT="/home/luma-build/luma-voice-kristin-${VERSION}.lva"
  [[ "$(basename -- "${VOICE_OUTPUT}")" == "luma-voice-kristin-${VERSION}.lva" ]] || die "voice output filename must match the release version"
  VOICE_OUTPUT="$(realpath -m -- "${VOICE_OUTPUT}")"
  case "${VOICE_OUTPUT}" in "${REPO_ROOT}"|"${REPO_ROOT}"/*) die "keep signed voice archives outside the repository" ;; esac
  [[ ! -e "${VOICE_OUTPUT}" && ! -L "${VOICE_OUTPUT}" ]] || die "voice output already exists; choose a new path"
fi

if ((PUBLISH)); then
  command -v gh >/dev/null || die "GitHub CLI (gh) is required to publish"
  gh auth status --hostname github.com >/dev/null || die "authenticate gh with release-write access first"
  gh repo view "${REPOSITORY}" --json nameWithOwner --jq .nameWithOwner | grep -Fxq "${REPOSITORY}" || die "the configured GitHub repository did not match"
  CI_STATE="$(gh run list --repo "${REPOSITORY}" --workflow "Luma software checks" \
    --branch main --commit "${HEAD_SHA}" --limit 100 \
    --json databaseId,status,conclusion,headSha,createdAt | python3 -c '
import json,sys
sha=sys.argv[1]
runs=[run for run in json.load(sys.stdin) if run.get("headSha")==sha]
if not runs: print("missing")
else:
    latest=max(runs,key=lambda run:run.get("createdAt", ""))
    print("success" if latest.get("status")=="completed" and latest.get("conclusion")=="success" else "not-green")
' "${HEAD_SHA}")"
  [[ "${CI_STATE}" == "success" ]] || die "the latest Luma software-check run for ${HEAD_SHA} is not green"
  TAG_STATE="$(git -C "${REPO_ROOT}" ls-remote --tags --refs origin 'refs/tags/v*' | python3 -c '
import re,sys
versions=[]
for line in sys.stdin:
    match=re.fullmatch(r"[0-9a-f]+\s+refs/tags/v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)",line.strip())
    if match: versions.append(tuple(map(int,match.groups())))
candidate=tuple(map(int,sys.argv[1].split(".")))
print("new" if not versions or candidate>max(versions) else "old")
' "${VERSION}")"
  [[ "${TAG_STATE}" == "new" ]] || die "${VERSION} must be newer than every existing version tag"
  if git -C "${REPO_ROOT}" show-ref --verify --quiet "refs/tags/${TAG}"; then
    die "local tag ${TAG} already exists; versions are never reused"
  fi
  if gh release view "${TAG}" --repo "${REPOSITORY}" >/dev/null 2>&1; then
    die "release ${TAG} already exists; versions are never reused"
  fi
fi

printf 'Running frontend tests and production build for %s…\n' "${TAG}"
(
  cd -- "${DELIVERY_ROOT}/source/frontend"
  # Keep pnpm's content store on the Linux build filesystem. WSL can otherwise
  # choose a Windows-backed store and create incomplete cross-filesystem links.
  CI=true pnpm install --frozen-lockfile --store-dir "$(dirname -- "${OUTPUT}")/pnpm-store"
  pnpm test
  pnpm run build
)

printf 'Running the complete backend suite…\n'
(cd -- "${DELIVERY_ROOT}/source/backend" && python3 -m pytest -q)
printf 'Running image-builder, recovery and packaging tests…\n'
(cd -- "${REPO_ROOT}" && python3 -m pytest -q "SD Card/image-builder")

if ((PUBLISH)); then
  git -C "${REPO_ROOT}" fetch --quiet origin main
  [[ "$(git -C "${REPO_ROOT}" rev-parse refs/remotes/origin/main)" == "${HEAD_SHA}" ]] || die "main advanced while tests were running; nothing will be published"
fi

printf 'Signing locally with the key held outside GitHub Actions and the repository…\n'
python3 "${DELIVERY_ROOT}/source/tools/build-update-bundle.py" "${DELIVERY_ROOT}" \
  --key "${KEY_PATH}" --output "${OUTPUT}"
printf 'Qualifying the exact signed application archive against switch and rollback…\n'
python3 "${DELIVERY_ROOT}/source/tools/qualify-update-bundle.py" "${OUTPUT}" \
  --public-key "${DELIVERY_ROOT}/source/system/luma-update-ed25519.pub" \
  --current-version "${QUALIFY_FROM}"
if [[ "${VERSION}" == "0.3.0" ]]; then
  # The first remote install is performed by the already-deployed 0.2.11
  # verifier/installer, not this release's new active-gateway allowlist.
  LEGACY_SHA="68ca52aea57997fef83f8ea7368751c43f989963"
  [[ "$(git -C "${REPO_ROOT}" rev-parse 'refs/tags/v0.2.11^{}')" == "${LEGACY_SHA}" ]] || die "the accepted 0.2.11 tag changed"
  LEGACY_ROOT="$(mktemp -d "$(dirname -- "${OUTPUT}")/luma-legacy-0211.XXXXXXXX")"
  git -C "${REPO_ROOT}" archive "${LEGACY_SHA}" -- \
    "SD Card/source/backend/pyproject.toml" \
    "SD Card/source/backend/src/luma/storage.py" \
    "SD Card/source/backend/src/luma/update_agent.py" | tar -x -C "${LEGACY_ROOT}"
  printf 'Qualifying the same signed archive with the accepted 0.2.11 verifier/installer…\n'
  python3 "${DELIVERY_ROOT}/source/tools/qualify-update-bundle.py" "${OUTPUT}" \
    --public-key "${DELIVERY_ROOT}/source/system/luma-update-ed25519.pub" \
    --current-version "0.2.11" --legacy-delivery "${LEGACY_ROOT}/SD Card"
elif [[ "${VERSION}" == "0.3.1" ]]; then
  # Multi-user rollout must also pass the verifier/installer already running
  # on the owner's 0.3.0 Pi, not merely this candidate's current implementation.
  LEGACY_SHA="99081bb0972d77d03afaf4860b25d7e5cdb514c9"
  [[ "$(git -C "${REPO_ROOT}" rev-parse 'refs/tags/v0.3.0^{}')" == "${LEGACY_SHA}" ]] || die "the accepted 0.3.0 tag changed"
  LEGACY_ROOT="$(mktemp -d "$(dirname -- "${OUTPUT}")/luma-legacy-030.XXXXXXXX")"
  git -C "${REPO_ROOT}" archive "${LEGACY_SHA}" -- \
    "SD Card/source/backend/pyproject.toml" \
    "SD Card/source/backend/src/luma/storage.py" \
    "SD Card/source/backend/src/luma/update_agent.py" | tar -x -C "${LEGACY_ROOT}"
  printf 'Qualifying the same signed archive with the accepted 0.3.0 verifier/installer…\n'
  python3 "${DELIVERY_ROOT}/source/tools/qualify-update-bundle.py" "${OUTPUT}" \
    --public-key "${DELIVERY_ROOT}/source/system/luma-update-ed25519.pub" \
    --current-version "0.3.0" --legacy-delivery "${LEGACY_ROOT}/SD Card"
fi
if [[ "${VERSION}" == "0.3.2" ]]; then
  LEGACY_SHA="9ca2299074d913829a41d601314082ac1fcf5ed1"
  [[ "$(git -C "${REPO_ROOT}" rev-parse 'refs/tags/v0.3.1^{}')" == "${LEGACY_SHA}" ]] || die "the accepted 0.3.1 tag changed"
  LEGACY_ROOT="$(mktemp -d "$(dirname -- "${OUTPUT}")/luma-legacy-031.XXXXXXXX")"
  git -C "${REPO_ROOT}" archive "${LEGACY_SHA}" -- \
    "SD Card/source/backend/pyproject.toml" \
    "SD Card/source/backend/src/luma/storage.py" \
    "SD Card/source/backend/src/luma/update_agent.py" | tar -x -C "${LEGACY_ROOT}"
  printf 'Qualifying the same signed archive with the accepted 0.3.1 verifier/installer…\n'
  python3 "${DELIVERY_ROOT}/source/tools/qualify-update-bundle.py" "${OUTPUT}" \
    --public-key "${DELIVERY_ROOT}/source/system/luma-update-ed25519.pub" \
    --current-version "0.3.1" --legacy-delivery "${LEGACY_ROOT}/SD Card"
fi
RELEASE_ASSETS=("${OUTPUT}")
if [[ "${VERSION}" == "0.3.3" ]]; then
  LEGACY_SHA="383552f5f545551f97e6df26574f770bacdc7b1f"
  [[ "$(git -C "${REPO_ROOT}" rev-parse 'refs/tags/v0.3.2^{}')" == "${LEGACY_SHA}" ]] || die "the published 0.3.2 tag changed"
  LEGACY_ROOT="$(mktemp -d "$(dirname -- "${OUTPUT}")/luma-legacy-032.XXXXXXXX")"
  git -C "${REPO_ROOT}" archive "${LEGACY_SHA}" -- \
    "SD Card/source/backend/pyproject.toml" \
    "SD Card/source/backend/src/luma/storage.py" \
    "SD Card/source/backend/src/luma/update_agent.py" | tar -x -C "${LEGACY_ROOT}"
  printf 'Qualifying the same signed archive with the published 0.3.2 verifier/installer…\n'
  python3 "${DELIVERY_ROOT}/source/tools/qualify-update-bundle.py" "${OUTPUT}" \
    --public-key "${DELIVERY_ROOT}/source/system/luma-update-ed25519.pub" \
    --current-version "0.3.2" --legacy-delivery "${LEGACY_ROOT}/SD Card"
fi
if [[ "${VERSION}" == "0.3.4" ]]; then
  LEGACY_SHA="59174f549adaa38d8674bb9763eb787fd0e1e0f9"
  [[ "$(git -C "${REPO_ROOT}" rev-parse 'refs/tags/v0.3.3^{}')" == "${LEGACY_SHA}" ]] || die "the published 0.3.3 tag changed"
  LEGACY_ROOT="$(mktemp -d "$(dirname -- "${OUTPUT}")/luma-legacy-033.XXXXXXXX")"
  git -C "${REPO_ROOT}" archive "${LEGACY_SHA}" -- \
    "SD Card/source/backend/pyproject.toml" \
    "SD Card/source/backend/src/luma/storage.py" \
    "SD Card/source/backend/src/luma/update_agent.py" | tar -x -C "${LEGACY_ROOT}"
  printf 'Qualifying the same signed archive with the published 0.3.3 verifier/installer…\n'
  python3 "${DELIVERY_ROOT}/source/tools/qualify-update-bundle.py" "${OUTPUT}" \
    --public-key "${DELIVERY_ROOT}/source/system/luma-update-ed25519.pub" \
    --current-version "0.3.3" --legacy-delivery "${LEGACY_ROOT}/SD Card"
fi
if [[ "${VERSION}" == "0.3.5" ]]; then
  LEGACY_SHA="55f9aadd3037f75c8df708a6ecf692dbc7c9f5e0"
  [[ "$(git -C "${REPO_ROOT}" rev-parse 'refs/tags/v0.3.4^{}')" == "${LEGACY_SHA}" ]] || die "the published 0.3.4 tag changed"
  LEGACY_ROOT="$(mktemp -d "$(dirname -- "${OUTPUT}")/luma-legacy-034.XXXXXXXX")"
  git -C "${REPO_ROOT}" archive "${LEGACY_SHA}" -- \
    "SD Card/source/backend/pyproject.toml" \
    "SD Card/source/backend/src/luma/storage.py" \
    "SD Card/source/backend/src/luma/update_agent.py" | tar -x -C "${LEGACY_ROOT}"
  printf 'Qualifying the same signed archive with the published 0.3.4 verifier/installer…\n'
  python3 "${DELIVERY_ROOT}/source/tools/qualify-update-bundle.py" "${OUTPUT}" \
    --public-key "${DELIVERY_ROOT}/source/system/luma-update-ed25519.pub" \
    --current-version "0.3.4" --legacy-delivery "${LEGACY_ROOT}/SD Card"
fi
if [[ -n "${KEYWORD_ASSETS_DIR}" ]]; then
  python3 "${DELIVERY_ROOT}/source/tools/build-keyword-asset.py" "${DELIVERY_ROOT}" \
    --model "${KEYWORD_ASSETS_DIR}/model" --wheels "${KEYWORD_ASSETS_DIR}/wheels" \
    --model-card "${KEYWORD_ASSETS_DIR}/licenses/model-card.txt" \
    --license "${KEYWORD_ASSETS_DIR}/licenses/Apache-2.0.txt" \
    --key "${KEY_PATH}" --output "${KEYWORD_OUTPUT}"
  KEYWORD_LAB_RUN="$(mktemp -d "$(dirname -- "${KEYWORD_OUTPUT}")/luma-keyword-release-check.XXXXXXXX")"
  printf 'Verifying the exact signed keyword payload and isolated ARM64 install…\n'
  python3 "${DELIVERY_ROOT}/source/tools/qualify-keyword-asset.py" \
    --bundle "${KEYWORD_OUTPUT}" --public-key "${DELIVERY_ROOT}/source/system/luma-update-ed25519.pub" \
    --output "${KEYWORD_LAB_RUN}/extracted" > "${KEYWORD_LAB_RUN}/payload-report.json"
  python3 "${DELIVERY_ROOT}/source/tools/qualify-keyword-arm64-install.py" \
    --bundle "${KEYWORD_OUTPUT}" --public-key "${DELIVERY_ROOT}/source/system/luma-update-ed25519.pub" \
    --lab-root "${KEYWORD_ARM64_ROOT}" --output "${KEYWORD_LAB_RUN}/installed" \
    > "${KEYWORD_LAB_RUN}/arm64-report.json"
  printf 'Keyword reports retained in %s (not microphone or Pi acceptance).\n' "${KEYWORD_LAB_RUN}"
  RELEASE_ASSETS+=("${KEYWORD_OUTPUT}")
fi
if [[ -n "${VOICE_ASSETS_DIR}" ]]; then
  python3 "${DELIVERY_ROOT}/source/tools/build-voice-asset.py" "${DELIVERY_ROOT}" \
    --assets "${VOICE_ASSETS_DIR}" --key "${KEY_PATH}" --output "${VOICE_OUTPUT}"
  printf 'Verifying every signed offline voice file against the appliance key…\n'
  PYTHONPATH="${DELIVERY_ROOT}/source/backend/src" python3 - \
    "${VOICE_OUTPUT}" "${DELIVERY_ROOT}/source/system/luma-update-ed25519.pub" <<'PY'
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from luma.voice_asset import verify_and_extract

with TemporaryDirectory(prefix="luma-release-voice-check-") as staging:
    manifest = verify_and_extract(Path(sys.argv[1]), Path(staging), Path(sys.argv[2]))
    print(f"Verified {len(manifest['files'])} voice files for Luma {manifest['version']}.")
PY
  RELEASE_ASSETS+=("${VOICE_OUTPUT}")
fi

if ((PUBLISH)); then
  git -C "${REPO_ROOT}" fetch --quiet origin main
  [[ "$(git -C "${REPO_ROOT}" rev-parse refs/remotes/origin/main)" == "${HEAD_SHA}" ]] || die "main advanced while signing; nothing will be published"
  printf 'Verified assets for %s from accepted main commit %s.\n' "${TAG}" "${HEAD_SHA}"
  sha256sum "${RELEASE_ASSETS[@]}"
  printf 'Type "publish %s" to create the stable GitHub release: ' "${TAG}"
  read -r CONFIRMATION
  [[ "${CONFIRMATION}" == "publish ${TAG}" ]] || die "confirmation did not match; nothing was published"
  git -C "${REPO_ROOT}" tag -a "${TAG}" "${HEAD_SHA}" -m "Luma ${VERSION}"
  if ! git -C "${REPO_ROOT}" push origin "refs/tags/${TAG}"; then
    git -C "${REPO_ROOT}" tag -d "${TAG}" >/dev/null
    die "could not publish the exact tested tag; main or the remote tag changed"
  fi
  if ! gh release create "${TAG}" "${RELEASE_ASSETS[@]}" --repo "${REPOSITORY}" --target main \
    --verify-tag \
    --title "Luma ${VERSION} Beta" --notes-file "${NOTES_FILE}"
  then
    printf 'The tested tag %s is on GitHub at %s; the release upload did not finish.\n' "${TAG}" "${HEAD_SHA}" >&2
    printf 'Recover by creating the release for this same tag and attaching all signed assets; do not reuse its version.\n' >&2
    exit 1
  fi
  printf 'Published %s. The private signing key was not sent to GitHub.\n' "${TAG}"
else
  printf 'Built signed assets only (not published): %s\n' "${RELEASE_ASSETS[*]}"
fi
