# Luma 0.2.3: update the existing microSD without reflashing

This procedure is for the Pi currently running Luma `0.2.0`. It uses the
Windows-readable FAT **BOOT** partition to ask the **already-installed** signed
updater to install `0.2.3` once. It does **not** format the card, replace the
Linux OS, or reset the Google account, Wi-Fi, PIN, Tailscale identity, game
saves or Luma preferences. Those live outside the switched application release
under `/var/lib/luma`. As with any SD-card operation, a current independent
backup is still valuable; a failing card or power loss during filesystem writes
cannot be made risk-free.

The kit is an owner-directed feature-branch hardware-test candidate, not yet a
stable GitHub `main` release. The signed archive is checked by the public key
already pinned in your Pi image; the signing private key stays offline on the
build laptop. Do **not** select this `.lup` as a Custom OS in Pi Imager. An
offline ARM64 test on a disposable r13 image confirmed the one-shot boot,
signature verification, `0.2.0` → `0.2.3` app switch, restoration of the
original boot command line, and healthy new API/database. The final kit was
rebuilt only for an additional night-clock CSS adjustment; it uses the same
backend wheel and independently passed the signed-bundle verifier. Real Pi
behavior remains untested.

## On the Pi and Windows laptop

1. Shut down Luma normally and wait for the Pi to power off. Unplug Pi power,
   remove its microSD, and insert it in the laptop. If Windows offers to
   **format** the Linux partition, cancel that prompt.
2. Identify the small FAT BOOT drive by its `cmdline.txt`, `config.txt` and
   `kernel8.img` files. Do not select a Samsung USB stick or Windows drive.
3. Open PowerShell. Substitute only the real BOOT drive letter for `E:`:

   ```powershell
   powershell.exe -NoProfile -ExecutionPolicy Bypass -File "C:\Users\brian\OneDrive\Documents\ChatGPT\Smart Wall Screen\SD Card\updates\v023-no-flash\arm-boot-fat-recovery.ps1" -BootDrive "E:"
   ```

   The script checks that this is FAT BOOT, copies and verifies the signed
   archive, backs up `cmdline.txt` byte-for-byte, then arms a one-time boot
   command. It refuses a pre-existing 0.2.3 recovery backup rather than
   overwriting it. Do not run it twice.
4. Use Windows **Eject** for BOOT. Reinsert the microSD in the powered-off Pi
   and reconnect power. The first boot may take several minutes; keep power
   connected. Because the **old `0.2.0` installer** controls this one initial
   switch, the screen may go dark with a pointer while it restarts the kiosk.
   Do not right-click/Exit, click Update again, or power-cycle during it. The
   new progress display applies to **subsequent** updates after 0.2.3 starts.
5. When Luma returns, open **Settings → Luma software** and confirm `0.2.3`.
   Check that the existing Google calendar, Wi-Fi, PIN, Tailscale and theme are
   still configured. Then test phone reconnection, normal-speech mic level,
   voice orb, night dimming and the GitHub updater status. Physical acceptance
   is required before calling 0.2.3 stable.

The one-shot boot script restores the **exact original** `cmdline.txt` before
asking the updater to act. The signed updater stages a separate app release,
checks the new API/database, and rolls back to the old app if health fails.
This does not touch durable user data. If the result is not `0.2.3`, shut down
safely, inspect `luma-v023-result.log` on BOOT from the laptop, and report only
the non-secret failure text. Never send OAuth JSON, PIN, tokens, account data,
private calendar entries or login links. If the log says the original boot
command line was not restored, **stop** instead of repeatedly booting.

The recovery files can remain on BOOT afterward; they are not re-executed
because the original boot command line has been restored. After hardware
acceptance and an approved merge to `main`, later normal application releases
should use Luma's signed GitHub update button. Pi Connect remains a recovery
tool, not a requirement for this path.
