# BOOT diagnostics (next full-image iteration)

The next fully built Luma image installs an independent, root-owned
`luma-boot-diagnostics.service`. It records concise JSON lines in the FAT BOOT
partition, visible on a Windows computer as `luma-diagnostics.log`. The prior
rotated file is `luma-diagnostics.previous.log`. Each is limited to about
128 KiB; the service writes at boot and on changes to the active release,
update phase, or critical service state. It does not write continuously.

The record contains a UTC timestamp, boot ID, app version, update state/phase,
and systemd state/result/exit counters for the API, update broker, display,
voice, and kiosk. It intentionally excludes network credentials, Google data,
calendar titles, spoken phrases, and free-form error text. The FAT partition
is broadly readable; never put secrets in this log. Detailed, sensitive logs
remain in the protected Linux system journal and require authorized access.

If an update stalls, leave the Pi powered on while you observe the screen, and
do not retry blindly. After powering down, read the BOOT log on a computer.
An incomplete final JSON line can be ignored after an abrupt power loss. A
normal boot still starts the monitor when the Luma application itself fails.
No software log can run if the Pi fails before Linux mounts BOOT or starts
systemd; in that case the last retained log is still available for inspection.

This feature is **not present in the already-flashed 0.2.3 image** and cannot
be delivered by an app-only `.lup` release. It takes effect after a future
full-image flash or a separately qualified OS-level migration. Until then,
use the one-shot diagnostic kit in the workspace for 0.2.4 troubleshooting.
