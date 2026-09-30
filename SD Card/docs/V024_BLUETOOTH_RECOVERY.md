# 0.2.4 iPhone connection recovery

Status: implemented in source and locally tested; **not yet verified on the Pi**. Do not claim that the owner's reported reconnect failure is fixed until the post-update hardware test succeeds.

The owner observed an iPhone that reported “connected” while Luma showed “iPhone connected; waiting for Bluetooth services” and remained in privacy standby. BlueZ's `Connected` property is only a link, not proof of a resolved LE GATT connection, an exposed Apple Notification Center Service (ANCS), or notification authorization. A dual-mode phone may connect on a bearer that cannot expose LE-only ANCS. BlueZ also can expose GATT objects before `ServicesResolved` becomes true. Apple's ANCS may appear or disappear during a connection; only Notification Source is mandatory.

The runtime now:

1. Discovers the saved bonded/trusted iPhone over LE before its normal periodic reconnection attempt. Where BlueZ exposes the optional `PreferredBearer` property, Luma prefers LE before connecting.
2. Accepts a live bonded/trusted link with an ANCS Notification Source GATT object even when `ServicesResolved` remains false. This does **not** grant access by itself.
3. If service resolution stalls, or resolution completes without ANCS, performs a bounded recovery at most once per five minutes: verifies the selected phone and bond; disconnects **only that phone**; waits for link teardown; requests LE bearer where supported; briefly refreshes LE discovery; reconnects if the phone has not done so; and waits for services again. It never removes the bond or changes user settings.
   A phone-initiated disconnect racing this request is accepted only after BlueZ confirms that the selected, still-bonded phone is down. If it reconnects so fast that the polling loop never sees a down edge, a fresh ANCS source is treated as progress rather than a failed reset; the source still must authorize its subscription before private content appears.
4. Subscribes to mandatory ANCS Notification Source to prove authorization before releasing private calendar information. Optional Data Source failure removes caller/details only; it does not falsely report a missing phone. Loss of the link or ANCS source returns to privacy standby. This does not promise that iOS will authorize notifications or that all iPhone/Bluetooth configurations support ANCS.
5. Shows connection phase and last service-recovery time on the local phone setup screen. These are status clues, not proof of success.

The logic follows the [BlueZ Device API](https://github.com/bluez/bluez/blob/master/doc/org.bluez.Device.rst) and [Apple ANCS specification](https://developer.apple.com/library/archive/documentation/CoreBluetooth/Reference/AppleNotificationCenterServiceSpecification/Specification/Specification.html). The preferred-bearer property is optional/experimental, so recovery remains best-effort when the installed BlueZ does not expose it. The existing app-only updater cannot alter the system BlueZ daemon configuration.

## Local evidence and next hardware check

`tests/test_bluetooth.py` covers delayed GATT resolution, ANCS arriving later, source-only ANCS, mandatory source authorization, optional data degradation, LE preference, phone-initiated reconnect during recovery, very fast reconnect without a visible down edge, disconnect-request races, bond/selection preservation, and recovery cooldown. Backend suite and on-device acceptance results are recorded separately.

After updating to 0.2.4, leave the phone near Luma, with iPhone **Share System Notifications** enabled. Turn iPhone Bluetooth off, wait for privacy standby, then on. Within about a minute, the phone setup page should move through reconnection to **Authorized ANCS session** (or **Authorized iPhone; notification details unavailable**) and private pages should return. Repeat after a Pi reboot and after walking out of range for several minutes. If it instead stalls, record the exact phase, last recovery time, whether the iPhone says connected, and whether the privacy screen opened; do not unpair until those results are captured. Do not share notification contents or Bluetooth addresses publicly.
