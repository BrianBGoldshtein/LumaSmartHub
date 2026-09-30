# Raspberry Pi Connect recovery access

## Current inclusion and validation

The physical r12 test exposed a first-time enrollment bug: the broker called
`rpi-connect vnc off` and `rpi-connect shell off` before sign-in. The real
packaged client rejects both commands until the Pi is signed in, so the button
failed before it could return a verification QR. A disposable QEMU boot of the
exact r12 image reproduced this. Correct date/time, working weather and a
successful Internet check do not resolve the command-order bug.

The corrected r13 image source installs the official shell-only Connect Lite
client, which has no VNC service. The broker now starts Connect, requests
sign-in, and displays a locally generated QR. After account approval, it
disables any default shell permission until the owner explicitly taps
**Enable admin remote shell**. That approval persists across broker restart
and Pi reboot. This correction is not yet physically verified, and the next
image still requires owner testing. No account password, auth key or sign-in
link is placed in the image or project files.

On the physical r13 card, the owner later reported a second failure: Luma
`0.2.0` remains "Not signed in" and Start sign-in errors after roughly twenty
seconds, despite working weather, Google OAuth, correct time and trials on
both eduroam and Stanford Visitor. A disposable boot of that exact image
measured nearly seventeen seconds for `rpi-connect on` alone, uncomfortably
close to the broker's twenty-second limit. This is a plausible timeout cause,
not yet a confirmed physical diagnosis. The signed `0.2.2` app-only candidate
uses separate longer startup/sign-in deadlines, avoids restarting an already
running client, and adds a fixed, non-sensitive on-screen `rpi-connect doctor`
check. It needs the no-flash card recovery route in
[R14_NO_FLASH_RECOVERY.md](R14_NO_FLASH_RECOVERY.md) until Connect itself works.

## Set up from the Luma touchscreen

After the corrected image is installed, first connect the Pi to Wi-Fi with
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
sharing is not installed. The account is linked to the owner's
Raspberry Pi account; enable two-factor authentication on that account and
disable remote shell from the Luma screen when you no longer need it. Disabling
shell keeps sign-in but revokes shell access; the owner's local sign-in can
enable it again.

The image enables systemd user lingering for the dedicated account so Connect
survives kiosk logouts and reboots. Its owner-approved device identity remains
on the card under `/home/luma-admin`; app-only signed updates do not replace
that account or its state. A full OS reflash does erase it and requires the
owner to enroll the newly imaged Pi again.

## Preserving settings during a new image flash

A full OS flash erases the current card's Wi-Fi, PIN, calendar and phone setup
and any Pi Connect/Tailscale enrollment. The r12 USB file browser is presently
blocked by its missing polkit authority, so USB backup has not been verified
on that device. Before reflashing, inventory what configuration has actually
been completed and preserve any recoverable settings by a supported route.
The corrected image includes the authority, but physical USB retesting is
still required. Later signed `.lup` app updates are designed to preserve
`/var/lib/luma` and the Connect identity; they cannot replace OS packages or
system services on r12.

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
