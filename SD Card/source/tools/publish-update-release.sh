#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash "SD Card/source/tools/publish-update-release.sh" \
    --notes-file /path/to/release-notes.md [--key /offline/path/key.pem] \
    [--output /path/to/luma-update-X.Y.Z.lup] [--publish]

Without --publish this builds and signs a local .lup only. Publishing additionally
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
PUBLISH=0

while (($#)); do
  case "$1" in
    --key) (($# >= 2)) || { usage >&2; exit 2; }; KEY_PATH="$2"; shift 2 ;;
    --notes-file) (($# >= 2)) || { usage >&2; exit 2; }; NOTES_FILE="$2"; shift 2 ;;
    --output) (($# >= 2)) || { usage >&2; exit 2; }; OUTPUT="$2"; shift 2 ;;
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
[[ "${BRANCH}" == "main" ]] || die "signing releases is allowed only from main after the hardware gate"
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
python3 -c 'import sys; a=tuple(map(int,sys.argv[1].split("."))); b=tuple(map(int,sys.argv[2].split("."))); raise SystemExit(a <= b)' \
  "${VERSION}" "${BASE_VERSION}" || die "the update must be newer than the last full-image version ${BASE_VERSION}"
TAG="v${VERSION}"
ASSET="luma-update-${VERSION}.lup"
[[ -n "${OUTPUT}" ]] || OUTPUT="/home/luma-build/${ASSET}"
[[ "$(basename -- "${OUTPUT}")" == "${ASSET}" ]] || die "output filename must be ${ASSET}"
OUTPUT="$(realpath -m -- "${OUTPUT}")"
case "${OUTPUT}" in "${REPO_ROOT}"|"${REPO_ROOT}"/*) die "keep signed archives outside the repository" ;; esac
[[ ! -e "${OUTPUT}" && ! -L "${OUTPUT}" ]] || die "output already exists; choose a new path"

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
  pnpm install --frozen-lockfile
  pnpm test
  pnpm run build
)

printf 'Running the complete backend suite…\n'
(cd -- "${DELIVERY_ROOT}/source/backend" && python3 -m pytest -q)

if ((PUBLISH)); then
  git -C "${REPO_ROOT}" fetch --quiet origin main
  [[ "$(git -C "${REPO_ROOT}" rev-parse refs/remotes/origin/main)" == "${HEAD_SHA}" ]] || die "main advanced while tests were running; nothing will be published"
  printf 'Tests passed. This will publish %s from accepted main commit %s.\n' "${TAG}" "${HEAD_SHA}"
  printf 'Type "publish %s" to continue: ' "${TAG}"
  read -r CONFIRMATION
  [[ "${CONFIRMATION}" == "publish ${TAG}" ]] || die "confirmation did not match; nothing was published"
fi

printf 'Signing locally with the key held outside GitHub Actions and the repository…\n'
python3 "${DELIVERY_ROOT}/source/tools/build-update-bundle.py" "${DELIVERY_ROOT}" \
  --key "${KEY_PATH}" --output "${OUTPUT}"

if ((PUBLISH)); then
  git -C "${REPO_ROOT}" tag -a "${TAG}" "${HEAD_SHA}" -m "Luma ${VERSION}"
  if ! git -C "${REPO_ROOT}" push origin "refs/tags/${TAG}"; then
    git -C "${REPO_ROOT}" tag -d "${TAG}" >/dev/null
    die "could not publish the exact tested tag; main or the remote tag changed"
  fi
  if ! gh release create "${TAG}" "${OUTPUT}" --repo "${REPOSITORY}" --target main \
    --verify-tag \
    --title "Luma ${VERSION}" --notes-file "${NOTES_FILE}"
  then
    printf 'The tested tag %s is on GitHub at %s; the release upload did not finish.\n' "${TAG}" "${HEAD_SHA}" >&2
    printf 'Recover by creating the release for this same tag and attaching %s; do not reuse its version.\n' "${OUTPUT}" >&2
    exit 1
  fi
  printf 'Published %s. The private signing key was not sent to GitHub.\n' "${TAG}"
else
  printf 'Built signed bundle only (not published): %s\n' "${OUTPUT}"
fi
