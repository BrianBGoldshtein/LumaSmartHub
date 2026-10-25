# Luma 0.3.9 standby power and phone recognition

## Required behavior

Keep all onboard USB ports powered whenever no registered phone has a verified live connection, preserving mouse access in standby and the owner's saved cooling preference. Remove application-imposed delays between an incoming authorized phone connection and the wall leaving standby. Distribute through the signed GitHub updater without resetting data.

## Standby power

The API cooling worker uses the multi-phone presence verifier, including secondary users with no calendars or wall sharing. An empty agenda, a privacy-only display or Sleep does not by itself mean no phones are connected. Missing or failed presence checks conservatively keep power on.

The existing root broker receives its unchanged five-field protocol. A standby transition sends Keep USB on, which restores power and cancels a physical test. Subsequent heartbeats retain power without repeating restores or resetting the minimum-on timer. The UI reports a temporary standby override separately from the saved Always on or Automatic setting. Automatic returns to 70°C on / 60°C off after a verified return, with existing safety interlocks intact. An in-flight automatic request that races a disconnect is followed by a power-on request before status is returned.

The cooling worker subscribes to primary and secondary presence events so losing the last phone wakes it immediately rather than waiting for its five-second heartbeat. USB probe and confirm actions require a verified registered phone as well as primary PIN authorization and acknowledgment. There is no periodic discovery window.

## Phone recognition

Two previous waits affected incoming connections: retry backoff could reach approximately two minutes, and optional ANCS notification-detail setup preceded recognition. A read-only BlueZ observer now wakes the correct phone verifier on connection and service signals. It checks the unique BlueZ sender, retains only whitelisted link metadata and never grants presence by itself. Raw Connected, RSSI and advertisements are not authority. The five independent phone workers retain shared-radio scheduling and isolation.

Primary presence still requires a trusted live bond and successful mandatory Notification Source authorization. Optional Data Source discovery, Control Point discovery, Data Source subscription and Service Changed subscription run outside that recognition path. The worker continues fresh link checks while optional setup is pending. Secondary users retain their strict registered Address, Paired, Bonded, Trusted, Connected, ServicesResolved and not-Blocked checks, without subscribing to ANCS or reading notifications.

Lease loss publishes disconnection immediately and wakes the active worker. A BlueZ owner change revokes all old generations and starts fresh verification; failure of the optional observer alone does not invalidate an independently healthy verifier. Signal wakeups also interrupt active notice waits and secondary heartbeat pauses. No new generic Bluetooth commands, adapter resets, pairing prompts or OS packages are introduced.

The application can react immediately to verified evidence, but iOS can still delay service publication or authorization. Relevant contracts are the [BlueZ Device API](https://bluez.readthedocs.io/en/latest/device-api/) and [Apple ANCS specification](https://developer.apple.com/library/archive/documentation/CoreBluetooth/Reference/AppleNotificationCenterServiceSpecification/Specification/Specification.html). Apple's mandatory Notification Source is distinct from optional Data Source and Control Point.

## Qualification status

Focused Linux tests currently cover physical-controller standby transitions, no repeated power cycling, saved preferences, disconnect races, probe cancellation, last-phone event delivery, primary consent, secondary privacy, forged signals, five independent live private-bus sessions, incoming connections during a 120-second backoff, slow optional setup and BlueZ restarts. The first focused post-recovery run passed 75 tests. Final full-suite, browser, signing and published-asset results must be recorded before declaring release readiness.

Release source and signed artifact are not yet published. The next build must qualify installation and forced health-failure rollback using both candidate code and the pinned published 0.3.8 installer at source `6a688f3b2ef934121e89ced143d97724854267a0`. Physical Pi switching and iPhone behavior are not proven by the private Linux fixture.
