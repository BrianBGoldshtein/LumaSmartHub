# Signed in-place application updates

The release target is one final planned full OS image containing the complete
system baseline, Pi Connect touchscreen recovery setup, and this signed
application updater. After that image is installed and qualified, normal Luma
feature releases use signed `.lup` bundles without another OS flash. OS-level
components (packages, accounts, services, device rules and firmware) must be
present in that final image; they are intentionally outside the app bundle.
Future OS/security or hardware-platform maintenance may still require a new
OS image.

## Primary update path: GitHub Releases

The on-device **Settings → Luma software → Check for updates** control checks
the public `BrianBGoldshtein/LumaSmartHub` GitHub Releases feed. It does not
execute `git pull`, install a branch checkout, or trust a branch archive. The
Pi downloads only the exact `luma-update-X.Y.Z.lup` asset attached to a stable
`vX.Y.Z` release whose target is `main`. It checks the release size/checksum,
then verifies the image-pinned Ed25519 signature and every payload hash. Luma
shows the signed release version and notes for review before the separate
**Install update** confirmation. The protected installer checks the signature
again, installs the app-only package into a fresh version directory, switches
atomically, verifies the restarted health endpoint and rolls back if it fails.

Development commits can go to a feature branch for CI and review, then to
`main` for beta delivery after software tests pass. As of October 1, 2026,
the owner explicitly approved `main` as the ongoing beta update channel;
physical Pi acceptance remains a separate step and must not be implied by a
beta release. The GitHub Release title and notes say **Beta**. The GitHub
release itself must use the normal release flag, not GitHub's prerelease flag,
because the installed Pi updater intentionally ignores prereleases.
After the versioned source passes CI, merge it to `main`, confirm CI again on
that exact main commit, then create the matching signed release.
The asset name and tag must match exactly
(`v0.3.0` → `luma-update-0.3.0.lup`). Set the release target to `main` and add
human-readable release notes; drafts and prereleases are not installed.

The Ed25519 private key stays on the owner's Linux signing machine and is never
placed in GitHub Actions, the repository, release notes, or the Pi. CI never
receives a signing secret. The local release helper rebuilds and tests the
frontend/backend, requires a clean checkout of the exact `origin/main` commit,
checks for a successful GitHub Actions run on that commit, verifies the key
matches the public key pinned into the image, and signs locally. It cannot
publish a release until `--publish` is given and the operator types the exact
tag confirmation. For beta delivery, use it after software qualification and
after the tested code has been merged to `main`:

```sh
bash "SD Card/source/tools/publish-update-release.sh" \
  --key /home/luma-build/keys/luma-update-ed25519.pem \
  --notes-file /home/luma-build/luma-release-notes.md \
  --publish
```

The helper asks you to type `publish vX.Y.Z` before it publishes. It
requires an authenticated `gh` session with write access and creates the stable
release on `main`, attaching exactly `luma-update-X.Y.Z.lup`. Without
`--publish`, it builds a local signed bundle only. If you first build a preview
bundle, use a different `--output` path for the later publishing run because
the signer deliberately never overwrites an existing archive. Use a new stable
version every time; the helper refuses a reused tag, asset name, dirty checkout,
non-main branch, stale main, or missing green CI run. Keep notes and signed
archives outside the checkout. The Pi uses no GitHub account, token, API key,
or secret. If campus Wi-Fi has not completed its visitor sign-in or otherwise
cannot reach GitHub, checking fails without changing the installed app; use the
on-screen Wi-Fi setup and retry.

This Settings feature and its root-owned `luma-update.socket` broker must be
present in the newly qualified full image. The app-only updater deliberately
cannot install that broker or add its systemd policy to an older image. Keep
Pi Connect as the separate recovery path. A release with changed OS packages,
system units, Python dependencies, durable-data schema or hardware rules is
rejected for app-only installation and needs a newly qualified image.

The next freshly built Luma image installs the application as a root-owned
versioned release and pins the Ed25519 verification public key in
`/etc/luma/luma-update-ed25519.pub`. The active version is selected through
`/opt/luma`, a relative symlink. Durable settings, Google credentials, game
checkpoints, logs and backups remain in `/var/lib/luma`, outside every release.

## What an update can change

A bundle may contain exactly the compiled frontend, `backend/pyproject.toml`
and one built Luma Python wheel. Its canonical manifest lists every payload
size and SHA-256 and is signed locally with the private Ed25519 key. The Pi
checks the signature against its image-pinned public key, rejects duplicate,
traversal, linked, oversized or unlisted files, verifies wheel/package version
and refuses a changed dependency fingerprint. It never installs a bundle's
arbitrary service units, OS packages, configuration, credentials or scripts.
It also compares the wheel's `Storage.SCHEMA_VERSION` marker with the installed
source before staging; a durable-data schema change, even when the value has
not changed, requires a newly built and qualified full image. Keep this marker
and all SQLite writes backward-compatible within app-only releases so a code
rollback can still read the existing `/var/lib/luma` database. Those changes
require a newly built and qualified full image.

The signing private key is kept only on the owner's Linux signing machine at
`/home/luma-build/keys/luma-update-ed25519.pem` (directory mode 0700, key mode
0600); it is not in the Windows workspace, source tree, SD image, GitHub
workflow or Pi. The bundle tool refuses keys with permissive POSIX mode bits
and checks that the local private key matches the image-pinned public key before
it builds anything. Losing this key means making a fresh full image with a new
pinned public key; there is no bypass or remote key-rotation command.

## Build, transfer and apply

On the configured Debian WSL build machine, after tests and production frontend
build pass, run from the project root (adjust the Windows-mounted root if it
moved):

```sh
python3 "SD Card/source/tools/build-update-bundle.py" "SD Card" \
  --key /home/luma-build/keys/luma-update-ed25519.pem \
  --output /home/luma-build/luma-update-0.3.0.lup
```

Choose a version strictly greater than the installed one in
`source/backend/pyproject.toml`; never reuse a release version. The builder
rebuilds one wheel, includes the already-built `frontend/dist`, computes the
same whole-source fingerprint used for image provenance and writes a new signed
archive without putting the key in it. Copy only the resulting `.lup` file to a
temporary path on the Pi using key-only SSH while both machines can reach each
other on the local network. The Luma Tailscale gateway intentionally does not
permit SSH; campus guest Wi-Fi/client isolation may also prevent direct peer
connections.

On the Pi, inspect then explicitly apply as the owner-approved administrator:

```sh
sudo /opt/luma/venv/bin/luma-update verify /path/to/luma-update-0.3.0.lup
sudo /opt/luma/venv/bin/luma-update apply /path/to/luma-update-0.3.0.lup
```

`verify` is read-only. `apply` serializes requests with a root-owned lock,
rechecks everything, stages a separate complete
release, installs the wheel without dependency resolution or network access,
and refuses a pre-existing version. It stops only active Luma application
services/socket activators (not Wi-Fi, SSH, Bluetooth, Tailscale or the system
network), atomically switches `/opt/luma`, syncs the pointer directory, starts
the services that had been active, and requires the local health endpoint to
report the exact new version with a healthy database. A failure triggers a
second atomic switch to the previous release and service restart. Old releases
are retained; this first implementation deliberately does not prune them.
After a successful health check, the root update broker asks systemd to restart
it from the newly active release, so future checks and installs use the updated
broker code too. Its short-lived status returns to `idle` after that restart;
the Settings screen confirms completion by matching the installed app version.
After success, remove the uploaded archive yourself when convenient; Luma does
not keep a copy or upload telemetry.

A power interruption during staging leaves the old version selected. After a
complete pointer switch, the active version directory entry is synced before
success is reported. As with any SD-card filesystem, this cannot protect
against a card/controller that acknowledges writes it has not made durable.
If automatic rollback itself cannot restart services, use the separate
key-only administrator recovery route and select the previous retained
`/opt/luma-releases/<version>` with local help. Do not delete a release while
it is active.

## First-image boundary and CI

The existing commissioning card predates this updater. It cannot accept a
signed application bundle and must not be overwritten in place; the updater
arrives with the separately prepared fresh image. Physical flashing and testing
remain owner-gated.

The repository-root `.github/workflows/luma-ci.yml` runs the complete Linux
backend suite (including Linux-only tests), frontend tests, TypeScript/production
build and image-manifest tests on pushes and pull requests. CI receives no
signing secret and produces no trusted update. It regenerates required public
assets from checksum-pinned sources before running tests; generated assets and
the image itself are not committed. The workflow is active on the authorized
feature branch. Its first hosted run exposed a Linux test-fixture mismatch
between setup-python and the OS-managed interpreter used by the Pi; the fix is
in the branch. The hosted workflow previously passed end-to-end, including the
complete backend suite, frontend tests/build, and image-manifest tests. The
focused Linux updater suite at that checkpoint passed 8/8. On September 29, the
updated local source passed 977 backend tests, 124 frontend tests,
TypeScript/production build, and the updater's systemd packaging checks. Hosted
GitHub Actions run #14 passed on feature commit `64f2ce2`, covering the backend,
frontend, build, image-manifest, updater-broker, Pi Connect and wireless-package
checks. The configured Debian build machine remains an independent full-suite
gate.
