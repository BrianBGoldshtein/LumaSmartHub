#!/usr/bin/env python3
"""Build one signed, app-only update bundle using an externally held key."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile
import tomllib
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path, help="SD Card delivery directory")
    parser.add_argument("--key", required=True, type=Path, help="Ed25519 PEM private key; never put this in the delivery tree")
    parser.add_argument("--output", required=True, type=Path, help="New output path; existing files are never replaced")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    key_path = args.key.resolve(strict=True)
    output = args.output.absolute()
    if output.exists() or output.is_symlink():
        parser.error("output already exists; choose a new filename")
    if key_path.is_relative_to(root):
        parser.error("signing key must be outside the delivery tree")
    if stat.S_IMODE(key_path.stat().st_mode) & 0o077:
        parser.error("signing key permissions are too open; use mode 0600")
    key = serialization.load_pem_private_key(key_path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        parser.error("signing key must be Ed25519 PEM")

    backend = root / "source/backend"
    project = tomllib.loads((backend / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    version = project["version"]
    if not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", version):
        parser.error("project version must be a stable three-part release")
    with tempfile.TemporaryDirectory(prefix="luma-update-") as temporary:
        wheel_dir = Path(temporary)
        subprocess.run([sys.executable, "-m", "pip", "wheel", "--no-deps", "--no-cache-dir",
                        "--wheel-dir", str(wheel_dir), str(backend)], check=True)
        wheels = list(wheel_dir.glob("luma_smart_screen-*.whl"))
        if len(wheels) != 1:
            parser.error("backend build did not produce exactly one Luma wheel")
        payload: dict[str, bytes] = {
            "backend/pyproject.toml": (backend / "pyproject.toml").read_bytes(),
            f"backend/{wheels[0].name}": wheels[0].read_bytes(),
        }
        dist = root / "source/frontend/dist"
        if not dist.is_dir() or dist.is_symlink():
            parser.error("compiled frontend is missing; build it before packaging an update")
        for path in dist.rglob("*"):
            if path.is_symlink():
                parser.error(f"frontend contains a symbolic link: {path.relative_to(dist)}")
            if path.is_file():
                relative = path.relative_to(dist).as_posix()
                if relative == "index.html":
                    name = "frontend/index.html"
                elif (len(Path(relative).parts) == 2
                      and Path(relative).parts[0] in {"assets", "licenses"}):
                    name = f"frontend/{relative}"
                else:
                    parser.error(f"unexpected compiled frontend path: {relative}")
                payload[name] = path.read_bytes()
    if len(payload) > 512 or sum(map(len, payload.values())) > 24 * 1024 * 1024:
        parser.error("update payload exceeds device limits")

    source_hash = subprocess.run([sys.executable, str(root / "image-builder/source-manifest.py"), str(root)],
                                 check=True, capture_output=True, text=True).stdout.strip()
    if not re.fullmatch(r"[0-9a-f]{64}", source_hash):
        parser.error("source manifest did not produce a valid SHA-256")
    dependency_contract = {
        "dependencies": sorted(project["dependencies"]),
        "optional-dependencies": {key: sorted(value) for key, value in sorted(
            project.get("optional-dependencies", {}).items())},
    }
    manifest = {
        "format": 1,
        "version": version,
        "source_sha256": source_hash,
        "dependencies_sha256": hashlib.sha256(canonical(dependency_contract)).hexdigest(),
        "files": {name: {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
                  for name, data in sorted(payload.items())},
    }
    manifest_bytes = canonical(manifest)
    signature = key.sign(manifest_bytes)
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with output.open("xb") as raw:
            with zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
                bundle.writestr("manifest.json", manifest_bytes)
                bundle.writestr("manifest.sig", signature)
                for name, data in sorted(payload.items()):
                    bundle.writestr(name, data)
            raw.flush()
            os.fsync(raw.fileno())
    except FileExistsError:
        parser.error("output appeared during packaging; refusing to replace it")
    print(f"Built signed application bundle: {output} (Luma {version}, {len(payload)} files)")
    print("The signing private key was not copied to the bundle or appliance.")


if __name__ == "__main__":
    main()
