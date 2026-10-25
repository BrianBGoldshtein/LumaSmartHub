# Luma 0.3.9 Beta

USB power stays on whenever no registered phone has a verified connection. This keeps the fan and mouse powered in standby, including after a disconnect or reboot. Your saved Automatic cooling preference is not changed. Once a registered phone returns, Automatic resumes its existing 70°C on / 60°C off policy and minimum-on safety delay. There are no periodic USB discovery windows.

Luma now reacts to incoming Bluetooth connection and service signals instead of waiting for the reconnect backoff to finish. Optional notification-detail discovery and subscription no longer delay a verified arrival. Lost connections and Bluetooth service restarts also wake the affected phone workers immediately, without restarting the adapter or disconnecting other users.

Primary-phone privacy still requires notification-service authorization; secondary users still need only a verified registered Bluetooth connection and their notifications are never read. Luma removes its own avoidable waits, but cannot force iOS to finish Bluetooth services or authorization instantly.

## Install and check

Use Settings → Luma software → Check for updates → review **0.3.9 Beta** → Install. The primary phone remote can also install it. Keep power connected through the verified reboot, then confirm version 0.3.9. No reflash, re-pairing or settings reset is required.

With Automatic already qualified, disconnect all registered phones. Confirm the fan and mouse stay powered and the cooling panel reports the standby override while retaining Automatic as the selected mode. Connect a registered phone and confirm the override clears; cooling may retain power for its existing minimum-on period. With several phones, the override should begin only when the last verified phone disconnects. USB fan testing is disabled without a connected phone so the mouse cannot be stranded.

On the iPhone, reconnect to Luma and check that the wall leaves standby promptly once Bluetooth services and primary authorization are ready. Repeat after leaving and returning. If it still lags, report the connection-status sentence and whether the iPhone was waiting for authorization or already fully connected.

Settings, Google accounts, profiles, Bluetooth bonds, browser enrollments, timers and saved games are retained. Physical fan switching and actual iPhone negotiation remain owner-led checks after installation.
