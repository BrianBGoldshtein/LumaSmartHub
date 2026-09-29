"""Fetch and verify the newest published Luma application release from GitHub."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import tempfile
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .update_agent import MAX_BUNDLE_BYTES, PUBLIC_KEY, UpdateError, verify_bundle


OWNER = "BrianBGoldshtein"
REPOSITORY = "LumaSmartHub"
RELEASES_API = f"https://api.github.com/repos/{OWNER}/{REPOSITORY}/releases/latest"
VERSION_RE = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
MAX_METADATA_BYTES = 512 * 1024
MAX_NOTES_CHARS = 4000
REDIRECT_HOSTS = {"github.com", "release-assets.githubusercontent.com",
                  "objects.githubusercontent.com"}


class GitHubUpdateError(ValueError):
    """A fixed, user-safe error while checking the configured public feed."""


class _HTTPSGitHubRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, new_url):
        parsed = urlsplit(new_url)
        if (parsed.scheme != "https" or parsed.hostname not in REDIRECT_HOSTS
                or parsed.username or parsed.password):
            raise HTTPError(request.full_url, code, "Rejected release download redirect", headers, None)
        return super().redirect_request(request, response, code, message, headers, new_url)


def _opener():
    return build_opener(_HTTPSGitHubRedirect())


def _read(opener, url: str, *, limit: int, accept: str) -> bytes:
    request = Request(url, headers={"Accept": accept, "User-Agent": "LumaSmartHub-Updater/1"})
    try:
        with opener.open(request, timeout=12) as response:
            final = urlsplit(response.geturl())
            if final.scheme != "https" or final.hostname not in REDIRECT_HOSTS | {"api.github.com"}:
                raise GitHubUpdateError("GitHub returned an unexpected download address.")
            declared = response.headers.get("Content-Length")
            if declared is not None and (not declared.isdigit() or int(declared) > limit):
                raise GitHubUpdateError("The GitHub release file is too large.")
            data = response.read(limit + 1)
    except GitHubUpdateError:
        raise
    except HTTPError as error:
        if error.code == 404:
            raise GitHubUpdateError("No published Luma update is available yet.") from None
        raise GitHubUpdateError("Could not reach the GitHub update service. Check Wi-Fi sign-in and try again.") from None
    except (OSError, URLError, TimeoutError, ValueError):
        raise GitHubUpdateError("Could not reach the GitHub update service. Check Wi-Fi sign-in and try again.") from None
    if len(data) > limit:
        raise GitHubUpdateError("The GitHub release file is too large.")
    return data


def latest_release(current_version: str, *, public_key_path: Path = PUBLIC_KEY,
                   opener=None) -> dict:
    """Return current status or a verified newer release plus its signed bytes."""
    if not VERSION_RE.fullmatch(current_version):
        raise GitHubUpdateError("The installed Luma version cannot be checked safely.")
    opener = opener or _opener()
    raw = _read(opener, RELEASES_API, limit=MAX_METADATA_BYTES,
                accept="application/vnd.github+json")
    try:
        release = json.loads(raw)
        if not isinstance(release, dict) or release.get("draft") is not False or release.get("prerelease") is not False:
            raise ValueError
        if release.get("target_commitish") != "main":
            raise ValueError
        tag = release.get("tag_name")
        if not isinstance(tag, str) or not re.fullmatch(r"v(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)", tag):
            raise ValueError
        version = tag[1:]
        notes = release.get("body", "")
        if not isinstance(notes, str):
            notes = ""
        assets = release.get("assets")
        if not isinstance(assets, list):
            raise ValueError
        asset_name = f"luma-update-{version}.lup"
        matching = [asset for asset in assets if isinstance(asset, dict) and asset.get("name") == asset_name]
        if len(matching) != 1:
            raise ValueError
        asset = matching[0]
        size = asset.get("size")
        if type(size) is not int or not 0 < size <= MAX_BUNDLE_BYTES:
            raise ValueError
        download_url = asset.get("browser_download_url")
        parsed = urlsplit(download_url if isinstance(download_url, str) else "")
        if (parsed.scheme != "https" or parsed.hostname != "github.com"
                or parsed.username or parsed.password
                or parsed.path != f"/{OWNER}/{REPOSITORY}/releases/download/{tag}/{asset_name}"):
            raise ValueError
        published = release.get("published_at")
        if not isinstance(published, str) or len(published) > 64:
            published = None
        release_url = release.get("html_url")
        if not isinstance(release_url, str) or not release_url.startswith(
                f"https://github.com/{OWNER}/{REPOSITORY}/releases/tag/{tag}"):
            release_url = f"https://github.com/{OWNER}/{REPOSITORY}/releases/tag/{tag}"
    except (ValueError, TypeError, KeyError, json.JSONDecodeError):
        raise GitHubUpdateError("The published GitHub update metadata is incomplete or invalid.") from None

    installed = tuple(map(int, current_version.split(".")))
    candidate = tuple(map(int, version.split(".")))
    if candidate <= installed:
        return {"state": "current", "current_version": current_version}

    bundle = _read(opener, download_url, limit=MAX_BUNDLE_BYTES,
                   accept="application/octet-stream")
    if len(bundle) != size:
        raise GitHubUpdateError("The GitHub release file did not match its published size.")
    digest = asset.get("digest")
    if digest is not None:
        if (not isinstance(digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
                or digest[7:] != hashlib.sha256(bundle).hexdigest()):
            raise GitHubUpdateError("The GitHub release file failed its published checksum.")
    try:
        with tempfile.NamedTemporaryFile(prefix="luma-update-check-", suffix=".lup") as temporary:
            temporary.write(bundle)
            temporary.flush()
            verified = verify_bundle(Path(temporary.name), public_key_path)
    except UpdateError as error:
        raise GitHubUpdateError(str(error)) from None
    if verified["version"] != version:
        raise GitHubUpdateError("The GitHub release tag and signed application version do not match.")
    return {"state": "available", "current_version": current_version,
            "version": version, "release_notes": notes[:MAX_NOTES_CHARS],
            "published_at": published, "release_url": release_url,
            "source_sha256": verified["source_sha256"], "bundle": bundle}
