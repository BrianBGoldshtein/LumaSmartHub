from pathlib import Path
from runpy import run_path
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "linux", reason="Linux image configuration")
enable = run_path(str(Path(__file__).resolve().parents[1] / "source/backend/src/luma/bluez_config.py"))["enable"]


@pytest.mark.parametrize("original,expected", [
    (b"[General]\n#Experimental=false\n[Policy]\n", b"[General]\nExperimental=true\n#Experimental=false\n[Policy]\n"),
    (b"[General]\r\n[Policy]\r\n", b"[General]\r\nExperimental=true\r\n[Policy]\r\n"),
    (b"[General]", b"[General]\nExperimental=true\n"),
])
def test_default_bluez_configuration_gets_bearer_option(tmp_path, original, expected):
    conf = tmp_path / "main.conf"
    conf.write_bytes(original)
    conf.chmod(0o640)
    assert enable(conf)
    assert conf.read_bytes() == expected
    assert conf.stat().st_mode & 0o777 == 0o640
    assert not enable(conf)


def test_existing_opt_out_is_preserved(tmp_path):
    conf = tmp_path / "main.conf"
    original = b"[General]\nExperimental=false\nKernelExperimental=false\n"
    conf.write_bytes(original)
    with pytest.raises(ValueError, match="explicit"):
        enable(conf)
    assert conf.read_bytes() == original


def test_update_keeps_an_exact_backup_and_is_idempotent(tmp_path):
    conf = tmp_path / "main.conf"
    backup = tmp_path / "main.conf.luma-before-le"
    original = b"[General]\n#Experimental = false\n#KernelExperimental = false\n"
    conf.write_bytes(original)
    assert enable(conf, backup=True)
    assert backup.read_bytes() == original
    assert backup.stat().st_mode & 0o777 == 0o600
    assert not enable(conf, backup=True)
    assert backup.read_bytes() == original


def test_update_resumes_after_backup_and_rejects_conflicting_backup(tmp_path):
    conf = tmp_path / "main.conf"
    backup = tmp_path / "main.conf.luma-before-le"
    original = b"[General]\n#Experimental = false\n"
    conf.write_bytes(original)
    backup.write_bytes(b"different configuration")
    with pytest.raises(ValueError, match="backup differs"):
        enable(conf, backup=True)
    assert conf.read_bytes() == original
    backup.write_bytes(original)
    assert enable(conf, backup=True)
    assert backup.read_bytes() == original
