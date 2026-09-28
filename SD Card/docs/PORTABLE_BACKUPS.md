# Portable settings backups — source checkpoint

The portable backup is a separate format from `luma-maintenance backup`. The
maintenance command copies the private live SQLite database, including account
secrets; it must stay administrator-only and must never be offered as a portable
USB export.

## Implemented in source

- `portable_backup.py` uses a versioned binary envelope with AES-256-GCM and a
  fixed-cost scrypt KDF (32 MiB, random 16-byte salt and 12-byte nonce). Header
  parameters are checked against a strict allowlist before deriving a key; the
  header is authenticated as associated data. Archive, document, schema and
  passphrase lengths are bounded. Duplicate JSON fields, unexpected keys,
  unsupported KDF parameters, tampering and wrong passphrases fail closed.
- Export is an explicit preference allowlist, not a database/cache dump. It
  excludes OAuth/VeSync/511/Luma credentials, calendars and account identifiers,
  phone identity, PIN configuration, Wi-Fi/Bluetooth/Tailscale/SSH material,
  private cached events, live weather, appliance bindings and notification data.
  The four saved game checkpoints are validated against strict per-game
  schemas and transferred separately through the browser local-storage bridge;
  unrelated game saves are preserved when absent from an archive.
- Google countdown pins are converted into local, unlinked title/date reminders;
  transit favorites omit live predictions. Scene action intent is retained but
  device bindings are stripped; all restored scenes are off and receive an
  impossible placeholder binding until a later explicit device review/rebind.
- `apply_document()` validates every section before a single SQLite transaction
  replaces settings, local dates, transit favorites and disabled scene records.
  It leaves provider secrets, calendar/task links, phone pairing, PIN state,
  purifier/fan configurations and existing microphone mute untouched. A muted
  target stays muted even if the backup says voice is enabled. Automation is
  never replayed.
- `backup_media.py` accepts only opaque fresh IDs and authenticated-container
  envelopes, never caller paths or filenames. Its POSIX path uses pinned
  directory file descriptors, no-follow opens, a fixed folder/name format,
  bounded file counts/sizes, read-back verification and atomic no-clobber
  publication. Existing exports are retained. Eject uses a fixed `udisksctl`
  invocation and reports failure honestly.
- `backup_inventory.py` uses structured `lsblk` data, requires USB transport,
  removable flags and USB sysfs ancestry, rejects filesystem ancestors backing
  `/`, `/boot` or `/boot/firmware`, limits filesystems to an explicit data-FS
  allowlist, tracks read-only mounts, and binds short-lived random volume IDs
  to the device, filesystem UUID and major/minor identity. IDs expire after
  five minutes; each media operation re-enumerates devices and matches the
  selected ID before access.
- `backup_broker.py` provides scan/list/write/read/eject over a root-owned,
  systemd-activated Unix socket. It verifies the Linux peer UID is `luma`,
  requires exact action schemas, accepts opaque IDs only, and bounds the
  encrypted payload. The Pi installer now provisions UDisks/util-linux and
  filesystem support plus a confined broker service/socket.
- The owner-gated loopback API exposes scan/list/export/preview/apply/eject.
  Preview data is memory-only and short-lived; apply requires a separate
  explicit confirmation and reloads the live settings/countdown/transit/scene
  stores while preserving accounts, device links and mute state. The themed
  touch flow transfers browser game saves only on the confirmed apply path.
- A Linux-only end-to-end source integration test now drives the actual broker
  Unix-socket handler and owner API through temporary encrypted media: scan,
  verified write, list/read, passphrase preview, confirmed restore, preservation
  of account/phone/calendar/mute state, and safe-eject dispatch. It uses a temp
  directory rather than a mounted USB device and a fake power-off callback; it
  does not start systemd or claim the packaged `luma` UID. The real
  `SO_PEERCRED` value is read, but the isolated test maps the expected service
  name to its current test UID because WSL has no appliance `luma` account.
- Latest complete current-source backend qualification: **963 passed on Ubuntu
  WSL**; **907 passed, 25 Linux-only skipped on Windows**. Frontend suite:
  **112 passed**; TypeScript and production build passed. Linux-only inventory,
  media, socket and integration cases ran in WSL. These are still
  software/synthetic checks; no real USB device, Pi, or final image was
  qualified.
- Linux-native `systemd-analyze verify` and installer-shell checks pass for the
  backup service/socket. The exhaustive image-file audit map now explicitly
  includes both units; a missing mapping had been found and corrected. The
  installer now explicitly creates the `luma` group idempotently and uses it as
  the account's primary group, matching the socket ACL rather than relying on
  distro user-group defaults. Static checks do not start a manager, provision
  the actual image account, or prove the final raw image contains these files.

## Not physically or release qualified yet

The inventory/broker/API/UI are source-integrated and tested with synthetic
Linux block-device state, a real temporary Unix-socket/API/media round trip,
and native static checks of the service packaging.
They are not yet qualified against the actual systemd socket activation, the
installed `luma` service UID, real Pi USB media, or the final image. Required
gates: verify packaged activation and service identity on the Linux image; test
removable media, restore and rollback on assembled hardware only after the
owner prompts; then rebuild and qualify a separate immutable final image. The
existing card/image must remain untouched.

Do not call feature 10 complete, do not write to arbitrary disks, and do not
claim a tested USB backup/restore flow until those pieces and a real packaged
Linux WebSocket test pass. Hardware testing still waits for the owner's prompt.
