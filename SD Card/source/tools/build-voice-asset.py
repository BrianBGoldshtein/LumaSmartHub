#!/usr/bin/env python3
"""Build a separately signed, pinned ARM64 Piper voice asset for a Luma release.

This intentionally does not put the private signing key or 130+ MB model/runtime
in Git. Download the exact files listed in voice-assets.lock.json from their
official sources, then sign them with the same offline key used for .lup files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import tomllib
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def digest(path: Path) -> tuple[str, int]:
    hashed = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            hashed.update(block)
            size += len(block)
    return hashed.hexdigest(), size


def build(root: Path, assets: Path, key_path: Path, output: Path) -> dict:
    root, assets, key_path = root.resolve(strict=True), assets.resolve(strict=True), key_path.resolve(strict=True)
    output = output.absolute()
    if output.exists() or output.is_symlink() or output.resolve(strict=False).is_relative_to(root):
        raise ValueError("choose a new output path outside the delivery tree")
    if key_path.is_relative_to(root):
        raise ValueError("the offline signing key must stay outside the delivery tree")
    if os.name == "posix" and stat.S_IMODE(key_path.stat().st_mode) & 0o077:
        raise ValueError("offline signing key permissions must be 0600")
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    public = serialization.load_pem_public_key((root / "source/system/luma-update-ed25519.pub").read_bytes())
    if not isinstance(key, Ed25519PrivateKey) or not isinstance(public, Ed25519PublicKey):
        raise ValueError("the signing key pair must be Ed25519")
    if key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw) != public.public_bytes(
            Encoding.Raw, PublicFormat.Raw):
        raise ValueError("the signing key does not match the image-pinned public key")
    lock = json.loads((root / "source/tools/voice-assets.lock.json").read_text(encoding="utf-8"))
    if lock.get("format") != 1 or lock.get("voice_id") != "en_US-kristin-medium" or lock.get("python") != "cp313-aarch64":
        raise ValueError("unsupported voice asset lock")
    version = tomllib.loads((root / "source/backend/pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    files: dict[str, dict[str, int | str]] = {}
    paths: dict[str, Path] = {}
    for name, pinned in sorted(lock["files"].items()):
        if not (name.startswith(("model/", "wheels/", "sources/"))) or name.count("/") != 1:
            raise ValueError("unsupported voice asset path")
        candidate = assets / ("py313-wheels/" + name.split("/", 1)[1]
                              if name.startswith("wheels/") else name)
        if candidate.is_symlink() or not candidate.is_file():
            raise ValueError(f"missing regular voice asset: {name}")
        actual, size = digest(candidate)
        if actual != pinned:
            raise ValueError(f"voice asset hash differs from the source lock: {name}")
        files[name] = {"sha256": actual, "size": size}
        paths[name] = candidate
    manifest = {"format": 1, "kind": "luma-offline-voice", "version": version,
                "voice_id": lock["voice_id"], "python": lock["python"], "files": files}
    encoded = canonical(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "x", compression=zipfile.ZIP_STORED, allowZip64=True) as archive:
        for name, contents in {"manifest.json": encoded, "manifest.sig": key.sign(encoded)}.items():
            archive.writestr(name, contents)
        for name, path in paths.items():
            archive.write(path, name)
    return {"version": version, "files": len(files), "sha256": digest(output)[0], "bytes": output.stat().st_size}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="SD Card directory")
    parser.add_argument("--assets", required=True, type=Path, help="directory containing model/, sources/ and py313-wheels/")
    parser.add_argument("--key", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(build(args.root, args.assets, args.key, args.output), sort_keys=True))
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.error(str(error))
