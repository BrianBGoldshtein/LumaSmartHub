# r14 app-only update through Pi Connect

This is a controlled **test-candidate** deployment, not the stable one-button
Settings update. It changes Luma's frontend/backend application from `0.2.0`
to `0.2.1`; it does not reflash the SD card, overwrite `/var/lib/luma`, change
OS packages, or remove the previous app release. The bundle is signed with the
offline key matching the public key pinned in the r13 image. Do not apply it
to an older image or put its feature-branch URL into the stable update feed.

## Before applying

1. On the physical Pi, finish the r13 boot/network/touch, USB and Pi Connect
   recovery checks in [R13_TEST_SEQUENCE.md](R13_TEST_SEQUENCE.md). In Luma,
   enable the admin remote shell only while you need it. Verify that the
   current version is `0.2.0` in Settings or by opening
   `http://127.0.0.1:8742/api/v1/health` on the Pi. If Connect itself is
   unavailable, stop; this procedure cannot substitute for a recovery route.
2. Make sure your important setup already survives an ordinary Pi restart.
   The updater leaves `/var/lib/luma` intact, but neither a source test nor
   the updater can guarantee survival of a failing SD card or a power cut.
3. In your Raspberry Pi Connect account, open this Pi's **remote shell**. It
   should be the dedicated `luma-admin` session. Do not paste credentials,
   OAuth JSON, or PINs into the shell or this chat.

## Download and verify

Paste the following commands into that Pi Connect shell **one at a time**.
Stop at the first error. The URL is pinned to the exact reviewed artifact
commit rather than a mutable branch name. It was observed returning HTTP 200
and a 1,085,719-byte file, but the local hash/signature checks are still
mandatory.

```sh
curl --fail --location --proto '=https' --tlsv1.2 --output /home/luma-admin/luma-update-0.2.1.lup 'https://raw.githubusercontent.com/BrianBGoldshtein/LumaSmartHub/accd938bd2d08f7e0ca55686ee7d7cd52238c1d4/SD%20Card/updates/r14-candidate-20260930/luma-update-0.2.1.lup'
```

```sh
printf '%s  %s\n' '8df24ca9859ecdd0f2f45a4da0f6e718a35095f4bb1facc8c07c15937f258fbc' '/home/luma-admin/luma-update-0.2.1.lup' | sha256sum -c -
```

The second command must print `OK`. Then verify the Ed25519 signature and
package contracts with the **r13-installed** updater:

```sh
sudo /opt/luma/venv/bin/luma-update verify /home/luma-admin/luma-update-0.2.1.lup
```

It must say `Verified Luma 0.2.1 · 31 files · no changes made`. If it does
not, stop and report the non-secret error text. Do not disable verification.

## Owner-approved installation

Only after the prerequisite checks above pass and the owner is ready for a
brief Luma restart, run:

```sh
sudo /opt/luma/venv/bin/luma-update apply /home/luma-admin/luma-update-0.2.1.lup
```

The installer stages a new release, switches `/opt/luma` atomically, restarts
the Luma services and waits for the `0.2.1` health response. On health-check
failure it switches back to `0.2.0` and restarts the old app. Network, Pi
Connect and saved `/var/lib/luma` state are outside the switched app directory.
Afterward, verify the Luma Settings version is `0.2.1`, check Calendar remains
connected, and watch several Pong rallies and at least two Space Invaders
waves in each theme. Confirm scene changes and an ordinary reboot preserve
the existing setup and game checkpoints. Report any failure before trying a
second install: a partially staged version can intentionally block reuse of
the same version number.

The normal **Settings → Check for update** remains reserved for signed
stable releases from `main`; it will not list this feature-branch candidate.
Once r14 and the hardware are accepted, publish an appropriate later version
through the stable release workflow rather than silently changing that gate.
