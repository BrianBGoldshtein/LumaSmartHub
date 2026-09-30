# r14 recovery from the existing microSD (no reflash)

This route is for the physical r13 card showing Luma `0.2.0` when Raspberry Pi
Connect cannot complete enrollment and campus Wi-Fi blocks local SSH. It uses
only Windows' readable FAT **BOOT** partition. It does not format either
partition, edit the Linux root filesystem from Windows, or erase the existing
Google sign-in, Wi-Fi, PIN, Tailscale identity, game saves or settings.

The signed `0.2.2` recovery kit passed an offline ARM64 boot/install test on a
disposable copy of the r13 image. The physical Pi, its Bluetooth radio and
campus Connect enrollment still require testing. The kit is a test candidate
on the feature branch, not a stable release from `main`. Its signed `.lup` is
verified by the already-installed r13 updater.

## On the Pi and Windows laptop

1. Use Luma's shutdown control and wait for the Pi to power off; then unplug
   the power supply. Remove only the Pi's microSD and insert it in the laptop.
   If Windows offers to **format** an unfamiliar Linux partition, cancel.
2. Identify the small FAT BOOT drive, containing `cmdline.txt`, `config.txt`
   and `kernel8.img`. Do not select another drive or the Windows system drive.
3. In PowerShell, replace `E:` below with that FAT BOOT drive letter. The
   script validates the filesystem and expected Pi boot files before writing:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\brian\OneDrive\Documents\ChatGPT\Smart Wall Screen\SD Card\updates\r14-no-flash\arm-boot-fat-recovery.ps1" -BootDrive "E:"
   ```

   It copies the signed bundle and one-shot script, makes a byte-for-byte
   backup of `cmdline.txt` on BOOT, stores both SHA-256 values, and appends a
   one-boot systemd command. It refuses a pre-existing recovery backup rather
   than overwriting it. The private signing key is not involved on Windows.
4. Use Windows **Eject** for the BOOT drive. Put the microSD back in the Pi,
   then reconnect power. The first boot may take longer while Luma stages and
   switches the version. Do not interrupt power during that first boot.
5. In **Settings → Luma software**, confirm version `0.2.2`. Confirm the
   existing Google calendar, Wi-Fi, PIN and Tailscale settings are still there.
   Then retry **Raspberry Pi Connect → Test Connect network → Start sign-in**.
   On **Your iPhone**, note the more specific Bluetooth connection status.
   The update does not treat a merely paired/connected phone as authorized:
   full calendar access still requires the verified notification session.

The one-shot script restores the exact original `cmdline.txt` **before** it
applies the update, so subsequent boots are normal even if installation fails.
The signed updater stages a new release under `/opt/luma-releases`, switches
the `/opt/luma` pointer, checks the new API/database, and rolls back to `0.2.0`
if its health check fails. Durable state under `/var/lib/luma` is outside the
switched directory. A filesystem or card failure is still possible; this is
not a substitute for a current backup.

If Luma does not show `0.2.2`, shut down safely, put the card back in the
laptop, and read `luma-r14-result.log` on BOOT. Report only the non-secret
error text; do not send PINs, OAuth JSON, private calendar data or sign-in
links. If the log says the original boot command line was not restored,
**stop** rather than repeatedly booting or changing `cmdline.txt` manually.

The recovery files can remain on BOOT after success; they are not executed
again because the original boot command line has been restored. Later normal
application updates should use Luma's signed GitHub release flow after
hardware acceptance and merge to `main`; Pi Connect remains a recovery tool.
