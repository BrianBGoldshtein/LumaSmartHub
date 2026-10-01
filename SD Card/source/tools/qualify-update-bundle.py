#!/usr/bin/env python3
"""Exercise one real signed .lup in a disposable Linux release tree.

This tests the exact archive and the updater's wheel install, atomic switch,
health-failure rollback and saved-state separation. It does not boot a Pi or
claim that systemd, Chromium or the physical SD card has been qualified.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "source/backend/src"))

from luma.update_agent import UpdateError, apply_bundle, verify_bundle  # noqa: E402


class Controller:
    def __init__(self) -> None:
        self.actions: list[str] = []

    def stop(self) -> None:
        self.actions.append("stop")

    def start(self) -> None:
        self.actions.append("start")


def tree(destination: Path, current_version: str) -> tuple[Path, Path, Path, Path]:
    """Create a credential-free stand-in with the installed dependency/schema contract."""
    releases = destination / "luma-releases"
    current = releases / current_version
    (current / "backend/src/luma").mkdir(parents=True)
    (current / "frontend").mkdir()
    project = (ROOT / "source/backend/pyproject.toml").read_text(encoding="utf-8")
    project, count = re.subn(r'(?m)^version = "[^"]+"$',
                             f'version = "{current_version}"', project, count=1)
    if count != 1:
        raise ValueError("source version marker was not found")
    (current / "backend/pyproject.toml").write_text(project, encoding="utf-8")
    (current / "backend/src/luma/storage.py").write_bytes(
        (ROOT / "source/backend/src/luma/storage.py").read_bytes())
    (current / "frontend/index.html").write_text("previous display", encoding="utf-8")
    (current / ".luma-release.json").write_text(
        json.dumps({"version": current_version}), encoding="utf-8")
    subprocess.run(["/usr/bin/python3", "-m", "venv", str(current / "venv")],
                   check=True, timeout=90, stdout=subprocess.DEVNULL)
    app = destination / "luma"
    app.symlink_to(Path("luma-releases") / current_version, target_is_directory=True)
    saved = destination / "durable-state" / "settings-marker"
    saved.parent.mkdir()
    saved.write_bytes(b"settings survive both outcomes\n")
    return app, releases, current, saved


def update_umask() -> int:
    unit = (ROOT / "source/system/luma-update.service").read_text(encoding="utf-8")
    match = re.search(r"(?m)^UMask=(0[0-7]{3})$", unit)
    if not match:
        raise AssertionError("the updater service has no auditable umask")
    return int(match.group(1), 8)


def assert_readable_by_luma(candidate: Path) -> None:
    """Check the files reached by non-root API and kiosk processes."""
    probe = subprocess.run(
        [str(candidate / "venv/bin/python"), "-c",
         "import importlib.util; spec=importlib.util.find_spec('luma.api'); "
         "print(spec.origin if spec else '')"],
        check=True, capture_output=True, text=True, timeout=15)
    module = Path(probe.stdout.strip())
    if not module.is_file() or not module.is_relative_to(candidate):
        raise AssertionError("the installed Luma API module is not in the candidate")
    paths = [module, candidate / "frontend/index.html"]
    paths.extend((candidate / "frontend/assets").iterdir())
    for file in paths:
        if not file.is_file() or not stat.S_IMODE(file.stat().st_mode) & stat.S_IROTH:
            raise AssertionError(f"the Luma service user cannot read {file.relative_to(candidate)}")
        parent = file.parent
        while parent.is_relative_to(candidate):
            if not stat.S_IMODE(parent.stat().st_mode) & stat.S_IXOTH:
                raise AssertionError(f"the Luma service user cannot traverse {parent.relative_to(candidate)}")
            parent = parent.parent


def check(bundle: Path, key: Path, current_version: str, *, healthy: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="luma-real-bundle-") as scratch:
        app, releases, current, saved = tree(Path(scratch), current_version)
        controller = Controller()
        phases: list[str] = []
        version = verify_bundle(bundle, key)["version"]
        if healthy:
            previous_umask = os.umask(update_umask())
            try:
                candidate = apply_bundle(bundle, app_root=app, releases_root=releases,
                                         public_key_path=key, controller=controller,
                                         health_check=lambda selected: selected == version,
                                         progress=phases.append)
            finally:
                os.umask(previous_umask)
            if (app.resolve() != candidate or not current.is_dir()
                    or controller.actions != ["stop", "start"]
                    or phases[-1] != "complete"):
                raise AssertionError("the signed candidate did not switch cleanly")
            command = candidate / "venv/bin/luma-api"
            if not command.is_file() or str(candidate).encode() not in command.read_bytes().splitlines()[0]:
                raise AssertionError("the installed API command did not relocate to the candidate")
            result = subprocess.run([str(candidate / "venv/bin/python"), "-c",
                                     "from importlib.metadata import version; "
                                     "print(version('luma-smart-screen'))"],
                                    check=True, capture_output=True, text=True, timeout=15)
            if result.stdout.strip() != version:
                raise AssertionError("the installed wheel has the wrong version")
            assert_readable_by_luma(candidate)
        else:
            try:
                apply_bundle(bundle, app_root=app, releases_root=releases,
                             public_key_path=key, controller=controller,
                             health_check=lambda _selected: False,
                             progress=phases.append)
            except UpdateError as error:
                if "health check" not in str(error):
                    raise
            else:
                raise AssertionError("a failed health check did not reject the candidate")
            if (app.resolve() != current or (releases / version).exists()
                    or controller.actions != ["stop", "start", "stop", "start"]
                    or "restoring" not in phases):
                raise AssertionError("the failed update did not restore the previous release")
        if saved.read_bytes() != b"settings survive both outcomes\n":
            raise AssertionError("the update changed durable owner state")
        print(f"{version}: {'switch' if healthy else 'rollback'} passed; "
              f"phases={','.join(phases)}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("bundle", type=Path)
    parser.add_argument("--public-key", type=Path,
                        default=ROOT / "source/system/luma-update-ed25519.pub")
    parser.add_argument("--current-version", default="0.2.3")
    args = parser.parse_args()
    if not sys.platform.startswith("linux"):
        parser.error("the atomic switch requires Linux")
    version = verify_bundle(args.bundle, args.public_key)["version"]
    if tuple(map(int, version.split("."))) <= tuple(map(int, args.current_version.split("."))):
        parser.error("bundle must be newer than the synthetic installed version")
    check(args.bundle, args.public_key, args.current_version, healthy=True)
    check(args.bundle, args.public_key, args.current_version, healthy=False)


if __name__ == "__main__":
    main()
