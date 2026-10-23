# Luma 0.3.8 cursor correction

## Required behavior

Hide the wall cursor after twenty seconds without mouse movement, restore it on real activity, start the real pointer at the far bottom-right boundary and distribute through the signed GitHub updater. Preserve accounts, settings, bonds and the existing cooling policy.

## Cause and implementation

The previous timer reset for every pointermove, including unchanged coordinates. The revised handler ignores duplicates, touchscreen movement and the bridge's reversible subpixel refresh. It uses capture listeners so dialogs cannot swallow activity. Startup and settings remain visible-pointer usable until the idle deadline.

The isolated labwc 0.8.3 / native Wayland Chromium test additionally reproduced a stale compositor cursor: computed CSS was none but 251 cursor pixels remained visible. A zero-motion refresh did not clear it. A reversible 1/256-pixel motion did. The final wall code flushes CSS before notifying the native bridge on hide/show transitions; subpixel callbacks do not restart the timer. The focused local wall alone can request the fixed refresh. The phone iframe and remote browsers cannot control it.

The existing graphical device service hosts a private same-UID Unix socket in /var/lib/luma. The hardened API uses ProtectHome, which hides /run/user; it connects only through its already-allowed data directory and never opens the display socket. The local-only API sends one fixed request with no coordinates or commands. Both native actions use the existing virtual-pointer protocol, with bounded roundtrips and no button/key/scroll requests. No root access, uinput, compiler, new package, compositor reconfiguration or systemd-unit update is needed on the Pi.

Startup parking uses normalized absolute coordinates 1.0,1.0 so the compositor clamps at its farthest output boundary. An atomic private runtime marker identifies the socket inode/session and prevents repeated warping after helper restarts. A reboot/new compositor starts a new session. Failures stay isolated from display/audio control and report a fixed cursor_startup diagnostic.

Protocol references: [wlroots virtual pointer](https://raw.githubusercontent.com/swaywm/wlr-protocols/master/unstable/wlr-virtual-pointer-unstable-v1.xml), [Wayland wire format](https://wayland.freedesktop.org/docs/book/Protocol.html). The client implements only the bounded requests required here; no generic input endpoint is exposed.

## Qualification

Focused startup/IPC/socket/protocol and idle-timer tests cover duplicate events, startup deadlines, subpixel feedback, selected runtime safety, peer ownership, stale/live socket handling, no-input-parameters API, retries and cleanup. The headless cursor fixture captures the compositor, including its native cursor, over a uniform background: visible before idle, zero cursor pixels after idle, visible again after real movement. A one-pixel inward probe verifies the normalized warp reaches the extreme bottom-right boundary. The runtime marker is checked against unwanted bridge-restart warping.

[0.3.8 Beta](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.8) is published from immutable source `6a688f3b2ef934121e89ced143d97724854267a0`. [Exact-source CI](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/39928163319) passed. Final Linux qualification passed **2,285 backend tests** in 290.25 seconds, **214 frontend tests**, **43 packaging tests** and both production builds.

Native lab: `/home/luma-build/luma-038-final.q47pHnSf`. The final-source headless check measured 251 native cursor pixels before idle, zero after idle, and 251 after movement. The measured idle wait was 19.91 seconds after the initial screenshot overhead, using a 20,000ms timer. Same-position events continued every 75ms. Exactly two native refresh requests were made, no clicks occurred, and a bridge restart did not warp the pointer. The one-pixel inward probe was 1278.99609375,718.99609375 on a 1280×720 output, confirming parking at the far boundary. An additional startup-only variant parked before Chromium launched; the new kiosk did not recenter the pointer. Logs are `native-smoke.log` and `early-startup.log`.

The full remote-browser fixture passed. All 24 shared-settings cases passed on a complete rerun in three themes at 320/390 widths with no JavaScript errors. The initial shared-settings run caught the existing transient 320-pixel onboarding overflow; no assertion or layout was weakened. Reports, active/idle/restored compositor screenshots and final logs are retained under workspace `qa/0.3.8-cursor`.

The earlier source candidate `b734d4a` was not published. Review caught that API ProtectHome hides /run/user, so final source moved only the refresh IPC socket into the existing private data directory and added regression coverage. Only the graphical helper reads /run/user or opens Wayland. The final archive was rebuilt and requalified after that correction.

The exact final signed archive passed installation and forced health-failure rollback with both candidate and pinned published 0.3.7 installers, preserving synthetic settings, Google credentials, browser grants, user profiles, timers and game state. Artifact: **2,142,428 bytes**, **92 files**, SHA-256 `928f0af6de943b8a8169519de4c507b97342346317112c4d75a591ed7b626621`; source fingerprint `a71d73b69cba1a6bcc4131271e646e8adfefdabb8a7d60b35d22dc8d14babe5d`. Luma's production `latest_release('0.3.7')` fetcher verified GitHub metadata, signature and payload and matched the qualified bytes. The release targets main, is not a draft/prerelease and carries the owner-requested Beta headline. The offline private signing key was not uploaded; previous tags/assets remain unchanged.

Physical Pi/display verification is owner-led after installation. No actual Pi has been controlled during this build.
