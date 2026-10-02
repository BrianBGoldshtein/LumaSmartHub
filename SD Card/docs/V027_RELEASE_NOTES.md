# Luma 0.2.7 Beta

This is a signed application update for an existing Luma 0.2.6 installation. It preserves local settings, Google authorization, voice assets, and saved games. It is not a new SD-card image and does not change the operating system.

- Say “Hey Luma, start a timer for 45 seconds,” “set a timer for two hours,” or add a short name such as “titled laundry.” Ambiguous spoken names or durations ask for clarification rather than silently starting the wrong timer. The touch timer also accepts seconds, minutes, and hours.
- The calendar now uses a regular whole-hour timeline while positioning events at their exact start and end minutes. Nearby events share useful screen space, and genuine overlaps move into adjacent lanes.
- Luma retries the selected iPhone connection when it is absent and bounds stalled Bluetooth service calls. Privacy mode still unlocks only when iPhone notification access is actually established; iOS may restrict when that service is available.
- The updater now restarts the Pi Connect helper along with release-bound services, preventing a new app version from leaving the old sign-in helper running. The first 0.2.7 install also has a one-time helper refresh path. The owner confirmed that a full reboot resolved the previous 0.2.6 sign-in timeout; the new update path still needs a real Pi check.

## Install and test

On Luma, open Settings → Luma software → Check for updates, review **0.2.7 Beta**, then tap **Install update** once. Keep the Pi powered throughout. Do not remove the SD card. A routine app update restarts affected Luma services, not the entire OS; if Pi Connect ever remains stale, a normal reboot remains a safe recovery step.

After the dashboard reports 0.2.7, test a named seconds-level timer and hear its completion alarm; inspect a crowded calendar interval; walk the iPhone out of range and return; and verify Pi Connect status/sign-in without a full reboot. These hardware behaviors are not certified by source tests. Report any failure with the exact screen status, not account links or private tokens.
