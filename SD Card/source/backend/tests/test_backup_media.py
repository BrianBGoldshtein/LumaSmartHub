from datetime import UTC, datetime
import os
import sys

import pytest

from luma.backup_media import BackupMedia, MediaError, RemovableVolume
from luma.portable_backup import encrypt
from test_portable_backup import PASSWORD, empty_document


NOW = datetime(2026, 9, 28, 18, 45, 12, tzinfo=UTC)
VOLUME_ID = "a" * 32
ARCHIVE = encrypt(empty_document(), PASSWORD)

linux_media = pytest.mark.skipif(sys.platform != "linux", reason="POSIX directory-FD/removable-media checks require Linux")


def mounted_volume(path, **updates):
    metadata = path.stat()
    device = ((os.major(metadata.st_dev), os.minor(metadata.st_dev))
              if hasattr(os, "major") else None)
    values = {"id": VOLUME_ID, "label": "Owner USB", "mount_root": path, "device_node": "/dev/sdb",
              "filesystem_device": device, "require_mountpoint": False}
    values.update(updates)
    return RemovableVolume(**values)


def make_media(path, volume=None, *, eject=None, clock=None):
    if volume is None:
        volume = mounted_volume(path)
    return BackupMedia(lambda: [volume], power_off=eject, now=clock or (lambda: NOW))


@linux_media
def test_usb_write_read_list_and_eject_use_opaque_ids_and_verified_bytes(tmp_path):
    ejected = []
    media = make_media(tmp_path, eject=ejected.append)
    assert media.list() == [{"id": VOLUME_ID, "label": "Owner USB", "backups": []}]
    saved = media.write(VOLUME_ID, ARCHIVE)
    assert saved["verified"] is True
    listed = media.list()[0]["backups"]
    assert len(listed) == 1 and listed[0]["id"] == saved["id"]
    assert media.read(VOLUME_ID, saved["id"]) == ARCHIVE
    assert media.eject(VOLUME_ID) == {"ejected": True}
    assert ejected == ["/dev/sdb"]
    metadata = next((tmp_path / "Luma Backups").iterdir()).stat()
    assert metadata.st_mode & 0o777 == 0o600


@pytest.mark.parametrize("kwargs", [
    {"system_disk": True}, {"removable_usb": False}, {"writable": False}, {"filesystem_device": (999, 999)},
])
@linux_media
def test_system_non_usb_readonly_or_changed_volume_is_never_used(tmp_path, kwargs):
    row = mounted_volume(tmp_path)
    values = {key: getattr(row, key) for key in row.__dataclass_fields__}
    values.update(kwargs)
    media = make_media(tmp_path, RemovableVolume(**values))
    with pytest.raises(MediaError):
        media.write(VOLUME_ID, ARCHIVE)


@linux_media
def test_caller_cannot_supply_path_filename_or_invent_volume(tmp_path):
    media = make_media(tmp_path)
    with pytest.raises(MediaError, match="encrypted"):
        media.write(VOLUME_ID, b"plain text must never be written")
    with pytest.raises(MediaError):
        media.write("../../etc", b"data")
    with pytest.raises(MediaError):
        media.read(VOLUME_ID, "../../luma.db")
    with pytest.raises(MediaError):
        media.write(VOLUME_ID, b"x" * (1024 * 1024 + 1))


@linux_media
def test_symlinked_backup_folder_is_rejected(tmp_path):
    # A non-directory at the fixed name also fails closed. Linux image tests
    # separately cover O_NOFOLLOW against an actual hostile symlink.
    (tmp_path / "Luma Backups").write_text("not a directory")
    media = make_media(tmp_path)
    with pytest.raises(MediaError, match="not safe"):
        media.write(VOLUME_ID, ARCHIVE)
    assert (tmp_path / "Luma Backups").read_text() == "not a directory"


@linux_media
def test_existing_exports_are_never_replaced_when_publish_fails(tmp_path, monkeypatch):
    media = make_media(tmp_path)
    original = media.write(VOLUME_ID, ARCHIVE)
    path = tmp_path / "Luma Backups" / next((tmp_path / "Luma Backups").iterdir()).name
    monkeypatch.setattr(os, "link", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("injected")))
    with pytest.raises(MediaError, match="previous backup was kept"):
        media.write(VOLUME_ID, ARCHIVE)
    assert media.read(VOLUME_ID, original["id"]) == ARCHIVE
    assert path.exists() and len(media.list()[0]["backups"]) == 1


@linux_media
def test_directory_fd_pins_selected_filesystem_when_mount_path_is_swapped(tmp_path, monkeypatch):
    # Operations work relative to the opened mount directory, so moving its
    # pathname cannot redirect them into a newly created directory at that path.
    original = tmp_path / "usb"
    original.mkdir()
    row = mounted_volume(original)
    media = make_media(original, row)
    moved = tmp_path / "detached-usb"
    create_directory = media._directory
    swapped = False
    def swap_after_volume_open(root_fd, create=False):
        nonlocal swapped
        if not swapped:
            original.rename(moved)
            original.mkdir()
            swapped = True
        return create_directory(root_fd, create)
    monkeypatch.setattr(media, "_directory", swap_after_volume_open)
    media.write(VOLUME_ID, ARCHIVE)
    assert not list(original.iterdir())
    assert list((moved / "Luma Backups").iterdir())


def test_opaque_ids_and_backup_names_are_strict():
    from luma.backup_media import _backup_name, _identifier, _name_id
    name = "luma-settings-20260928T184512Z-012345abcdef.lumabackup"
    assert _backup_name(name)
    assert _identifier(_name_id(name))
    assert not _backup_name("../../luma.db")
    assert not _identifier("../etc/passwd")


def test_inventory_rejects_duplicate_or_malformed_volume_ids():
    media = BackupMedia(lambda: [RemovableVolume(VOLUME_ID, "USB", ".", "/dev/sdb"),
                                 RemovableVolume(VOLUME_ID, "USB copy", ".", "/dev/sdc")])
    with pytest.raises(MediaError, match="inventory"):
        media.list()
