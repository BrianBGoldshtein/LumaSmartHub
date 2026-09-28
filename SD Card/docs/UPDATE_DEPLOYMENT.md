# Signed in-place application updates

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

The signing private key is kept only on the owner's Linux build machine at
`/home/luma-build/keys/luma-update-ed25519.pem` (directory mode 0700, key mode
0600); it is not in the Windows workspace, source tree, SD image, GitHub
workflow or Pi. Losing this key means making a fresh full image with a new
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
signing secret and produces no trusted update. The repository has not yet been
connected to a GitHub remote or given an initial commit, so the workflow is
prepared locally but is not active on GitHub. Until that is owner-configured,
the same Linux test/build gates are run in the configured Debian build machine.
