#!/usr/bin/env python3
"""Enable the BlueZ D-Bus option Luma uses for bonded iPhone reconnect."""
import os
from pathlib import Path
import re
import stat
import tempfile


class BlueZOptOut(ValueError):
    """The administrator explicitly disabled the experimental interfaces."""


def save_original(path: Path, original: bytes) -> None:
    backup = path.with_name(f"{path.name}.luma-before-le")
    if backup.exists() or backup.is_symlink():
        info = backup.lstat()
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                or info.st_mode & 0o022 or backup.read_bytes() != original):
            raise ValueError("The existing BlueZ backup differs from the current configuration")
        return
    # Link a fully flushed file so an interrupted backup is never mistaken
    # for an existing administrator backup on the next run.
    with tempfile.NamedTemporaryFile(dir=path.parent) as stream:
        stream.write(original)
        stream.flush()
        os.fsync(stream.fileno())
        os.link(stream.name, backup)


def enable(path: Path, *, backup: bool = False) -> bool:
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("BlueZ configuration is not a regular file")
    original = path.read_bytes()
    contents = original.decode("utf-8")
    general = list(re.finditer(r"(?m)^\[General\][ \t]*\r?$", contents))
    if len(general) != 1:
        raise ValueError("Expected one BlueZ [General] section")
    header = general[0]
    following = re.search(r"(?m)^\[", contents[header.end():])
    end = header.end() + following.start() if following else len(contents)
    values = re.findall(r"(?m)^[ \t]*Experimental[ \t]*=[ \t]*([^\r\n]*)", contents[header.end():end])
    if values:
        if len(values) == 1 and values[0].strip() == "true":
            return False
        if len(values) == 1 and values[0].strip() == "false":
            raise BlueZOptOut("BlueZ has an explicit Experimental=false setting")
        raise ValueError("Unexpected BlueZ Experimental setting")
    newline = "\r\n" if header.group().endswith("\r") else "\n"
    split = header.end() + 1
    prefix = contents[:split]
    if not prefix.endswith("\n"):
        prefix += newline
    updated = prefix + "Experimental=true" + newline + contents[split:]
    if backup:
        save_original(path, original)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(updated.encode("utf-8"))
            stream.flush()
            os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode))
            os.fchown(stream.fileno(), info.st_uid, info.st_gid)
            os.fsync(stream.fileno())
            # Persist the backup directory entry before replacing main.conf.
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
    return True


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image-build", action="store_true")
    args = parser.parse_args()
    path = Path("/etc/bluetooth/main.conf")
    if not args.image_build:
        info = path.parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("BlueZ configuration directory is not root-controlled")
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("BlueZ configuration is not a root-controlled regular file")
    try:
        changed = enable(path, backup=not args.image_build)
    except BlueZOptOut as error:
        print(error)
        return
    print("Enabled BlueZ reconnect support" if changed else "BlueZ reconnect support is already enabled")


if __name__ == "__main__":
    main()
