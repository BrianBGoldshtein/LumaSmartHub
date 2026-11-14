#!/usr/bin/env python3
"""Enable the BlueZ D-Bus option Luma uses for bonded iPhone reconnect."""
import os
from pathlib import Path
import re
import stat
import tempfile


def enable(path: Path) -> bool:
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
        raise ValueError("BlueZ already has an explicit Experimental setting")
    newline = "\r\n" if header.group().endswith("\r") else "\n"
    split = header.end() + 1
    prefix = contents[:split]
    if not prefix.endswith("\n"):
        prefix += newline
    updated = prefix + "Experimental=true" + newline + contents[split:]
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(updated.encode("utf-8"))
            stream.flush()
            os.fchmod(stream.fileno(), stat.S_IMODE(info.st_mode))
            os.fchown(stream.fileno(), info.st_uid, info.st_gid)
            os.fsync(stream.fileno())
            os.replace(temporary, path)
            directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        finally:
            temporary.unlink(missing_ok=True)
    return True


if __name__ == "__main__":
    enable(Path("/etc/bluetooth/main.conf"))
