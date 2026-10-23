# Luma 0.3.8 Beta

The wall cursor hides after twenty seconds without meaningful mouse activity and returns when you move the mouse. Repeated same-position hover events from changing dashboard content no longer restart the timer. A native Wayland refresh also clears Chromium's stale cursor image, which could remain visible even after the page requested no cursor.

At desktop startup, the real pointer moves to the extreme bottom-right output boundary, with no intentional margin. This happens once per graphical session; a device-bridge restart does not move an already-active mouse again.

The refresh moves just 1/256 pixel and reverses it. It never clicks, presses keys, scrolls, grabs a device or changes USB power. It runs only when the local wall requests a cursor-image refresh, not on a periodic input-injection timer. Phone remotes cannot trigger it. No compositor settings or OS packages are changed.

## Install and check

Use Settings → Luma software → Check for updates → review **0.3.8 Beta** → Install. Keep power connected through the verified reboot, then confirm version 0.3.8. No reflash or settings reset is needed.

After reboot, check the pointer starts at the far bottom-right edge. Move it into the middle of the dashboard, stop for twenty seconds and confirm it disappears while the dashboard continues cycling. Move it again and confirm it returns. Repeat on a settings page. Existing USB cooling still controls all onboard ports together; use the primary phone's Keep USB on override if the mouse is unpowered.

Settings, Google accounts, user profiles, Bluetooth bonds, phone browser enrollment, game saves and the 70°C on / 60°C off cooling policy are retained. Physical Pi/display acceptance remains this owner check; the native cursor test uses an isolated headless Linux display, not your Pi.
