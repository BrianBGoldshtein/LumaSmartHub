#!/usr/bin/env python3
"""Fingerprint the exact appliance build inputs, excluding host caches/secrets.

Creates a generated JSON artifact when --output is given. Without it, prints
only a deterministic aggregate digest for pre/post-build comparison.
"""
import argparse
import hashlib
import json
from pathlib import Path

TREES = ("source/backend/src", "source/frontend/dist", "source/system", "source/assets",
         "image-builder/hooks", "image-builder/layer")
FILES = ("source/backend/pyproject.toml", "source/tests/device_smoke.py", "source/tests/tailscale-status.json", "image-builder/luma.yaml",
         "image-builder/build-image.sh", "image-builder/prepare-assets.sh", "image-builder/source-manifest.py")


def manifest(root: Path) -> dict:
    root = root.resolve(strict=True)
    paths = [root / name for name in FILES]
    for name in TREES:
        directory = root / name
        if not directory.is_dir() or directory.is_symlink():
            raise ValueError(f"Missing or linked build directory: {name}")
        paths.extend(p for p in directory.rglob("*") if "__pycache__" not in p.parts and p.suffix != ".pyc" and (p.is_file() or p.is_symlink()))
    entries = {}
    for path in sorted(paths):
        name = path.relative_to(root).as_posix()
        if path.is_symlink() or not path.resolve(strict=True).is_relative_to(root):
            raise ValueError(f"Linked or external build input: {name}")
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        entries[name] = digest.hexdigest()
    payload = {"format": 1, "files": entries}
    payload["source_sha256"] = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return payload


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = manifest(args.root)
    if args.output:
        # Exclusive creation: do not overwrite a prior candidate's provenance.
        with args.output.open("x", encoding="utf-8", newline="\n") as output:
            json.dump(result, output, sort_keys=True, indent=2)
            output.write("\n")
    print(result["source_sha256"])


if __name__ == "__main__":
    main()
