import json
import os
import pytest

from luma.backup_inventory import LinuxUSBInventory
from luma.backup_broker import BackupBroker, validate_request


pytestmark = pytest.mark.skipif(os.name != "posix", reason="Linux sysfs identity paths require POSIX")


def _fixture(tmp_path):
    (tmp_path / "media" / "LUMA").mkdir(parents=True)
    sysroot = tmp_path / "sys" / "dev" / "block"
    devices = tmp_path / "sys" / "devices"
    for identity, relative in {
        "8:0": "platform/pci/internal/block/sda",
        "8:1": "platform/pci/internal/block/sda/sda1",
        "8:16": "platform/pci/usb1/1-1/block/sdb",
        "8:17": "platform/pci/usb1/1-1/block/sdb/sdb1",
    }.items():
        (devices / relative).mkdir(parents=True, exist_ok=True)
        (sysroot / identity).parent.mkdir(parents=True, exist_ok=True)
        (sysroot / identity).symlink_to(devices / relative, target_is_directory=True)

    block = {
        "blockdevices": [
            {"name": "/dev/sda", "path": "/dev/sda", "type": "disk", "rm": False,
             "tran": "sata", "maj:min": "8:0", "children": [
                 {"name": "/dev/sda1", "path": "/dev/sda1", "type": "part", "rm": False,
                  "tran": None, "fstype": "ext4", "label": "root", "uuid": "root-uuid",
                  "maj:min": "8:1", "pkname": "sda", "mountpoints": ["/"]}]},
            {"name": "/dev/sdb", "path": "/dev/sdb", "type": "disk", "rm": True,
             "tran": "usb", "maj:min": "8:16", "children": [
                 {"name": "/dev/sdb1", "path": "/dev/sdb1", "type": "part", "rm": True,
                  "tran": "usb", "fstype": "exfat", "label": "LUMA", "uuid": "media-uuid",
                  "maj:min": "8:17", "pkname": "sdb", "mountpoints": [str(tmp_path / "media" / "LUMA")]}]},
        ]}
    mountinfo = "36 25 8:1 / / rw,relatime - ext4 /dev/sda1 rw\n"
    calls = []

    def runner(args, **kwargs):
        calls.append(args)
        return type("Result", (), {"stdout": json.dumps(block)})

    inventory = LinuxUSBInventory(runner=runner, sys_dev_block=sysroot,
                                  mountinfo=tmp_path / "mountinfo")
    inventory.mountinfo.write_text(mountinfo, encoding="utf-8")
    return inventory, calls, block


def test_scan_mints_opaque_ids_only_for_non_system_removable_usb(tmp_path):
    inventory, _, _ = _fixture(tmp_path)
    volumes = inventory.scan()
    assert len(volumes) == 1
    selected = volumes[0]
    assert len(selected.id) == 32
    assert selected.device_node == "/dev/sdb"
    assert selected.system_disk is False and selected.removable_usb is True
    assert selected.filesystem_device == (8, 17)
    assert inventory.current_volumes() == volumes


def test_ids_expire_when_media_identity_changes(tmp_path):
    inventory, _, block = _fixture(tmp_path)
    first = inventory.scan()[0]
    block["blockdevices"][1]["children"][0]["uuid"] = "different-media"
    assert inventory.current_volumes() == []
    second = inventory.scan()[0]
    assert second.id != first.id


def test_volume_ids_expire_after_five_minutes(tmp_path):
    inventory, _, _ = _fixture(tmp_path)
    inventory.clock = lambda: 100.0
    assert inventory.scan()
    inventory.clock = lambda: 401.0
    assert inventory.current_volumes() == []


def test_unknown_usb_transport_or_nonremovable_disk_is_not_eligible(tmp_path):
    inventory, _, block = _fixture(tmp_path)
    block["blockdevices"][1]["rm"] = False
    assert inventory.scan() == []
    block["blockdevices"][1]["rm"] = True
    block["blockdevices"][1]["tran"] = "sata"
    assert inventory.scan() == []


def test_read_only_usb_mount_is_not_offered_for_export(tmp_path):
    inventory, _, _ = _fixture(tmp_path)
    inventory.mountinfo.write_text(
        "36 25 8:1 / / rw,relatime - ext4 /dev/sda1 rw\n"
        "70 25 8:17 / /media/LUMA ro,nosuid - exfat /dev/sdb1 ro\n",
        encoding="utf-8")
    assert inventory.scan()[0].writable is False


def test_backup_protocol_rejects_arbitrary_paths_unknown_fields_and_duplicates():
    for request in (
        {"action": "read", "volume_id": "a" * 32, "backup_id": "b" * 32, "path": "/"},
        {"action": "eject", "volume_id": "/dev/sda"},
    ):
        try:
            validate_request(request)
        except ValueError:
            pass
        else:
            raise AssertionError("unsafe request was accepted")
    try:
        json.loads('{"action":"list","action":"eject","volume_id":"' + "a" * 32 + '"}',
                   object_pairs_hook=lambda pairs: _reject_duplicates(pairs))
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate fields were accepted")


def test_root_broker_scan_and_export_api_use_only_minted_media_ids():
    calls = []

    class Inventory:
        def scan(self, *, mount):
            calls.append(("scan", mount))

    class Media:
        def list(self):
            return [{"id": "a" * 32, "backups": []}]
        def write(self, volume_id, data):
            calls.append(("write", volume_id, data))
            return {"verified": True}

    broker = BackupBroker(inventory=Inventory(), media=Media())
    assert broker.execute({"action": "scan"})["volumes"][0]["id"] == "a" * 32
    assert calls == [("scan", True)]
    assert broker.execute({"action": "write", "volume_id": "a" * 32,
                           "archive": "TFVNQVVTQg=="}) == {"verified": True}
    assert calls[-1] == ("write", "a" * 32, b"LUMAUSB")
    try:
        broker.execute({"action": "write", "volume_id": "/dev/sda", "archive": "TFVNQVVTQg=="})
    except ValueError:
        pass
    else:
        raise AssertionError("broker accepted a client-supplied device path")


def _reject_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate")
        result[key] = value
    return result
