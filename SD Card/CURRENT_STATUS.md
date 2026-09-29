# Luma — current restart point

## Latest checkpoint — September 29: r9 host, CI and exact-image checks

Current candidate: `image/r9-campus-network-20260929/luma-pi4-UNVERIFIED.img.xz`;
see its [handoff and receipts](image/r9-campus-network-20260929/README.md).
SHA-256 `77de4675402120626c167a7b393d595398d5facb44d5b23e0170626b9f0ba147`;
source fingerprint `42fbff0042504530c6dc0651a82fe30ef893009c2f059dca4390c330d8052`.
The exact 170-file/package/partition audits passed. The preserved compressed
archive matches its Linux raw disk build byte-for-byte. The r9 raw image then
passed two disposable QEMU-overlay checks: the installed `luma` user received
`{"volumes":[]}` from the peer-authorized backup socket; the Pi Connect setup
broker returned fresh-device status (`available=true`, `signed_in=false`,
`state=off`) after API/database health returned `ok`. Both emulators stopped
at the script's 180-second cap; these are targeted software checks, not proof
of complete or physical boot. `boot_verified=false` and
`hardware_qualified=false` remain correct. Backend regression: 957 Windows
passed, 32 Linux-only skipped; the full hosted Linux suite passed all 989.
Frontend: 124 passed and production build passed. Image-builder on Windows:
25 passed, 14 skipped for native Linux/systemd/symlink requirements.

GitHub Actions `Luma software checks` passed on commit
[`7a5a918`](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/36603151064),
including the complete Linux backend suite, frontend tests/build and image
builder/recovery tests. The hosted result does not cover r9 QEMU; those two
checks were run separately in Debian WSL. All-theme room-device and scene
interaction review is still incomplete. No Pi, SD or USB media was touched;
owner-directed physical/provider tests and flashing remain deferred.
The Levoit hotspot is opt-in, requires a second compatible USB Wi-Fi radio, and
must not be enabled on Stanford/venue Wi-Fi without explicit network-owner
approval. See [network policy and limits](docs/CAMPUS_NETWORK.md).

## Previous candidate checkpoint — September 29: r8 rebuilt and audited after USB discovery fix

The newest candidate is `image/r8-usb-inventory-20260929/luma-pi4-UNVERIFIED.img.xz`;
see its [handoff and exact receipts](image/r8-usb-inventory-20260929/README.md).
SHA-256: `b98feb293b431a360cb4240020250125f8b0133c5fb58e9341450e04054516b1`;
source fingerprint: `8ca82e2bc5ba71f9b3a882f6568d4fe8977d4e8c3b945880c47cffde930f796d`.
The candidate was independently re-hashed on Windows; XZ integrity, matching
root-partition/ext4-sidecar check, wireless/recovery package checks and the
exhaustive **170-file** exact-source audit passed. Two disposable QEMU checks
passed: the authorized Luma account received an empty USB inventory from the
backup socket, and Pi Connect's local setup broker returned fresh-device
status; API/database health responded too. Each VM stopped at its planned
180-second timeout after its required markers; this is emulation evidence, not
a real-device boot test.

The USB scanner fix accepts physically USB-attached storage based on USB
transport and sysfs ancestry instead of relying on the unreliable `lsblk RM`
bit, and rejects all sibling partitions on the physical system disk. Current
source verification: **989 Linux backend tests passed**, **957 Windows passed
with 32 Linux-only skips**, and focused inventory tests **8/8**. The unchanged
frontend suite (124), TypeScript/production build, and image-builder suite (39)
had passed on the preceding source checkpoint.

The build manifest says `boot_verified=false`; the raw-image audit says
`hardware_qualified=false`. The owner explicitly deferred physical testing:
do not flash or touch the connected Pi/SD until prompted. Physical USB-media
discovery/export/restore, display/touch/audio, campus networking, Levoit AP,
phone/provider setup and power-loss tests remain outstanding. The AP stays off
by default and still requires a separate compatible Wi-Fi adapter and campus
permission. GitHub publication remains pending the commit-author choice; no
commit, push, release or hosted CI run has occurred.

## Previous checkpoint — September 29: USB discovery compatibility/safety source fix

The portable backup scanner no longer requires the `lsblk RM` removable bit,
which some USB flash controllers report as false despite USB transport. It
requires USB transport plus USB sysfs ancestry and blocks every partition on
any physical disk backing `/`, `/boot` or `/boot/firmware`. Regression tests
cover both behaviors. Verification: **989 Linux backend tests passed**;
**957 Windows tests passed with 32 Linux-only skips**; the focused Linux USB
inventory module passed **8/8**. The full Linux run used a disposable WSL
environment with the Luma package installed. No USB hardware or SD card was
changed.

## Previous checkpoint — September 29: r7 candidate rebuilt and checked

The r6 image is preserved. At this checkpoint, r7 was the full-image
development candidate. It packages the signed-updater Windows portability fix
and the source then current, including the optional Levoit-forwarding AP. The local image
archive is `image/r7-updater-fix-20260929/luma-pi4-UNVERIFIED.img.xz` (large
image binaries are excluded from Git); see its [handoff and receipts](image/r7-updater-fix-20260929/README.md).
SHA-256: `ceb97a0140433765bd7d48bcc44a57fea66788b55af07fd3705af6dd7d6c9f1a`.
Source fingerprint: `aba921d1de6d6c3fffbe685ae5fc09dc824f0ade324a561fbec252714fd22c7d`.
Windows independently hashed the copied artifact; XZ integrity and checksum
passed. Matching source, raw-image/package, and 170-file byte-audit receipts
are beside it.

Verification: **957 Windows backend tests passed** (31 Linux-only tests
skipped), **988 Linux backend tests passed**, **124 frontend tests passed**,
TypeScript/production build passed, and **39 image-builder tests passed**.
The raw partition matches its ext4 sidecar; required Wi-Fi/recovery packages,
including `dnsmasq-base` and `firmware-realtek`, are present. Two isolated
QEMU runs passed the backup socket's authorized empty-inventory response and
the fresh-device Pi Connect setup response. The emulator's planned 180-second
timeout is not itself a pass criterion; both smoke assertions were observed.

The candidate intentionally remains `boot_verified=false` and
`hardware_qualified=false`. No SD card was flashed or changed. The Levoit AP
is off by default and needs a separate AP-capable Wi-Fi USB adapter while the
Pi's built-in radio stays connected upstream. Reusing the Luma PIN as Wi-Fi
key works only with an exactly eight-digit PIN; Stanford/venue permission and
real forwarding/pairing remain unverified. GitHub publication also remains
outstanding: the supplied `origin/main` has been fetched and an isolated
feature branch prepared, but no commit or push has been made while author
identity is being confirmed. Hosted CI has not run.

Next: owner-directed hardware testing when requested, including display/touch,
audio, campus uplink, a compatible second Wi-Fi adapter and Levoit enrollment.
Do not flash until the owner explicitly asks.

## Previous checkpoint — September 29: signed-updater Windows portability fix

A fresh full Windows backend run found that the GitHub release verifier and
root update broker reopened a `NamedTemporaryFile` while its writer handle was
still open. POSIX permits this, but Windows' default sharing rules reject it.
Replaced that with a private temporary directory and a closed staged bundle,
used for both signature verification and installer handoff. Focused updater
tests: **7 passed, 5 Linux-only skipped**. Full Windows backend suite:
**957 passed, 31 Linux-only skipped**. Frontend: **124 passed**; TypeScript/
production build passed.

This changed packaged backend source and required replacing the previous r6
candidate. The fresh-build, exact-file/package, checksum and QEMU gates are
now complete as recorded above. No SD card was touched.

## Previous checkpoint — September 29: optional Levoit internet-sharing hotspot

Implemented an opt-in `Luma-Devices` 2.4 GHz WPA2 access point for a compatible
Levoit purifier, using NetworkManager's separate subnet, DHCP/DNS and NAT to
the Pi's current default internet route. It is deliberately off by default,
local-dashboard-only, protected by the current Luma PIN for enable/disable,
and will not start unless it sees an active Wi-Fi uplink plus a separate
AP-capable physical Wi-Fi radio. The Pi 4's built-in radio remains on
eduroam/Visitor; a Linux-supported 2.4 GHz USB adapter is required. The image
recipe now includes Debian's `firmware-realtek` for relevant in-kernel USB
adapters and `dnsmasq-base` for NetworkManager's shared-mode DHCP/DNS, without
claiming compatibility with every chipset.

The owner can choose the exact Luma PIN only when it is eight digits, or a
separate 16–63 character ASCII Wi-Fi passphrase (recommended). The selected
key is persisted in NetworkManager's root-managed profile so it survives
restart; it is never returned by APIs or included in Luma backups. The PIN
mode exposes the PIN to anyone admitted to Wi-Fi, so the UI prominently warns
against this weak shared-secret arrangement. The custom passphrase is only
shown in the setup page session that created it; after reload it cannot be
retrieved through Luma.

Documented the important unknown: Stanford's public guidance does not
explicitly approve a personal NAT/router on eduroam or Stanford Visitor.
Sharing requires owner confirmation to ask Stanford/venue IT first. Visitor
also has a 12-hour session and service/port restrictions, so the Levoit cloud
onboarding could fail even if the Pi's browser got through its portal. No
Stanford approval, second Wi-Fi adapter, Levoit onboarding or physical
forwarding test is claimed.

Verification: **124 frontend tests passed**, TypeScript/production build
passed, changed Python files compiled, **5 image wireless-package tests passed**,
the full current-source Linux backend suite passed **988/988**, and the Linux
image-builder suite passed **39/39**. A fresh, isolated current-source
candidate is in `image/r6-current-20260929/`; SHA-256 is
`e82d2573426b3b05acd187836e293eccda045167fa8e30e49d083f2033122f42`. Its
source fingerprint matched (`1804a735b04a3a63f061d16d28c71f0faed57eddea1aadb7fcf6665d9b6581ed`),
XZ integrity passed, its Windows copy was byte-compared with the Linux
artifact, and the exact-image package/file plus exhaustive audits passed
(170 mapped Luma files, Wi-Fi packages, Pi Connect/update brokers). In
disposable QEMU, the protected backup socket returned `{"volumes":[]}` to the
authorized Luma user. A second isolated run verified API/database health and
the Pi Connect setup broker's fresh-device status (`available=True`,
`signed_in=False`, `state=off`) without enrollment. Each emulator reached its
planned 180-second bound (status 124) after its smoke assertions passed. The
candidate manifest still says `boot_verified=false` and
`hardware_qualified=false`.

The attached SD card was not changed or flashed. At this earlier checkpoint,
WSL was the authoritative backend test environment. The following updater
change supersedes its source fingerprint and requires a new image before the
Pi's signed application release can include it.

Older checkpoint entries below are retained as history. Any phrases such as
“next image,” “must be included,” or “not yet wired” describe that earlier
state and are superseded by the September 29 r7 checkpoint above.

## Archived checkpoint — September 29: final-image feature scope and arcade completion

Owner confirmed that this in-progress Luma release should include Pi Connect
and be the final planned full OS flash. Treat this as the final *routine*
image: include the Pi Connect recovery/enrollment UI and broker, GitHub-backed
Settings updater and protected broker, current Wi-Fi fix, and all accepted
Luma features together. Later ordinary feature releases should use signed
`.lup` assets attached to stable GitHub Releases, preserving settings and
enrollment; the Pi verifies the image-pinned key and never executes a raw Git
branch checkout. The private signing key remains on WSL, outside GitHub. Do not
flash until backup/restore and immutable-image qualification gates below pass.

The source now has a Settings update card that checks the public repository's
latest `main`-targeted stable release, verifies the downloaded bundle and
shows release notes before explicit install confirmation. A root-owned
socket-activated broker re-verifies and hands the bundle to the existing
atomic/health-checked installer, surviving the dashboard restart. Added
GitHub-release metadata, checksum, signature, downgrade, local-only API,
review-token, broker, and systemd package tests. Verification: **977 backend
tests passed**, **124 frontend tests passed**, TypeScript/production build
passed, and the updater systemd packaging checks passed. This source must be
included in the next fresh full image. GitHub Actions run #14 passed on feature
commit `64f2ce2`; no release was signed/published and nothing has been
installed on the Pi.

Completed the requested Space Invaders interlude as an autonomous classic game
in all three themes. Its 55-invader formation reverses and descends, both sides
fire, the ship glides at constant speed and turns only after a short cooldown,
hits score by row, cleared waves preserve score, and a formation breach
redeploys remaining invaders without spending lives. Only zero lives ends the
run; a true loss restarts it while keeping best score. Bullet avoidance now
checks each shot across the full vertical collision window and runs after
ordinary steering, so a newly expired turn cannot send the ship into a bullet.
It preserves a safe heading and rejects a needless reversal when both routes
are equally threatened. Neon Grid uses a visible 32×20 subdivision and the
same master-grid rules as the Arcade scenes. Game state is versioned and
included in browser/portable encrypted backups. Frontend suite: **124 passed**;
TypeScript and production Vite build passed. Rendered-browser checks and the
fresh final-image build/boot checks remain release gates; no hardware has been
flashed or tested by Codex.

## Previous checkpoint — September 29: arcade continuity refinements

Implemented the requested modest Pong speed increase as an **8% ball-only**
change. Serve pace and the ball cap rise; receiving paddle speed, acceleration,
reaction delay and turn-taking remain on the existing tempo. Checkpoint format
advances to v4 and migrates v2/v3/older active games once, preserving rally
score and paddle state. Tetris code/timing is untouched. Also made the Arcade
Snake board's 32×20 motion cells visible as Neon Grid subdivisions. At that
checkpoint the frontend suite had **114 passing tests** and TypeScript/build
passed. The Snake board was checked at 1280×720, 2048×1536 and 390×844 with no
horizontal overflow.

## Archived checkpoint — September 29: Pi Connect in the final planned OS image

Owner clarified that the currently prepared Luma update should be the final
planned full OS flash—not that Pi Connect should be deferred to a later image.
Release gate: build Pi Connect, its owner-controlled touchscreen enrollment,
the recovery account, and the signed app updater into this same full image.
Subsequent routine Luma features are intended to ship through signed app-only
updates, preserving settings and Connect enrollment. A later OS/security or
hardware-platform change could still require an OS image. The backup/restore
gate remains mandatory before flashing anything over the current card.

## Pi Connect implementation checkpoint — September 29

The currently installed card still has **no supported on-screen Pi Connect
enrollment**, and SSH is not usable on Stanford eduroam. Do not try to find a
Pi Connect toggle on that old Luma screen. The upcoming full-image source now
adds **Device setup → Connections → Raspberry Pi Connect**: the owner signs in
through Raspberry Pi's one-time verification URL (shown as a local QR), then
separately enables the dedicated `luma-admin` remote shell. Screen sharing is
kept off; the setup broker accepts only fixed actions from the local Luma API;
the Connect user lingers across kiosk logout/reboot. The owner must approve the
link and shell explicitly. Pi Connect still needs working Internet, and a
restrictive campus firewall could block it.

This is **source only** so far, not a new image or hardware-tested recovery
route. The signed app-only `.lup` cannot install base OS packages, accounts or
systemd units, so it cannot add this capability to the currently installed
image. A full OS reflash erases on-card settings; do not reflash until backup
and restore are verified (the user's USB drive is not currently detected).
The exact-file checker now compares `pi_connect_setup.py` in the installed
release, and its receipt reports the broker verification. Native Debian
`systemd-analyze verify` plus installer syntax tests pass (**3 passed**); the
Windows image-builder suite passes **19**, with **13 Linux-only checks
skipped**. This validates unit syntax, not activation under the packaged user
or real `SO_PEERCRED` flow. Pi Connect focused backend tests: **40 passed**;
frontend: **112 passed**, production TypeScript/Vite build passed. Next: run
the Linux broker/socket peer-auth integration, build a fresh immutable image
from the current sources, and perform exact-file/QEMU checks. Physical
enrollment, eduroam compatibility and access are unverified.

Latest hardware-driven diagnosis — September 28: the owner confirmed that
stock Raspberry Pi OS on this same Pi sees nearby Wi-Fi networks, while the
Luma image did not. The retained candidate SBOM contains NetworkManager and
Broadcom firmware but not `wpasupplicant`; Debian marks the supplicant as a
NetworkManager recommendation, and the minimal image drops recommendations.
This is the leading concrete OS-level cause. The source image recipe now adds
`wpasupplicant` explicitly and adds the official `rpi-connect` package for
owner-authorized recovery access (left unlinked/off by default). The Wi-Fi
scanner now waits for NetworkManager `LastScan` completion and reports radio,
scan-timeout and empty-result cases separately. Historical candidate images
are unchanged and should not be reflashed to test this fix. Focused tests:
22 backend/image-package tests passed; frontend **112 passed** and production
TypeScript/Vite build passed. Fresh candidate:
`image/luma-pi4-wifi-fix-20260928-UNVERIFIED.img.xz` (SHA-256
`ed988cc43b57f657575e1297f707af15a87c0879f48f57b57db4c132dc569d32`). Its
raw root partition and all 162 audited Luma files match their staged inputs;
the image contains both `wpasupplicant` and `rpi-connect`. Disposable QEMU
reached the graphical target and Luma's API/database health check passed. This
is not physical qualification: `boot_verified=false`, and the actual Pi Wi-Fi
scan, touch/display and complete hardware acceptance remain for owner testing.
Raspberry Pi Connect is packaged but still needs working Internet and owner
enrollment; it cannot diagnose the offline Wi-Fi issue until connectivity works.

Latest continuation checkpoint — September 28: the fresh r5 Raspberry Pi 4
candidate has been built from current application inputs after the backup
broker cold-import fix. Exact-image QEMU activated the shipped backup socket;
the unprivileged installed `luma` client received `{"volumes":[]}` at 63.4 s.
The bounded QEMU process then ended at its planned 180 s timeout (exit 124);
the test's response assertion passed. The raw root partition matched its
ext4 sidecar, all 161 audited shipped Luma files matched staged inputs,
native ARM64 binaries passed architecture checks, source fingerprint
`7db318e9bd32d031842bf6c68c538f0ebdef2a9e39b5b7a7a0a091b2a8779241` matched,
and XZ/checksum verified (SHA-256
`63de5c349abc1a76031fe6e8e07b067ff103ca82c80c5e810f08f29ac122c57c`). The
Windows handoff copy is `SD Card/image/luma-pi4-r5-UNVERIFIED.img.xz`; the
older r4 file was preserved. This is ready for owner-directed hardware
bring-up, not a hardware-qualified or v1 release: manifest correctly retains
`boot_verified=false`, `hardware_qualified=false`. Owner will flash with
Raspberry Pi Imager. Run `docs/HARDWARE_VALIDATION.md`; capture first-boot,
display/touch/audio/network and recovery findings before changing or replacing
the candidate.

The September 28 animation requests (all-theme persistent Space Invaders,
visible Arcade Snake subdivisions, and a modest Pong ball-only speed increase)
were recorded at that time. Those software changes are now complete; see the
September 29 checkpoint above. Tetris retains its existing gradual score-based
speed ramp and current curve.

Latest continuation checkpoint — September 28: resolved the mystery behind
the r4 backup-broker timeout with an exact-image faulthandler capture. The
root broker was spending its cold start importing `backup_media →
portable_backup → scenes → fans → room → purifier_adapter → pyvesync`; the
`pyvesync`/Mashumaro model compilation was still in progress when the client
timed out at 60 seconds. This was not a socket-accept loop or a systemd
syscall-filter denial. Split the bounded encrypted-container constants and
fixed-cost envelope validation into lightweight `backup_envelope.py`, then
made broker/media import that module instead of the portable settings
serializer. Added a fresh-process regression that asserts broker import does
not load scenes or VeSync SDK modules. Windows backup-related tests: **18
passed, 17 Linux-only skipped**; Debian backup socket/media/inventory suite:
**35 passed**; complete Debian backend suite: **943 passed**; image-builder
unit tests: **26 passed**. The fix and ledger are published on the authorized
feature branch at commit `1e86b4b`; GitHub Actions run 36506577393 passed. The
immutable-image QEMU response still needs to pass on a rebuilt r5; r4 remains
**not ready for reflash**. Exact-image stack evidence is in the September 28
`PROGRESS.md` entry.

Latest continuation checkpoint — September 28: implemented the signed,
in-place application updater requested for future development. Fresh image
version 0.2.0 will install into root-owned `/opt/luma-releases/0.2.0` behind a
stable `/opt/luma` pointer; the update public key is pinned at
`/etc/luma/luma-update-ed25519.pub`. The corresponding Ed25519 private key is
only in the Linux build home at `/home/luma-build/keys/luma-update-ed25519.pem`
(0700 directory/0600 file); never copy it into the project, image, Pi or CI.
Updater documentation: [UPDATE_DEPLOYMENT.md](docs/UPDATE_DEPLOYMENT.md).

The signed bundle route is app-only (Python wheel, dependency declaration,
compiled frontend and bundled attribution notices); it rejects dependencies
or durable-data schema changes, validates signature/manifest/wheel, stages a
separate version, preserves `/var/lib/luma`, serializes updates, fsyncs before
switch, health-checks and rolls back on failure. A real signed 0.2.0 test
bundle was built and verified against the pinned public key (31 payload files;
not applicable to the already-written card). Linux updater suite: **8 passed**,
including pip installation in a disposable real venv, a post-rename generated
console-script invocation, signature/tamper checks and atomic rollback. The
complete backend suite is **942 passed on Linux in hosted CI** and **912
passed / 30 Linux-only skipped on Windows** (one existing Starlette/httpx
warning). The fresh Windows run took 206 seconds. Frontend: **112 passed**;
TypeScript/production build passed (`index-DgQv9Dlb.js`,
`index-CjCfDND2.css`).

The source, documentation, and CI workflow are published on the authorized
feature branch
[`codex/luma-updater-ci-20260928`](https://github.com/BrianBGoldshtein/LumaSmartHub/tree/codex/luma-updater-ci-20260928)
at commit `c613252`. GitHub Actions run
[36488243784](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/36488243784)
is green: complete Linux backend suite, checksum-pinned asset preparation,
frontend tests/build, and image-manifest tests all passed. It confirms **942
backend tests** on Ubuntu. The focused Linux updater suite passes
**8/8**, including a real venv relocation/entrypoint check. Neither CI nor the
repository contains the update-signing private key.

**Latest r4 image result:** the immutable Pi 4 image has been built at
`/home/luma-build/luma-final-20260928-r4/image/luma-pi4-UNVERIFIED.img.xz`
(SHA-256 `3acfdaccca4b3dd74eb92f577eea951791454cbb709ac61adb6eb0f1a66dcf70`).
Its source fingerprint is
`770906ac80b3efc86dfea19bcee93b2b7e7930d7966c22ab65a577a0e6908921`;
the source manifest, embedded root-filesystem comparison, exhaustive
161-file audit, approved recovery public key and API/gateway/Tailscale
offline-QEMU checks passed. However, exact-image QEMU testing does **not**
qualify the USB backup service: the socket listens and activates
`luma-backup.service`, but an authorized `luma` client receives no response
within 60 seconds. Do not copy this image into the SD handoff folder or flash
it until that packaged service integration is fixed and revalidated. QEMU is
software evidence only; hardware remains owner-prompt-gated. The rejected r2
candidate omitted the approved public recovery SSH key and must not be used.
Never overwrite the owner's existing SD.
Updater deployment itself remains untested on a physical Pi. Narrow/portrait/
touch, actual Pi/phone/appliance/campus network tests remain owner-gated.

Latest continuation checkpoint — September 28: added two production FastAPI
lifespan integration checks. A synthetic Google fetch verified merged
agenda+Sleep calendar IDs and drove one selected-calendar `Sleep` boundary to
the durable Night journal. A fake BlueZ manager verified that a connected phone
remains unknown until fresh authorized-session evidence, and that startup
presence is a baseline, not an Arrive event. Device dispatch, Google and BlueZ
were all synthetic; this is not owner-account, radio or appliance acceptance.
Focused scene-runtime suite: **12 passed on Windows and Debian Linux**. Latest
complete current-source Debian backend suite: **934 passed**. Windows complete
suite: **909 passed / 25 Linux-only skipped**; the final changes after that run
were test-fixture timing/clock determinism only, with the current 12-test scene
suite rerun on Windows. Warnings were existing Starlette/httpx and dbus-next
deprecations. The earlier 963 WSL figure below was stale and is superseded by
this fresh complete run.

September28 recheck after fan-UI QA: full Windows backend **909 passed / 25
Linux-only skipped** in117.89s; frontend **112 passed**; TypeScript and Vite
production build passed with `index-DgQv9Dlb.js` and `index-CjCfDND2.css`.
Warnings remain the existing Starlette/httpx deprecation and Vite callback
timing notice. This confirms the current Windows-visible suite, not the skipped
Linux peer-credential, sysfs and removable-media integration cases or ARM64.
September28 escalated Debian rerun now confirms the full Linux suite: **934
passed in100.51s**, including the Linux-only peer-credential/socket, sysfs and
removable-media cases. Warnings were the existing Starlette/httpx and dbus-next
deprecations plus pytest being unable to write its optional cache under the
workspace mount. No failures. This is x86-64 Debian integration evidence, not
ARM64 or real Pi qualification.

Purifier UI follow-up — September 28: a real rendered Hearth/Glass/Neon browser
pass with the synthetic provider checked offline refresh, provider rate limit,
failed re-login, retained credentials/device selection, and a long custom name.
At1280×720 the label wrapped in two lines without horizontal overflow in all
three themes. Offline state explicitly became “Saved reading · check needed”
after local refresh and disabled controls; rate limit displayed its wait
message; failed re-login cleared the entered password and left the previous
selection/session intact. API output excluded the fake password/token/account
sentinels. No owner account, appliance, USB, Pi or SD was contacted. This is not
narrow/portrait/touch or full error/recovery acceptance; see
`docs/ROOM_DEVICES.md`.

Fan API integration follow-up — September28: new `fan_preview.py` and
`fan_live_check.py` exercise the real fan API, durable store/runtime, and
WebSocket using a fake transport and temporary SQLite. Discovered/selected two
separate emitter routes, learned and observed a synthetic absolute button in
both outputs, and verified scene eligibility only after independent evidence.
A simulated transport failure left a durable `unknown` receipt and exposed no
sentinel; competing work returned429 while learn was busy; explicit cancel
returned409 and did not save the late button. WebSocket remained privacy-
redacted and carried no waveform or error sentinel. PASS; current Debian
`tests/test_fans.py`:30 passed. No USB, remote, appliance, Pi or SD was
contacted. This is not broker/systemd/udev, ARM64, touch or physical fan
acceptance. See `docs/ROOM_DEVICES.md` and `docs/IR_DEVICES.md`.

Rendered fan setup — September28: Hearth at1280×720 against the same temporary
production-API/fake-IR fixture saved and rendered both fan labels, including a
40-character name. Synthetic USB unavailability explicitly promised no retry.
Learning and the one-shot test each required separate operator confirmation;
the test UI then requested both-fan observation, which was deliberately left
unconfirmed. A blocked learn was cancelled from the UI; after reload, fixture
state confirmed cancellation count1 and no late `On` button persisted (fan1
still had only the earlier `Off` button, at0/2 checks). No synthetic result was
misreported as a real fan observation. A separate transport-exception path
showed a fixed error; restoring the fake transport and reloading cleared the
error with no automatic retry or newly saved `On` button. This covers one
theme/viewport for interactions. The overview and Buttons & controls pages fit
1280×720 in Hearth, Luma Glass and Neon Grid without document overflow. Narrow
and portrait layouts, touch, full keyboard/pointer coverage, reconnect and
physical gates remain. Details in `docs/ROOM_DEVICES.md`.

Additional room-scene preview QA: list and action-editor layouts fit three
themes at2048×1536,1536×2048 and390×844. Scene-card status text measured only
1.2–1.5:1 contrast; corrected it to bold22.4px inherited card ink. Final nine
theme/size readings are9.83:1 minimum. Pointer Add/Review/enable, keyboard
Sleep-trigger, default-off and discard-confirm flows passed in preview. These
checks used sample data only; provider error/reconnect, long-name edge cases and
physical touch are not thereby accepted. Frontend112 tests, TypeScript and the
final Vite build passed (`index-DgQv9Dlb.js`, `index-CjCfDND2.css`).

Latest continuation — September 28: added a disposable real HTTP/WebSocket
scene release fixture and live check. Production APIs exercised default-off
scenes, binding-checked save/reload, stale revision rejection, one durable
manual run with a factual synthetic outcome, exact remote consent,
edit-invalidated consent, authenticated remote rejection, and storage-object
reconstruction from temporary SQLite. A real WebSocket delivered the scene
update without raw IR bytes. Result: PASS. The local dispatcher was replaced
with a synthetic fake; no USB, account, provider, appliance, Pi or SD card was
touched. Existing Debian focused scene suite: 12 passed. This strengthens
backend integration evidence only; it does not qualify browser error/stale-
review states, physical touch, real hardware, or the packaged image. Reproduction
fixtures are in `source/backend/tests/scene_preview.py` and
`scene_live_check.py`.

Rendered follow-up — Hearth scene setup in the temporary synthetic server:
saved one enabled Night action, explicitly confirmed a manual run, and verified
the per-device “Unconfirmed · check device” result. Granted the separate exact
remote permission, changed the saved action and confirmed the old grant stayed
ineffective and appeared as “local review required”; the UI did not silently
regrant it. This spot check covers one theme/viewport and the basic result/stale
label only. Long-name, provider/disconnect/error/recovery, other-theme and real
touch cases remain.

The scene remote-permission
path now exists in source as a distinct local-owner grant for exact saved
scene/action/device-binding bundles. The restricted iPhone Shortcut gateway
can run only a fresh, locally reviewed, explicitly allowlisted scene; later
scene edits/relinks invalidate the permission. Permission state defaults off,
is recoverable without altering local scenes, exposes no private calendar or
device state, and does not route SSH/main API access through Tailscale. Scene,
voice and gateway regression set: **196 passed**. Frontend suite: **112
passed**; TypeScript/Vite production build passed. Linux-only media, sysfs and
peer-credential cases ran in Debian. The installed Luma wheel is older, so the
full Linux suite explicitly selected current workspace source. The Linux-only integration pass covers the temporary Unix-socket
broker → backup API → encrypted media/restore path. A small
theme-alignment change made the permission-panel heading use the theme heading
font and removed its misleading inert default-off button. See
[SCENES.md](docs/SCENES.md) and [TAILSCALE.md](docs/TAILSCALE.md).

The complete expansion is still active. The already-written commissioning card
is older and must not be overwritten. No one-click source updater is built or
qualified; any eventual updater must keep authenticated integrity checks,
atomic version switching, health checks, rollback, and all private/settings/game
data untouched. Do not expose administrator SSH through the restricted
Tailscale app gateway.

**Still outstanding:** complete fan/purifier credential/error/reconnect and
long-name UI qualification; finish scene error/result/remote-grant stale-review
states and real touch acceptance; qualify authenticated-phone scene triggers through actual
BlueZ/ANCS and packaged service behavior (FastAPI lifespan paths for selected
Sleep and fake BlueZ authorization now have synthetic integration tests); verify real systemd socket activation and appliance
service UID for the USB broker (native unit syntax and the image audit map now
pass); complete ARM64/exact-image/static/real-WebSocket release gates; refresh
the immutable image/checksum/provenance and write a final wiring/flashing/
recovery guide. Provider/device/physical checks remain owner-gated. Feature
scope and accepted behavior remain in [the expansion plan](docs/EXPANSION_PLAN.md),
with room gates in [SCENES.md](docs/SCENES.md), [ROOM_DEVICES.md](docs/ROOM_DEVICES.md),
and backup gates in [PORTABLE_BACKUPS.md](docs/PORTABLE_BACKUPS.md). The latest
Hearth synthetic browser check exercised the two-output fan learning/test/
observation path, including the repeated-state gate; it used no hardware. Error,
reconnect and real touch checks remain. Hardware testing remains deferred until
the owner prompts.

## Active full expansion goal — September 28 (supersedes the older commissioning pause)

Owner resumed implementation and software testing of the selected expansion
features, and asked for a *new prepared* SD image only after the work is ready.
The card already written on September 28 contains the earlier commissioning
candidate; do not overwrite it now and do not treat it as the final expanded
image. Physical Pi, panel, ReSpeaker, campus-network and appliance tests remain
deferred until the owner explicitly prompts. The ultimate delivery must include
a fresh immutable image, checksums, ARM/package/real-WebSocket qualification and
the final wiring/first-boot/SSH/reflash guide. Preparation does not authorize
writing the new image to the owner's SD card.

### Historical checkpoint — portable backup foundation (superseded by the September 28 test record above)

Added `portable_backup.py` with a strict allowlist, AES-256-GCM authenticated
encryption, bounded scrypt parameters, validated archive/document schemas,
unlinked conversion for Google countdowns, disabled/review-required scene
intent, and one-transaction database restore. Existing account secrets,
calendar links, appliance bindings, phone pairing and a stricter microphone
mute survive import. Added `backup_media.py`, USB identity inventory and the
root-owned peer-checked broker/systemd socket. At this earlier checkpoint,
the owner API and UI were still outstanding; see the current test record above
and [PORTABLE_BACKUPS.md](docs/PORTABLE_BACKUPS.md) for the completed source path.
Current audit: [PORTABLE_BACKUPS.md](docs/PORTABLE_BACKUPS.md).

Evidence: **903 complete backend tests passed on Ubuntu WSL** before the latest
broker additions. New targeted backup tests pass **30/30** on Ubuntu WSL.
Windows backup-media skips are not counted as Linux passes. Separately the complete scene/device integration
set passed **142 tests** (session 55701, exit 0, 23.72 s). The expanded portable
archive/scene round-trip was included in the 101-test run. No provider account,
USB disk, appliance, Pi, SD card or image was changed.

The earlier WSL setup notes are historical. Ubuntu WSL now runs the current
full backend suite; its latest result is recorded in the opening checkpoint.

Next: complete USB root broker and actual verified Linux inventory, local API
and touch-first UI; validate/reload import against live service references;
perform scene/fan UI and all-feature regression QA; finish the remaining remote
and native voice appliance action contracts; run full backend/frontend builds
and scene-specific synthetic HTTP/WS/browser checks; then execute Linux/ARM/
real-packaged-WS image gates and prepare a *separate versioned image*. Preserve
Tetris timing, games, saved mute/privacy and the already-written card. Do not
claim physical qualification or end the active goal until every selected
feature and final delivery requirement has direct evidence.

## Existing card and deferred first-boot work

The candidate then written to the card was `image/commissioning-20260927/luma-pi4-UNVERIFIED.img.xz`. Raspberry Pi Imager visibly reached **Write complete** for Raspberry Pi 4 and automatically ejected the selected SDXC card. This is an imaged card, not a physically boot-qualified device, and it predates the currently requested final expansion image.

Next: owner is waiting for a micro-HDMI-to-full-size-HDMI adapter; there is no Ethernet cable. The parts brief identifies the Pi output as micro-HDMI and the Thinlerain 9.7-inch monitor input as **mini-HDMI**. A micro-to-full-size adapter alone will not mate to the monitor unless there is also a full-size-HDMI-to-mini-HDMI cable/adapter; one micro-HDMI-to-mini-HDMI cable is the direct alternative. Confirm the connector ends on the arriving adapter/cable before first boot. On the Pi use **HDMI0** (labelled on the board) for the display; the Pi USB-C socket is power input and does not carry video. Connect the panel's touch-data USB separately to a Pi USB-A port, and power the panel as specified by its own label/manual. Check the Pi supply label too: official guidance for Pi 4 is 5 V/3 A; the project's original brief asked for at least 3.5 A. Then power the Pi and complete local onboarding on-screen; Stanford Visitor terms and/or Stanford eduroam setup still require owner interaction. Do not enter personal Google/device credentials until the local display and network path are checked. Hardware, display/touch, Wi-Fi/captive portal, sound, microphone, Bluetooth/iPhone, power-recovery and integrations remain untested.

Possible adapter workaround: if a standard HDMI TV/monitor is available, the arriving micro-HDMI-to-full-size-HDMI adapter plus an ordinary HDMI cable can be used for initial boot and network setup. A USB keyboard/mouse can stand in for touch on that temporary display; the actual Thinlerain picture, touch alignment and rotation must still be checked later using its mini-HDMI input and touch-data USB connection. Laptop HDMI is generally an output, so use a TV/monitor with HDMI input.

Before first power-on, fit the specified ReSpeaker 2-Mics Pi HAT **V1.0 / WM8960** only with the Pi's USB-C power fully disconnected. Carefully align the 40-pin header and check it is not offset; do not hot-plug the HAT. The Seeed V1 board has onboard microphones and WM8960 audio codec; its extra micro-USB power input is for supplying additional current when using a speaker, not the Pi's video connection. The image's HAT overlay is V1-specific, so verify the board's printed revision before powering on. See the [Seeed board overview](https://wiki.seeedstudio.com/ReSpeaker_2_Mics_Pi_HAT/).

The September 27 commissioning record has build and software evidence. Physical assembly and first boot remain deferred. The detailed paragraphs below are chronological historical development notes and can conflict with current source; use the dated active-expansion checkpoint above, inspect live source/tests, and update this file after each meaningful implementation or verification gate.

Earlier scene-foundation-only text below is historical: local scene API/runtime/presence/adapters/UI now exist in current source, but optional extras are not fully qualified and remain disabled by default. Current image work packages the existing baseline without claiming incomplete scene extras, encrypted USB backup or physical acceptance complete. No existing historical image should be flashed as the current baseline.

## Latest checkpoint — scene foundations tested; production integration next

Read docs/SCENES.md before continuing. Source now has `scenes.py` (four empty disabled definitions, separate automatic opt-in, bounded strict absolute actions, revision-bound durable execution journal), `scene_triggers.py` (boot-local authenticated-presence debounce and fresh selected-Sleep boundary monitors), and `scene_executor.py` (injected sequential dispatcher, per-step durable unknown-before-I/O, no replay, revocation/cancellation/partial outcomes,120sec run/30sec dispatch/2sec cleanup, retained stuck-child handle and fail-closed restart requirement). These are **not yet wired to production device adapters, service workers, API or scene UI**. Do not claim scene feature complete or silently activate automations.

Fixed purifier one-hour manual override persistence in room.py: independent deadline survives selection/account changes; legacy receipt migration preserved on next edit; receipt+override commit atomically before send; internal scene claims cannot override active manual control and do not extend it. Updated storage-failure test to inject at the real transaction boundary rather than the formerly used set_cache helper. Added mid-transaction rollback, corrupt/migration/reconnect cases. No real provider/device access.

Verification this turn: full Windows backend **855passed/8Linux-only skipped**, session89591 terminal0,88.88sec, existing Starlette/httpx warning. Then one additional clock-trust regression plus explicit clock fixture correction: all27room tests passed Windows, terminal0. Linux Debian **128passed** across71scene+27room+30fan tests, session51079 terminal0,9.34sec. No real devices: injected dispatch/HTTP/IR only. Frontend **107passed**, TypeScript and Vite production build terminal0; unchanged final hashes index-rjWahl3Q.js/index-Ck8v9jgk.css. No visual source changes or new browser QA this turn. All test/install/build handles terminal; no image/fixture job launched.

Linux qualification environment initially lacked pyvesync; installed already-pinned3.4.2 into /home/luma-build/qualification/venv with its dependencies. Detected preexisting websockets17.1 outside source range, aligned to16.1.1; pip check now clean. A version-range shell quoting attempt failed before pip; its identified empty accidental '=15,' workspace file was removed, then exact-version install succeeded. Initial Linux room tests had two Windows-clock assumptions; corrected only test inputs and added explicit untrusted-clock/PIN-denial regression, no production clock weakening. These tests use current source via pytest pythonpath; installed Luma wheel in that venv remains older and must be rebuilt before installed-module/image qualification. This is x86 Linux testing, not ARM/physical acceptance.

Recovered/documented the previous uncheckpointed fan implementation: fans.py/fan_runtime.py/fan_api.py and FanSetup/fanState/Extras/onboarding hooks already exist and47fan/onboarding tests were rechecked this turn. Bounded owner-local setup, both-direction/repeated-state proof, durable unknown receipts, no-serial boot-local review flags and request-disconnect cancellation. Demo/browser evidence and specific unverified cases are now in ROOM_DEVICES.md. Do not repeat transport or fan foundation work because historical sections below say unwired. Fan realHTTP/WS/browser and complete all-theme/keyboard/error/pointer checks remain; no physical fan qualification.

Next concrete work: production scene dispatcher with server-minted device bindings, current fan proofs + no-serial review, serialized existing runtimes, current capability/configuration/source guards and1h manual overrides. Connect monitors to authoritative Bluetooth session evidence (not cached UI phone_connected/PIN/Tailscale) and fresh selected-calendar Sleep intervals, with no missed-run replay. Then owner-local API, themed sequential scene editor/review/results, manual/native-voice integration and separate remote action/device opt-in allowlists. See SCENES.md for exact constraints. Feature10 encrypted settings-only USB, a NEW immutable Pi image/ARM/exact-file/realWS qualification and final wiring→laptopSDreader→confirmed-target flash→firstboot/network/key-onlySSH guide remain required. Existing image still outdated, do not flash. Hardware testing remains deferred until owner prompts; preserve frozen Tetris/game saves/mute/privacy. Last research turn and this implementation turn are concrete progress; full goal active, no blocker.

## Latest checkpoint — USB IR transport source qualified; fan workflow next

Read docs/IR_DEVICES.md for exact boundaries/evidence/next steps. Added strict ir_protocol.py and unprivileged ir_broker.py around corrected ir_signal.py/ir_linux.py. No silence-as-complete capture; explicit real delimiter, bounded stale drain, repeated USB identity check, no guessed carrier. Fixed isolated child command with deadlines, bounded reap/late-spawn cleanup and fail-closed stuck-worker state. One global operation/no queue, peer UID check, disconnect cancellation, strict one-message16KiB IPC, no automatic retransmission and only unconfirmed/unknown sends. Linux-specific client reports unavailable on Windows. NO room store/API/UI/scenes wired, NO physical devices used.

Source installer now creates dedicated luma-ir system account/group, installs USB-only72-luma-ir.rules and dormant socket-activated service; interactive/API luma is not in hardware group. Gateway masks IR socket. Exact image-file audit map includes new units/rule. No installer or host service was run. No image regenerated. Docs record no-serial identity limitations, protocol/semantic/independence gates and production sandbox/ARM/physical validation still outstanding.

Verification: full Windows backend750passed/8Linux-only skipped(session65688 terminal0,77.63sec; existing Starlette/httpx warning). WSL Debian73IR tests passed including all8Linux-only tests,4.51sec; real Unix sockets/kernel peer authorization plus synthetic sysfs/ioctl/IR and installed-worker invalid-action check (no discovery). New IR packaging4Linux tests passed with native systemd/udev/bash syntax validators; gateway packaging4passed. Existing frontend103pass/build remains applicable, frontend unchanged. No test/image/fixture jobs remain running. WSL access needed approved escalation; distro Debian/qualification venv confirmed, not reinstalled. Current wheel installed with --no-deps into /home/luma-build/qualification/venv; not final dependency/ARM qualification. Early test failures were missing Windows asyncio Unix-function mock attribute; corrected and all rerun. Early WSL cache warning avoided with no:cacheprovider; no functional failure.

Next: implement durable two-fan slots/learned commands/semantics and revision-bound independent-reception proof; owner-local bounded learn/test/cancel API and themed guided setup, no fake working controls while hardware missing. Then empty disabled Morning/Night/Arrive/Away scenes with authenticated-presence debounce/cooldown, durable at-most-once claims, per-device1h manual overrides, voice and separate remote allowlists. Preserve purifier privacy/freshness/override contract and finish its remaining UI checks. Feature10 encryptedUSB, new immutable image/ARM+exact-file+realWS gates and final hardware guide remain. Hardware input is a setup gate, NOT a blocker to remaining software work. Previous research turn and this implementation turn both made concrete progress. Goal active/incomplete; preserve game saves/frozen Tetris/mute; no hardware testing until requested.

## Latest checkpoint — owner requested cheap hardware research

Paused feature9 implementation to research additional hardware at owner's request. See docs/HARDWARE_ADDITIONS.md for sourced prices/caveats. USB IR preferred over adding campus Wi-Fi clients; exact Woozoo models/codes and independent-control requirements remain purchase gates. Irdroid v3 EUR32 is a ready-made candidate, NOT verified independent-channel control; custom USB Pico dual-emitter option needs firmware/circuit work. BroadLink promo prices are not checkout/compatibility proof. Iguanaworks has closed despite stale store listings. No purchases, enrollment or hardware tests performed.

Immediately before this research, new backend src/luma/ir_signal.py and ir_linux.py were drafted. They are UNTESTED/UNWIRED foundations, not qualified features: bounded pulse/carrier parsing; Linux USB-only /dev/lirc discovery with opaque IDs; single-frame learn and one-shot send; strict actions. No broker, systemd/udev, store/API/UI or tests added yet. Do not expose worker directly: parent process deadlines/peer authorization are still required. Review stale receive buffers, frame termination, hotplug identity checks, ioctl capabilities and selected adapter driver before integration. A Pico transport would require a different adapter/firmware, not automatically work with this LIRC draft. Previous685backend/103frontend pass applies to purifier checkpoint, NOT these new IR files. Existing image remains outdated; full goal incomplete. Preserve frozen Tetris/game saves/privacy/mute; hardware tests deferred.

## Latest checkpoint — purifier runtime, API and themed local setup

Feature9 now has `room.py`, `room_runtime.py`, `room_api.py`, service/lifespan/private snapshot hooks, `RoomSetup.tsx`, `roomState.ts`, `room.css`, Extras entry and non-secret onboarding review fields. Saved session/selected-device/revision/generation/unknown-command receipts survive restart; no replay.120sec selected-only polling/backoff/auth-stop; credential-safe local API; owner/config rechecks after awaits and immediately before physical dispatch. New stale-revision failure guard and auth-discovery failure handling, privacy403, cancellation/busy/disk-failure cases. No real VeSync account/appliance activity. Read ROOM_DEVICES.md before extending; feature9 still incomplete, fans/scenes/voice/remote opt-ins not dropped.

Evidence: **full685backend** passed(session72318 terminal0,72.23sec, one existing Starlette/httpx warning), including34adapter+22room tests. **103frontend** passed; TypeScript/build terminal0. Final build after adding30sec UI deadline and all six reported fields: JS `index-yQgI5n12.js`, CSS `index-DHizXJyT.css`;4room frontend tests rechecked terminal0. Real disposable HTTP/WS fixture `tests/room_preview.py`/8750 used temporarySQLite and MockTransport with actual pinned library. Browser masked login→discovery→named selection→reload, dirty/discard, confirmed vs unconfirmed command readback, WS privacy-unmount and explicit disconnect passed. `room_live_check.py` passed terminal0 with no unintended commands and no secrets in config/review.9control layouts across3themes×landscape/portrait/narrow fit; stale viewport captures rechecked by actual DOM dimensions. Pointer actions were unreliable in browser tooling; keyboard flow passed. Further credential-keyboard/review/long-name/error/pointer checks remain; do not call all UI/touch tests complete. Screenshot `docs/room-setup-hearth-qa.png` is synthetic only.

Fixture9573 was explicitly stopped Ctrl-C terminal1 after testing; temporary data only, no real credentials. One Windows Proactor connection-reset callback appeared when a browser connection closed; fixture stayed live, continued checks and was then stopped. Preview4173 is confirmed HTTP200 and serves final assets. Windows Get-NetTCPConnection returned no output, but an attempted strict-port preview start exited1 because4173 was already occupied; do NOT treat that empty socket query as proof of a stopped server. No replacement launched and no process killed. Browser `roomTab` is tab4, now safe demo `http://127.0.0.1:4173/?demo=1&theme=hearth&setup=extras`, Air purifier open; marked deliverable, viewport reset. Earlier tabs1/2 may still show old preview errors; stopped tab3's error-page URL was previously tool-policy-blocked, leave it alone. No test/image/fixture jobs remain active.

Owner expanded final deliverable: after development/software qualification, provide verified hardware wiring→microSD reader/laptop→confirmed-target image flash→safe first boot→campus setup→dedicated-key SSH-assisted provisioning/recovery instructions. Recorded in EXPANSION_PLAN delivery section; the actual final guide is still required, based on exact part revisions/manuals. No hardware testing/flashing until owner is ready.

Next meaningful action: finish purifier UI gaps where software allows, then USB/LIRC two-Woozoo capability/learn/test and independence gates, disabled four-scene engine with presence debounce/cooldown and durable per-device overrides, themed controls/native voice/explicit remote allowlists. Then feature10 encrypted settings-only USB and a NEW immutable image with ARM/exact-file/realWS gates, followed by final owner hardware guide. Preserve game saves/frozen Tetris/privacy/mute. Source is newer than image; existing image must not be represented as final. Goal active, not complete. This goal turn made concrete implementation and verification progress; no blocker.

## Latest checkpoint — purifier adapter foundation tested

Feature9 begun with `purifier_adapter.py`, exact pyvesync3.4.2 pinned/installed (installation55902 terminal0). Read ROOM_DEVICES.md before continuing. Actual installed library models/methods tested via synthetic HTTP: fixed US/EU HTTPS/path/method allowlists,10sec I/O/20sec whole-operation deadline/2MiB cap, no redirect/proxy/automatic auth retry, session-only credentials and password-reference clearing, Core300S-only discovery/capability checks, preflight read and separate post-command readback. Busy requests never queue; uncertain dispatch outcomes never replay. No runtime worker/API/UI wiring yet and no real account/appliance calls. Two Woozoos/scenes remain as specified, not dropped.

Full663backend passed(session47067 terminal0,60.50sec; existing Starlette/httpx warning);34new purifier adapter cases included. Initial tests exposed incorrect async fixture annotation/missing synthetic library response fields, corrected; no weakening of production checks. Prior99frontend/TypeScript/build pass remains current, frontend unchanged after transit directory fix. Added pyvesync MIT notice and detailed room integration plan. No fixture/image/test processes remain running. Browser tab10 cleanup was interrupted after server stop; inspect tab inventory if resuming browser QA. Viewport reset, normal Neon transit tab8 intended retained. Last two goal turns made concrete progress, no blocker.

Preview recovery at turn end: browser session reset and all old tab bindings/IDs changed. Inventory now tab1=Hearth transit stress, tab2=normal Neon transit, tab3=stopped8749synthetic. All initially showed connection failure. Read-only Windows socket check confirmed no4173listener; restarted loopback-only Vite preview, session75474 live with startup URL. Selecting stopped tab3 for cleanup was blocked by browser URL security policy (error-page protocol); no workaround attempted. Leave that tab alone unless a supported allowed action becomes available. Other browser work is unnecessary for the next backend step. MIT notice matches installed wheel exactly after newline normalization. No image/fixture/test process remains; only preview75474 is live.

Immediate next: durable room selection/session-generation/configuration-revision store; owner-local bounded login/discovery/selection/command APIs and conservative backoff runtime, preserving privacy during awaits. Then USB/LIRC two-fan capability/learning/independence gates and empty disabled scene engine, themed optional setup/device controls/voice/remote opt-in + realHTTP/WS/browser QA. Feature10 encrypted settings-only USB and newimmutableimage/ARM/realWS qualification remain. Physical tests deferred by owner. Existing image outdated, do not flash; goal active, not complete.

## Latest checkpoint — transit local integration qualified; room devices next

Feature8 now passes real browser→HTTP→SQLite save/edit/reload, 45-stop directory pagination, observed-direction selection, private-default review, dirty/discard/extra-navigation guards, exact removal confirmation, masked token review/save/removal, six-stop traversal, real WebSocket full→private filtering and post-commissioning setup403. Killing the fixture's real server immediately cleared all private stops and converted the public stop to explicitly Saved schedule. Synthetic providers only, no owner credentials or appliance activity. Added reproducible `tests/transit_preview.py` and `tests/transit_live_check.py`; latter passed terminal0. Fixture87075 explicitly stopped Ctrl-C terminal1; temporary data only. Browser cleanup of tab10 was interrupted, inspect before reusing; viewport was reset. Tab8 is normal Neon transit preview.

Fixed directory failure UX: malformed/offline/429 no longer also say No matching entries or retain stale pagination. Search retry recovers and leaves saved stops intact. Verified9review+touch-keyboard layouts across3themes/native landscape/portrait/narrow without horizontal clipping. First attempted Neon pass was still Hearth due unsaved reload guard; discarded draft and rechecked actual theme class. TypeScript/build pass (`index-DxDDZYBi.js`, CSS unchanged);99frontend pass. Full backend rerun67516 was observed progressing but handle vanished at continuation; do not claim its terminal result. Prior629-pass evidence remains, rerun after dependency setup.

Next concrete work: feature9 as specified in EXPANSION_PLAN. Public PyPI metadata confirms pyvesync3.4.2, Python>=3.11, async V3 API and persisted session credentials; package wheel SHA256 `8f0a75433ce51f7ba8a539880ab654d3c5291a3a87de00cd496a5b8630a402f0`. Installing pinned library in project venv for source inspection/mock tests (session55902, poll to terminal). No production dependency pin/adapter yet. Read exact installed source before implementation, use session not persisted password, capability-gated Core300S controls. Then two safely isolated USB IR fans, disabled scenes, feature10 settings-only encrypted USB, final immutable image and ARM/realWS gates. No game changes or hardware tests. Goal active; last goal turn made concrete progress, no blocker.

## Latest checkpoint — transit frontend, voice and onboarding integrated

Feature8 now has TransitSetup inside Dates & travel: provider token masking/requirements links, sequential agency→route→stop→observed-direction→name/private review, local save/edit/remove/discard paths and explicit token removal. TransitPage uses large themed minutes/routes/destinations, one favorite per10sec, index continuation, shared cycle/visible heartbeat, semantic live/scheduled/saved labels and511attribution. Client expiration uses backend prediction_until/scheduled_at; disconnect drops private favorites and converts public predictions to saved schedules/Unavailable. Native “show transit”/“when is my next departure” are free deterministic queries, no provider call; actual saved count/token boolean added to onboarding review. No real token/provider/hardware calls or game changes.

Full629backend passed(session76093terminal0,64.98sec; existing Starlette/httpx warning);99frontend tests passed, final4transit pure tests rechecked, TypeScript/build pass (`index-s8VZD8G8.js`,`index-_Rp1z6yU.css`). First full run30441 failed only the old exact onboarding summary expectation (628pass); updated for three new non-secret transit fields, reran full. Browser9normal slide +9token setup +9long-name/four-digit/six-stop layout cases; long landscape initially overflowed, fixed by removing redundant Transit heading, explicit page-gap specificity, smaller row padding and pixel-unit Neon spacing, all long cases now fit. Demo agency→allroutes→stop→N→save private verified. Token type=password, save disabled until valid entry/review. **Feature8 not yet fully qualified:** real local HTTP/WS synthetic fixture save/edit/reload/privacy/disconnect; complete dirty/discard/removal and malformed/rate-limit UI checks; six-stop manual traversal and setup review/native-keyboard layout checks still required.

Browser originaltab6 hit debugger synchronization timeout during repeated responsive navigation. Recovered with newtab8 in same selected browser, no server restart. `transitQa` is the new supported browser binding; tab8 retained as deliverable at `http://127.0.0.1:4173/?demo=1&theme=neon-grid&page=transit&hold=1`; viewport reset. Oldtab6 may remain at Hearthstress and should be inspected/reused only if responsive; do not infer app failure from that tool timeout. No fixture/image job running. Next concrete action: build isolated transit_preview.py akin countdown_preview.py, mocked transport/no provider workers, then actual browserHTTP/WS privacy/persistence QA. After8 qualification,9appliances/scenes,10encryptedUSB and newimmutableimage/ARM/packagedWSgates. Physical tests deferred. Goal active; previous and current turns are progress, no blocker.

## Latest checkpoint — transit backend integrated, frontend next

Concrete progress this goal turn: feature8 now has documented JSON metadata discovery (distinct directory/realtime IDs),12-entry/7-day bounded cache, six durable private-by-default favorites, token/sample atomic reset, revision/generation late-response protection, read-time prediction expiry, cancellation filtering, local-only owner-gated API, privacy/night-redacted snapshots and a runtime worker. Shared stop groups use one request;75sec routine slots, favored visible/Stanford/Caltrain alternates with other stops, night/unknown-clock pause, schedule fallback on later slot and backoff. Every call including setup/preview uses the persisted55/hour budget. No provider/owner credential/hardware calls; mocks only. `docs/TRANSIT.md` now records the full API contract and precise remaining work.

Full622backend passed (session57675 terminal0,64.02sec, existing Starlette/httpx warning).62transit cases included. Earlier two new privacy-test failures were corrected to real service transitions; not runtime bypasses. Final tiny runtime guards prune obsolete group maps and skip scheduling changes from old-token responses; all62transit tests rechecked afterward, terminal0,6.36sec. Frontend unchanged this turn (previous95pass/build evidence retained). No image or fixture job running, no Tetris edits.

Next: frontend TransitSetup in Dates & travel, provider terms/token masking, sequential agency/route/stop/observed-direction/private review flow; themed3departure slide, disconnect/stale aging, visible heartbeat, cycle/voice and onboarding review; real synthetic localHTTP/WS/browser QA. Read TRANSIT.md before implementation. Then9appliances/scenes,10encryptedUSBsettings and newimmutableimage/ARM/realWSqualification. Final image still outdated, don't flash. Physical tests deferred; goal active, no blocker. Previous goal turn and this one are progress, not no-progress turns.

## Latest checkpoint — transit foundation, not activated

Feature8 research/transport/parser begun; read `docs/TRANSIT.md` for official sources, exact boundaries and next steps. `TransitBudget` atomically persists55/hour before every I/O, fails closed for corrupt histories/clock rollback; bounded HTTPS allowlist transport redacts token/errors. SIRI parser distinguishes fresh predictions from schedules and filters wrong stops/directions, invalid/expired/cancelled calls. Fixed malformed sibling/root crashes found by tests. No actual provider/account calls, token storage or runtime/UI integration yet. Do not label transit complete.

Targeted37backend tests (30transit +7agenda) and5frontend agenda tests pass. Full590backend passed (session96180 terminal0,55.10sec, existing Starlette/httpx deprecation warning);95frontend passed. No process from these checks remains running. Remaining features8/9/10 then immutable image/software gates; physical testing deferred. Earlier Important Dates and packed-day Calendar source qualification remains valid. No game changes. Next: official discovery/cancellation shape review, then durable favorite/secret model and scheduler; see TRANSIT.md.

## Latest checkpoint — Important Dates source/UI qualified

Feature7 now completed in source and software checks; see `docs/COUNTDOWNS.md`. Real browser→HTTP storage save/edit/reload, discard guards, paginated synthetic Google picker (including429 recovery), explicit public pin/local unpin, and real WebSocket full-to-private filtering passed. Post-commissioning setup403 hides all private titles. Fixed native date/time field input commits (browser previously displayed December10 but saved old date), disconnect public Google stale marker, slide continuation, portrait long-number overflow, native picker contrast and single-date presentation. No real account/provider/hardware calls. Tetris untouched.

Latest full560backend passed (session96908 terminal0,55.04sec; existing Starlette/httpx warning);95frontend passed; TypeScript/build pass (`index-Y1-R5iGi.js`, `index-DV-UkwjA.css`).18 Dates/setup theme×size cases +portrait overflow rechecks pass;12/12sample dates reachable. Temporary fixture8747/session82219 stopped via Ctrl-C terminal1 after successful QA; temporary tab closed. `countdown_live_check.py` first run reached all assertions but printing a Unicode arrow failed on Windows; ASCII rerun terminal0. Original preview tab6 retained and viewport reset.

Previous goal turn and this turn are concrete progress. No image/build processes active. Remaining full goal: **8 transit**, **9 purifier/fans/scenes**, **10 encrypted settings USB**, then new immutable Pi image, ARM packaged smoke and real WebSocket gate. Read EXPANSION_PLAN sections8–10 before implementation. Important Dates backup export belongs to10. Physical tests remain deferred. Existing image outdated; don't flash it or mark goal complete. No blocker; start transit provider research/quota/cache/secret/capability model next. Earlier countdown-pending notes below are superseded.

## Latest checkpoint — complete packed-day timeline

Owner requested all events across multiple calendars, with times laid out Google Calendar-style from wake to next Sleep. Implemented separate `agenda.py` complete-day snapshot (not limited/upcoming-only), `AgendaPage.tsx`, `agendaState.ts` packing/pagination and themed `agenda.css`. Earlier-today included; independent sleep bounds, overnight/DST, out-of-window appointments, all-day section, overlaps paginated without shrinking, Google colors, detail modal and privacy/disconnect clearing. Home still two upcoming events. Four-hour sections rotate9sec and preserve next section index across slide visits. Manual controls pause; interaction holds global cycle60sec. Read `docs/DAY_AGENDA.md` for tradeoffs and contracts. No game edits.

Evidence: full560backend tests passed(session2653 terminal0,58.69sec, one pre-existing Starlette/httpx warning);94frontend pass; TypeScript/build pass.9theme×viewport timeline checks passed (initial fast-navigation empty captures rechecked with fresh DOM).21/21 crowded sample events reached across11sections;40overlap pure test; details/Escape/focus restore passed. Last minor all-day modal exclusive-end fix and night agenda-null assertion checked subsequently. Preview should remain Neon packed-day Calendar. Real Google/Pi tests not performed; source only, final image still outdated. Full expansion next steps in preceding checkpoint remain, including Important Dates UI qualification/features8/9/10 and immutable image.

## Latest checkpoint — Sleep calendar clarification and partial countdown UI

Owner's latest contract: independently selected Google sleep calendar(s), daily timed events titled **Sleep**. Fresh default is now `Sleep`; existing saved custom titles (including old `Sleep Time`) are preserved. No selection disables automatic calendar sleep; removed agenda fallback. All-day/declined/cancelled events ignored. Overnight, recurring expanded occurrences, merged intervals, five-minute scheduled wake at end, manual20-second morning and temporary wake remain. Calendar setup, Night setup and docs updated. Agenda is multi-select; Leave soon independently uses all eligible events on selected calendars. Important Dates remains manual dates/individual Google pins, NOT calendar-wide. Settings validation and local-only gate added for sleep fields.

Latest verification: full **553 backend / 89 frontend tests pass**, TypeScript and production build pass (`index-BT5wYdAn.js`, `index-31qOrF8s.css`). Backend session41938 terminal exit0,62.08seconds, existing Starlette/httpx deprecation warning. Earlier session19285 had one navigation-wrap expectation failure after adding COUNTDOWNS; test now correctly expects the new last page, full suite passes. Sleep browser setup checked across3themes ×2048x1536/1536x2048/390x844: independent checkbox groups, `Sleep` field, no horizontal overflow. Viewport reset; tab6 restored to Hearth Dates preview. No account/hardware/image jobs or changes.

Countdown UI now exists: `CountdownSetup.tsx`, `CountdownsPage.tsx`, `countdownState.ts`, `countdowns.css`, Extras/onboarding/page/cycle/voice integration. Private dates removed on WebSocket disconnect; public dates only in private cycle; empty-date cycles skipped. Four frontend pure tests added. Dates near-square caption overflow fixed by narrowing stacked-row breakpoint to3:4; default preview rechecked visually, fits. **Feature7 still needs comprehensive UI qualification**: all themes/native portrait and long titles/many-date pagination; manual add/edit/discard/delete/public/Google picker demo; real isolated HTTP/WS persistence/privacy round trips; review disconnect public Google stale label behavior. Backend COUNTDOWNS.md remains authoritative for API. Update its outdated frontend-pending section after full QA. Do not claim feature7 or final image complete.

Next: finish feature7 qualification, then8transit,9appliances/scenes,10encryptedUSB, new immutable image and real packaged WebSocket gate. Old image outdated, do not flash. Hardware deferred. No blocker; preserve game timings/saves and saved microphone mute. Earlier entries below are historical.

## Latest work — countdown backend, UI still pending

Feature7 now has `countdowns.py` durable bounded12-item store and date/time/annual math, private/public snapshot filtering, `countdown_api.py` local-only configuration/search/pin/refresh endpoints, independent300-second exact-pin worker, and Google provider occurrence-page/get adapters. No new scope or Google writes. Read `docs/COUNTDOWNS.md` before continuing: API shapes, semantics and the exact remaining UI work are recorded there. Feature7 is NOT complete; frontend ignores snapshot.countdowns today.

Evidence:24 targeted countdown tests pass, including leap-year rollover fix, DST/exclusive dates, capacity/revisions, disk rollback, no tick writes, corrupt-store preservation, Google colors/stale/deleted, no provider calls with no pins, privacy expiry after network wait and unpin-before-response. Latest full540backend suite passed(session60524 terminal0,54.01seconds, one existing Starlette/httpx warning). Earlier538suite/session10169 also terminal0. Frontend unchanged this turn (prior85tests/build evidence remains historical). No account/provider/hardware/image calls; no new preview server or test process running.

Immediate next: implement CountdownSetup inside Extras (manual dates first, optional exact-Google-event picker with page/date-window controls), Dates slide with3entries/8-second pagination, Page/countdown cycle integration, “show countdowns” grammar, actual saved-count onboarding review, and3theme/responsive/browser tests. IMPORTANT: when adding frontend snapshot.countdowns, clear private entries on WebSocket disconnect and allow only explicit public dates in private cycling; suppress all in night/wake. Preserve Tetris timing/saves. Then8transit,9appliances/scenes,10encryptedUSB, finalimmutableimage+realWS qualification. Hardware still deferred; full goal active, no blocker.

## Latest addition — native voice question library

Owner requested free basic spoken questions, including time. Implemented `voice_library.py` with13 deterministic intents and aliases, offline Vosk grammar integration, local-only answer/library APIs, privacy-filtered `voice_snapshot` including earlier-today calendar items, and themed collapsed phrase reference in VoiceSetup. No LLM/cloud fallback, no new provider polls/permissions. Includes weather/current/rain, next/today/tomorrow/ongoing calendar, outstanding/due tasks, time/date, timer status and help. Unknown question forms do not fall through navigation/mutation. Existing controls/mute/calibration/Tetris unchanged. Read `docs/VOICE_LIBRARY.md`.

Verification:516backend passed (session58710 terminal0; existing Starlette/httpx warning),85frontend pass, TypeScript/build pass (`index-DfJBKrFG.js`, `index-Bi6IX1lL.css`).64new library cases cover all aliases/examples, local-only/no-cloud/no-provider paths, privacy, timezone/date/calendar filters, task colors, stale/missing weather and bounded responses. Small final response-copy edit rechecked in targeted suite.9expanded-reference browser layouts across3themes/native landscape/portrait/narrow fit; viewport reset, tab6 preview retained. No accounts/audio/hardware changed. Source update only; old image remains outdated. Next full goal:7/8/9/10 then new image/realWS qualification; physical acceptance deferred.

## Latest checkpoint — night/wake integrated and software checked

Features4/5 now connect DisplayCycle/Handoff to settings, service, boot-local clock trust, commands/voice/Shortcuts, local frame/job/generation APIs, nonblocking desktop DDC worker, themed night/waking UI, Extras and onboarding review. Read `docs/NIGHT_DISPLAY_IMPLEMENTATION.md`. Old sections below are historical, not remaining integration instructions. Privacy stays redacted during night/off/wake and untrusted time; first-run setup remains usable offline. Native keyboard/owned portal close outside day mode. Root is black and waits for first authoritative snapshot. Body opacity is a browser dimmer, NOT compositor-wide/native backlight control.

Software evidence:452backend passed (session89441 terminal0; existing Starlette/httpx warning),85frontend passed; TypeScript/build pass (`index-B_FGAC-6.js`, `index-CwEp8UgE.css`). Final exception-handling guard then targeted recheck.24night integration cases include live-command brief dedupe, nonblocking worker/failure, native helper suppression and a newly found/fixed polling race: compare display to last broadcast sample, not last HTTP read. Browser18layouts (clock/setup ×3themes×3sizes); actual isolated8746HTTP/WebSocket + simulated bridge touch wake/off/wake passed without reload. No owner accounts/hardware. `tests/night_preview.py` reproduces this with temporary state/no provider workers/10min deadline; sessions65341 and71835 stopped, terminal1 from deliberate Ctrl-C. No fixture/image job running.

WSL `image-builder/display-frame-smoke.py` completed terminal0(session6991): private headless labwc/pixman +sandboxed DebianChromium154 delivered240rAF/4sec while output on/off/on, hiddenfalse. Normalflags work; no shippingflagschanged. This is software liveness evidence, NOT actual Pi KMS/DPMS/retained-frame qualification. Full physical check waits for owner.

Next: selected features7countdowns,8transit,9Core300S/twoWoozoos+scenes,10encryptedsettings-onlyUSB, then newimmutableimage/exact-fileaudit/realpackagedWS qualification. Preserve frozen Tetris, all game saves, mute/privacy and account permissions. Historical image is outdated; do not recommend flashing. Full goal active, no blocker. See `docs/EXPANSION_PLAN.md` for each feature's exact contract.

## Latest checkpoint — night/wake backend components (NOT activated)

Added `display_cycle.py`, `display_handoff.py`, `DisplayController.set_brightness_confirmed` plus57 targeted tests. Full428backend passed (session24364 terminal exit0, existing Starlette/httpx warning). Timing uses monotonic smooth20sec/300sec ramps, verified-UTC recovery, unknown-clock darkness, repeated-command dedupe, manual cancel and transition-only persistence. Handoff serializes/frame-gates hardware jobs, preserves conservative reference through retarget/unknown commit, bounds retries and invalidates knowledge after bridge restart. Verified DDC uses getvcp scale + set + readback; all hardware calls MOCKED. Existing live service/bridge/UI/image unchanged; these components are not wired yet. Frontend last82-pass evidence unchanged, not rerun this turn.

Read `docs/NIGHT_DISPLAY_IMPLEMENTATION.md` before continuing: it records exact interfaces and integration checklist. Critical remaining design: a powered-off Wayland output may stop browser rAF, so naive frame-ack-before-power-on can deadlock. Resolve prepared-black-frame/resume sequencing with software compositor evidence; do not blindly timeout safety or call this hardware-qualified. This is meaningful integration work still available, not a blocker. Next integrate features4/5 (settings, service/commands, trust, local protocol/bridge, themed clock/ramp, timer silence, actual brief dedupe), then7/8/9/10, realWS image gate and new immutable image. No goal completion. All test sessions terminal; no image/hardware/API jobs launched this turn. Preserve Tetris/game saves/privacy/mute.

## Latest implementation — September 26, leave-soon reminders

Feature2 is implemented in source: opt-in calendar/buffer settings and Extras/onboarding, private/silent themed notice/dialog, per-occurrence override/snooze/dismiss, restart-safe bounded cache, enabled-only existing Google polling, metadata filtering and local/private/fresh-current-key API gate. No route estimates, Google writes, extra scopes or new worker. See `docs/DEPARTURES.md`. Owner's task color rule remains exact: only chosen completed color; other overrides outstanding. Frozen Tetris untouched.

Full backend371passed (session19388 terminal exit0; one existing Starlette/httpx warning); frontend82passed. This includes26 departure backend cases, 2 frontend cases and 2 sleep-interval cases. TypeScript/build pass (`index-B0CwcRsx.js`, `index-CG3Zg4xY.css`). Browser27layouts (notice/dialog/setup ×3themes×3sizes) no horizontal overflow; buffer edit, snooze/dismiss, unsaved guard, calendar-required validation, save/navigation and private suppression checked. No account/hardware changes. Preview4173 responds; tab4 left at `?demo=1&theme=hearth&fixture=departure&hold=1`, viewport reset. No API/image jobs running; all pytest sessions terminal.

Next features4/5 groundwork: `active_sleep_end` now merges connected overlapping/touching intervals using UTC instants, including future overlaps; new tests cover gaps/cancellation/unselected calendars and repeated DST hour. Explicit night-clock/waking modes and ramps are NOT implemented yet. Continue those, then7/8/9/10 and new image+real WebSocket qualification. Existing image remains immutable/older. Future night mode must suppress departure notices and timer chime; preserve no-early-wake and exact20sec/5min owner timing. No blocker.

## Active full expansion goal — September 26 to-do clarification implemented

Latest owner note supersedes old task semantics: one chosen Google calendar, all-day title-only tasks active TODAY (including multi-day spans), due on last visible Google day; only the chosen completed event color means complete (owner confirmed), other colors outstanding. Source implements two-way color-only updates, explicit optional OAuth write upgrade, ETag conflicts/no retries, default-color reopening, checked/dimmed themed tasks, all-task pagination and setup color picker. See `docs/TODO_CALENDAR.md`. 343backend/80frontend tests pass; TypeScript/build pass. 18new task-slide/color-picker layout checks (3themes×native landscape/portrait/narrow) pass; complete/reopen, all14sampletasks, save-before-consent and unsaved-color guards checked. No real Google writes/consent or hardware tests. This addition is implemented in SOURCE, not the historical image.

Next resume full expansion features2/4/5/7/8/9/10, then image packaging/qualification; no blocker. Google event edit scope is optional and explicitly disclosed; don't silently request it or infer it from a read-only token. Preserve task date/color contract, saved permissions/privacy, all game states and frozen Tetris.

**Delivery warning:** real browser testing exposed a missing WebSocket transport in minimal Uvicorn dependencies. Source explicitly requires `websockets>=15,<17` (16.1.1 in Windows venv). Actual Uvicorn/TCP regression `test_live_transport.py` passes pushed completion and bounded shutdown; event route receives disconnects and cleans up subscribers. Existing delivered image's HTTP-only smoke evidence does NOT prove live updates; do not recommend flashing it as a final build. Add a real WebSocket probe to the next image qualification gate. Both isolated API sessions56430/87558 are stopped; pushed browser completion was verified after the transport fix.

The active objective is **implement the entire expansion plan plus intuitive onboarding**, not onboarding alone. Source now implements guided setup, feature1 timers and feature3 weather hints. Features2/4/5/7/8/9/10 and final image qualification remain. Do not mark the full goal complete while they remain missing. No blocker: continue with night-clock/gentle-wake, preserving exact owner decisions in `docs/EXPANSION_PLAN.md`.

Added `focus_timer.py`, additive preset settings, monotonic runtime/UTC recovery, no per-second SD writes, current-ID replacement confirmation, private label redaction, bounded voice/Shortcut actions and local-only one-shot chime claim. `timer_chime.py` produces a short memory-only tone through the existing desktop bridge; no audio hardware used in tests. Frontend timer badge/panel/completion uses one overlay slot with controls and suppresses lower-priority phone notices. New optional `extras` onboarding step + `ExtrasSetup` expose timer presets without making the remaining planned features look implemented.

Feature3 adds `weather_nudges.py`, optional forecast metrics with explicit units and Unix/DST timestamps, pure six-hour rules, local-only opt-in thresholds, inline themed weather hints and unknown-rain display. Extras now selects one task at a time with collapsed advanced thresholds, unsaved-edit guards and factual review rows. No extra poller or per-tick writes. Missing/stale/future data and UI disconnect suppress hints. See `docs/WEATHER_NUDGES.md`.

Checks: **322 backend / 78 frontend tests passed**, TypeScript/build passed; 42 onboarding/weather cases rerun after review-row integration. Last build `index-D6CFZnLf.js`. Weather/Home layout18cases + expanded-extras9cases across three themes and native landscape/portrait/narrow viewports: no horizontal overflow. Invalid thresholds, unsaved checkbox warning, preview save verified. Old timer QA data `runtime/timer-ui-qa` is test-only (no accounts); no8748server should be running. Preview4173/session58897 remains the demo. No image build running. Future night-clock mode must extend timer silence beyond screen-off/zero-volume handling. Full new image build/qualification still required; prior image immutable.

## September 26 local — guided setup source update

Current source is **newer than the delivered Tailscale image**. Implemented resumable first-run wizard (Welcome, network, space, PIN, optional Google/phone/voice/Tailscale, review), themed/touch-friendly UI, existing-settings compatibility, local-only secret-free progress API, unsaved-edit guard and operation-navigation guard. Provider panels are reused; no accounts enrolled, credentials entered or hardware exercised.

New durable roadmap: `docs/EXPANSION_PLAN.md` records selected features 1/2/3/4/5/7/8/9/10 and the onboarding extension contract. Those feature implementations remain future work. Preserve the owner choices there, especially exact night/wake timing, independent Woozoos, Core 300S, settings-only USB export and frozen Tetris.

Checks: backend 272 passed (17 new setup cases), frontend 72 passed (5 new workflow cases), TypeScript and production build passed. Browser demo flow verified save/discard, touch-key edit warnings, optional skip, pairing cancel guard and reload resume; 36 layout checks across three themes at 2048×1536, 1536×2048 and 390×844 had no horizontal overflow. See `docs/ONBOARDING_QA.md` for limitations. Existing image checks are historical and do not qualify these newer source changes. Next packaging gate: a new immutable image build and software qualification, before any owner-authorized physical tests.

Final browser pass added the other five steps: **81 total layout checks**, no horizontal overflow; Finish opened the dashboard. Local preview restarted on `http://127.0.0.1:4173/` (session 58897 at this checkpoint). No image jobs are running. Do not rely on a persisted session handle after restart; check first.

Updated September25 local / September26 UTC,2026. This file is authoritative; older live handles in PROGRESS.md are historical.

## Owner decisions

- Complete non-hardware work now. Hardware is NOT assembled; do not flash or physically test until the owner prompts.
- Siri stays on iPhone. Local Hey Luma is default-on for new installs; saved microphone-off stays off.
- Tetris pacing is FROZEN: committed .105, drift .09, multiplier min(4,2.5+score/12000), unchanged thinking pauses. No retuning or save reset.
- Optional free Personal-plan Tailscale is approved and implemented. Private HTTPS Serve to restricted8743 only; never main8742/Funnel/VPN privacy unlock.
- Never read or copy the administrator private SSH key. Only the approved public key enters images.

## Latest delivered candidate

`image/tailscale-20260926/luma-pi4-UNVERIFIED.img.xz`

- 612409576bytes; SHA256 `22c0c58ef341a57d4c6d7f86dd56eb10abc0e1a7ba7a1250c2e7cc3ca99a0860`.
- Built2026-09-26T04:15:25Z; sourceSHA `8001c2fddd91a249dbeef9e2365b93106f91e09ce4901e73e1cfdc9f2055a35b`.
- Generator `dbd775d191a2e2cafec95bb218f2002213eff2ff`; frontend `index-DAC0tGYc.js`.
- Same-folder checksum/build+source manifests, README and React notice. Windows copy independently hash-verified; portable checksum and builder XZ integrity/source recheck passed.
- Includes default voice, campus/Google/Bluetooth onboarding, optional Tailscale QR setup/status/disconnect/private commands and local token replacement.
- Daemon/gateway ship disabled. No Tailscale identity/account, certificate or personal credentials are baked in.
- Older voice/OAuth candidates preserved. No SD card flashed. `boot_verified=false` deliberately means physical boot is not qualified.

## Completed software evidence

Receipts: `image/qualification-tailscale-20260926/`.

- Build39380 TERMINAL exit0. Immutable staging `/home/luma-build/luma-tailscale-20260926`; log `/home/luma-build/image-build-tailscale-20260926.log`.
- Rawchecker74218 TERMINAL exit0: real rootpartition matches sidecar SHA `395075ed96a5db016cd9f9172ffd9811e78131a0b01884518417672ca5e16050`; exact selected runtime/permissions/CA/SSH/defaults/officialTailscale binaries checked.
- OfflineQEMU43460 TERMINAL runnerexit0, deliberate underlyingtimeout124 after all required markers. Normal180s, no NIC: API/database86.554257s; gateway denial + real broker NeedsLogin101.801182s. Log `/tmp/luma-qemu.Nrl31Dem/serial.log`. No account, host ports, base mutation or competing compression.
- Fullfileaudit78066 TERMINAL exit0:112 shipped app/frontend/model/license/system/boot/source files compare exactly; all system inputs classified. Three main native binaries and all12 Python native libraries confirmed ARM64. Required WM8960/I2S/simple-card/TUN/nftables modules present.
-255backend +67frontend +18packaging +9manualchecker tests passed; TypeScript/production build passed. Separate isolated IPv4/6 firewall connection tests passed; demo touch setup reviewed in Hearth/NeonGrid.
- SPDX2.3 inventory2721packages/37908files; independent Linux/WindowsSHA `d01980b315f31810919533aa1042bad3a235bad26c1b55e490257fc67099b579`.
- Final non-hardware review and optional feature proposals are in `docs/SOFTWARE_AUDIT.md`; notices/maintenance in `docs/THIRD_PARTY.md`. Scope/limits explicit, not a vulnerability certification or public redistribution clearance.
- Initial Windows-directory install command failed only on chmod after creating the intended folder. Subsequent no-clobber copy succeeded and was independently hashed. No prior artifact overwritten.
- All older image/emulator handles are terminal. Do not poll/restart them. Only loopback frontend preview60125 may remain running at127.0.0.1:4173.

## Next phase — owner-deferred

Non-hardware implementation, integration, image delivery and the final software/file/hardware-constraints review are completed at the documented scope. No account or phone has been enrolled as a substitute for hardware tests.

Wait for the owner's explicit hardware-testing prompt. Then follow docs/FLASHING.md, FIRST_BOOT.md and HARDWARE_VALIDATION.md with exact-card confirmation and synthetic data first. Gates: native display/touch/DDC/wake; ReSpeaker capture/output/AEC/LEDs/voice range; actual Bluetooth/ANCS; Google consent; campus Wi-Fi/time/TLS; Tailscale enrollment/certificate/policy/iPhone Shortcuts/reconnect; physical outages; sustained2GB memory/thermal/frame pacing.

Do not claim authoritative ongoing call state from ANCS, Siri-only Bluetooth routing, guaranteed across-room wake accuracy, or permanent account authorization. Appliance automations need the actual appliance/action choice. Optional proposed features are not installed promises. Preserve the current candidate and receipts when making any future runtime change; new runtime bytes require a new versioned image and tests.
