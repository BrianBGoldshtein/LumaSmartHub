# Bluetooth Low Energy reconnect on Luma

Starting with Luma 0.4.2, install the signed update from **Settings → Luma software**. After the application passes its health check, the update broker backs up the BlueZ config to `/etc/bluetooth/main.conf.luma-before-le` and enables the D-Bus option if it is unset. The usual post-update reboot loads the new setting. Existing pairings and explicit BlueZ settings are preserved. Check automatic return with your registered iPhone nearby by turning Bluetooth off and on in iPhone Settings and leaving Luma untapped for a minute. The update can enable the reconnect option even when the card was flashed before that option was added to image builds.

For an administrator investigating the system step, `journalctl -u luma-bluez-reconnect.service -b -1` shows the result from the boot that installed the update when that boot's journal is available. To restore the backup, copy `/etc/bluetooth/main.conf.luma-before-le` over `main.conf` and restart `bluetooth.service` after checking for subsequent local edits. To explicitly disable the setting across future updates, set `Experimental=false` under `[General]`.

## Earlier releases and manual diagnosis

The interface became available and PreferredBearer became le on the old card, but reconnect still failed. A later controller capture isolated PIN or Key Missing during encryption. A one-time two-sided fresh pairing then recovered automatic return. A newly flashed 0.4.0 card can have this option unset again. Check the current configuration before using the reversible procedure below.

Owner's Pi runs BlueZ 5.82 and Luma 0.2.9. The selected trusted iPhone has a dual-mode bond, LE/classic keys and an identity-resolution key, but PreferredBearer is absent. General.Experimental is unset and bluetooth.service starts `/usr/libexec/bluetooth/bluetoothd` without additional arguments. This establishes a missing interface dependency, not proof of the cause of automatic reconnect failure.

The following owner-run experiment exposes BlueZ's experimental D-Bus interfaces. It does not enable KernelExperimental or Testing, disable SecureConnections, remove bonds, change the Wi-Fi connection, or bypass authorized ANCS. Existing Luma code already requests PreferredBearer=le when it is exposed. Bluetooth restart briefly disconnects devices. Pi Connect over Wi-Fi should remain available, but no remote-access guarantee is implied.

Run in Pi Connect remote shell, not Windows PowerShell. The script refuses a symlink/non-regular config, a missing/ambiguous General section, any already-set Experimental option, or an existing backup. It creates an exclusive exact-byte backup before replacing the config atomically; only a new Experimental=true line is added. Failure before replacement leaves the original config untouched. Failure after replacement requires the rollback below. Do not rerun after a failure without reading its message.

```bash
sudo python3 - <<'PY'
import configparser, os, pathlib, re, stat, tempfile
p = pathlib.Path('/etc/bluetooth/main.conf')
b = pathlib.Path('/etc/bluetooth/main.conf.luma-before-le-20261008')
s = p.lstat()
if not stat.S_ISREG(s.st_mode):
    raise SystemExit('Stopped: Bluetooth config is not a regular file.')
original = p.read_bytes()
text = original.decode('utf-8')
c = configparser.ConfigParser(interpolation=None, strict=True)
c.read_string(text)
if not c.has_section('General') or c.has_option('General', 'Experimental'):
    raise SystemExit('Stopped: General is missing or Experimental is already set.')
updated, count = re.subn(r'(?m)^(\[General\][ \t]*\r?$)',
                        r'\1\nExperimental=true', text)
if count != 1:
    raise SystemExit('Stopped: expected one plain General section header.')
with os.fdopen(os.open(b, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), 'wb') as f:
    f.write(original)
    f.flush()
    os.fsync(f.fileno())
with tempfile.NamedTemporaryFile(dir=p.parent, prefix='.luma-bluez-', delete=False) as f:
    temporary = pathlib.Path(f.name)
    f.write(updated.encode('utf-8'))
    f.flush()
    os.fchmod(f.fileno(), stat.S_IMODE(s.st_mode))
    os.fchown(f.fileno(), s.st_uid, s.st_gid)
    os.fsync(f.fileno())
try:
    os.replace(temporary, p)
    directory = os.open(p.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)
finally:
    temporary.unlink(missing_ok=True)
print('D-Bus Experimental enabled; exact original saved at:', b)
PY
```

Only after the script prints its success line:

```bash
sudo systemctl restart bluetooth.service
systemctl is-active bluetooth.service
```

Keep the iPhone nearby with Bluetooth on. Do not manually tap Connect. Allow about one minute for Luma to retry, then report whether it becomes an Authorized ANCS session and leaves privacy standby. If it succeeds, test iPhone Bluetooth off/on in Settings twice without tapping Connect and report times/results. This is a hardware experiment, not release acceptance solely from one successful link.

If restarting fails or the experiment makes things worse, restore the exact original config (only while no other Bluetooth-config edits have been made since this experiment):

```bash
sudo cp /etc/bluetooth/main.conf.luma-before-le-20261008 /etc/bluetooth/main.conf
sudo systemctl restart bluetooth.service
```

Backup is mode 0600 for containment. Plain cp into the existing regular config retains its permissions; do not replace this with cp --preserve=mode. The original pairing is never deleted. Do not delete the backup while diagnosis is ongoing. If PreferredBearer was set to le during the experiment, that bond preference can persist; restoring daemon config alone does not erase it. A full preference rollback, if needed, requires reading/restoring the previous bearer through D-Bus before disabling the experimental interface, not deleting the bond.

References: [BlueZ 5.82 configuration](https://raw.githubusercontent.com/bluez/bluez/5.82/src/main.conf), [Device1 API](https://raw.githubusercontent.com/bluez/bluez/5.82/doc/org.bluez.Device.rst).
