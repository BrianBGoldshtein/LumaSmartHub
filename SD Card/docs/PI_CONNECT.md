# Raspberry Pi Connect recovery access

## Requirement for the final planned OS image

Pi Connect is part of the **same final planned full-image update** as the
touchscreen enrollment UI and signed Luma application updater. It is not a
follow-up image or a feature deferred to a later flash. The image must ship the
official `rpi-connect` client, QR encoder, dedicated `luma-admin` account and
linger configuration, local fixed-action enrollment broker, and the
**Device setup → Connections → Raspberry Pi Connect** UI before it is
considered ready to hand off. The owner will enroll and opt in to remote shell
after first boot. Later ordinary Luma feature releases should use the signed
application updater and preserve settings and the enrolled Pi Connect state.

This means the current old card cannot receive this capability through its
app-only update path. The final planned OS image still needs to be built and
qualified as a complete update before it is flashed. Do not flash until the
existing settings have a verified backup/restore route. No separate future OS
flash is planned for delivering Pi Connect or routine Luma feature work; a
future OS/security or hardware-platform change could still require one.

Preview-only visual QA on September 29 checked the setup entry in Hearth, Luma
Glass and Neon Grid at 320×568, 390×844, 720×1280, 1280×720 and 2048×1536.
The card stayed within the viewport and interactive controls did not spill
horizontally. Demo mode correctly showed a non-actionable preview state. This
is rendered-layout evidence only—not enrollment, broker, network or hardware
acceptance.

The final planned full-image source includes a physical-screen enrollment
flow for Raspberry Pi Connect. That image has **not yet been rebuilt or
installed**; the card currently being tested predates this screen. In a fresh
image, the service is **not signed in or remotely enabled**. The owner links
the Pi and explicitly enables remote shell on its screen. No account password,
auth key, or sign-in link is placed in the image or project files.

## Set up from the Luma touchscreen

After that updated image is installed, first connect the Pi to Wi-Fi with
working Internet. Stanford eduroam or a Visitor session with its terms
accepted can provide that connection. Then:

1. Open **Device setup → Connections → Raspberry Pi Connect**.
2. Tap **Start Pi Connect sign-in**. Luma starts the official client and shows
   a locally generated, short-lived QR code and verification link.
3. Scan the QR code with your iPhone, sign in to your Raspberry Pi account,
   and approve the Luma device. The one-time link stays in memory only and
   expires after ten minutes. It is never sent to an external QR service.
4. When Luma reports **Pi linked · shell off**, tap **Enable admin remote
   shell**. This separate confirmation is required; a signed-in device alone
   cannot open a shell.
5. On your computer or phone, visit [connect.raspberrypi.com](https://connect.raspberrypi.com/),
   select **Devices → Luma → Connect via → Remote shell**.

The remote shell is the dedicated `luma-admin` account with passwordless
administrative `sudo`; treat it as full control of the Pi. Pi Connect screen
sharing is intentionally left off. The account is linked to the owner's
Raspberry Pi account; enable two-factor authentication on that account and
disable remote shell from the Luma screen when you no longer need it. Disabling
shell keeps sign-in but revokes shell access; the owner's local sign-in can
enable it again.

The image enables systemd user lingering for the dedicated account so Connect
survives kiosk logouts and reboots. Its owner-approved device identity remains
on the card under `/home/luma-admin`; app-only signed updates do not replace
that account or its state. A full OS reflash does erase it and requires the
owner to enroll the newly imaged Pi again.

## Current-image limitation and preserving settings

The card currently written predates the touch enrollment broker. Its Luma
screen has no supported control to start `rpi-connect signin`, so there is no
touch-only Pi Connect enrollment path on that install today. SSH is not needed
after a full updated image is installed: that image supplies **Pi Connect
setup in Device setup** and starts with remote shell disabled.

The signed `.lup` app updater intentionally cannot add OS packages, Linux user
accounts, system services, or other root-level configuration. Therefore it
cannot add the missing Pi Connect setup broker to this older OS. A full OS
reflash would erase on-card settings; **do not reflash until Luma's backup and
restore has been verified**, especially because this Pi has not detected the
owner's USB drive yet. Once the platform image is qualified and the data has a
verified backup/restore path, the updated image can be installed and Pi Connect
enrolled without SSH. App-only releases after that preserve `/var/lib/luma`
settings and the enrolled Connect identity.

## Network and troubleshooting

Pi Connect requires working Internet and an owner-approved Raspberry Pi
account. Its connections are end-to-end encrypted and use WebRTC; when a direct
peer connection is unavailable, Raspberry Pi may relay encrypted traffic.
Some restrictive networks can still block its required services. On the Luma
screen, refresh **Pi Connect status** first; after enrollment, use the
official `rpi-connect doctor` diagnostic from the remote shell if access fails.
Do not expose SSH or Luma's main API to Stanford Wi-Fi as a workaround.

Pi Connect is separate from Tailscale. Connect remote shell provides owner-
approved system maintenance; the optional Tailscale HTTPS gateway remains
limited to its fixed Apple Shortcut commands. VPN reachability does not reveal
private calendars or count as iPhone presence.

The official Raspberry Pi references are the [Connect setup and security
guide](https://www.raspberrypi.com/documentation/services/connect.html) and
[remote-access overview](https://www.raspberrypi.com/documentation/computers/remote-access.html).
