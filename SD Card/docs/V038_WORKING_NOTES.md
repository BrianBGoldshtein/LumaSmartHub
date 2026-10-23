# Luma 0.3.8 cursor correction

## Required behavior

Hide the wall cursor after twenty seconds without mouse movement, restore it on real activity, start the real pointer at the far bottom-right boundary and distribute through the signed GitHub updater. Preserve accounts, settings, bonds and the existing cooling policy.

## Cause and implementation

The previous timer reset for every pointermove, including unchanged coordinates. The revised handler ignores duplicates, touchscreen movement and the bridge's reversible subpixel refresh. It uses capture listeners so dialogs cannot swallow activity. Startup and settings remain visible-pointer usable until the idle deadline.

The isolated labwc 0.8.3 / native Wayland Chromium test additionally reproduced a stale compositor cursor: computed CSS was none but 251 cursor pixels remained visible. A zero-motion refresh did not clear it. A reversible 1/256-pixel motion did. The final wall code flushes CSS before notifying the native bridge on hide/show transitions; subpixel callbacks do not restart the timer. The focused local wall alone can request the fixed refresh. The phone iframe and remote browsers cannot control it.

The existing graphical device service hosts a private same-UID Unix socket. The local-only API sends one fixed request with no coordinates or commands. Both native actions use the existing virtual-pointer protocol, with bounded roundtrips and no button/key/scroll requests. No root access, uinput, compiler, new package, compositor reconfiguration or systemd-unit update is needed on the Pi.

Startup parking uses normalized absolute coordinates 1.0,1.0 so the compositor clamps at its farthest output boundary. An atomic private runtime marker identifies the socket inode/session and prevents repeated warping after helper restarts. A reboot/new compositor starts a new session. Failures stay isolated from display/audio control and report a fixed cursor_startup diagnostic.

Protocol references: [wlroots virtual pointer](https://raw.githubusercontent.com/swaywm/wlr-protocols/master/unstable/wlr-virtual-pointer-unstable-v1.xml), [Wayland wire format](https://wayland.freedesktop.org/docs/book/Protocol.html). The client implements only the bounded requests required here; no generic input endpoint is exposed.

## Qualification

Focused startup/IPC/socket/protocol and idle-timer tests cover duplicate events, startup deadlines, subpixel feedback, selected runtime safety, peer ownership, stale/live socket handling, no-input-parameters API, retries and cleanup. The headless cursor fixture captures the compositor, including its native cursor, over a uniform background: visible before idle, zero cursor pixels after idle, visible again after real movement. A one-pixel inward probe verifies the normalized warp reaches the extreme bottom-right boundary. The runtime marker is checked against unwanted bridge-restart warping.

Before publication, run full backend/frontend/packaging suites, both production builds, exact-main CI, native cursor smoke against final source, signed installation and forced rollback using candidate and pinned published 0.3.7 installers. Verify published bytes through Luma's production GitHub fetcher. Keep the signing key outside GitHub and preserve existing release artifacts.

Physical Pi/display verification is owner-led after installation. No actual Pi has been controlled during this build.
