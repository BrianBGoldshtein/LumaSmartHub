# Luma 0.3.9 standby power and phone recognition

> Owner hardware result, 2026-10-25: installation failed the real health check and restored 0.3.8. Do not retry 0.3.9. Historical software qualification below did not predict that physical startup stall. See [0.3.10 investigation](V0310_WORKING_NOTES.md) for the reproduced radio-load defect and recovery gates.

## Required behavior

Keep all onboard USB ports powered whenever no registered phone has a verified live connection, preserving mouse access in standby and the owner's saved cooling preference. Remove application-imposed delays between an incoming authorized phone connection and the wall leaving standby. Distribute through the signed GitHub updater without resetting data.

## Standby power

The API cooling worker uses the multi-phone presence verifier, including secondary users with no calendars or wall sharing. An empty agenda, a privacy-only display or Sleep does not by itself mean no phones are connected. Missing or failed presence checks conservatively keep power on.

The existing root broker receives its unchanged five-field protocol. A standby transition sends Keep USB on, which restores power and cancels a physical test. Subsequent heartbeats retain power without repeating restores or resetting the minimum-on timer. The UI reports a temporary standby override separately from the saved Always on or Automatic setting. Automatic returns to 70°C on / 60°C off after a verified return, with existing safety interlocks intact. An in-flight automatic request that races a disconnect is followed by a power-on request before status is returned.

The cooling worker subscribes to primary and secondary presence events so losing the last phone wakes it immediately rather than waiting for its five-second heartbeat. USB probe and confirm actions require a verified registered phone as well as primary PIN authorization and acknowledgment. There is no periodic discovery window.

## Phone recognition

Previous waits affected incoming connections: retry backoff could reach approximately two minutes, optional ANCS notification-detail setup preceded recognition, and an outgoing job could be queued behind another phone. A read-only BlueZ observer now wakes the correct phone verifier on connection and service signals. A newly completed incoming link can also leave its queued or outstanding outgoing request, using the existing ownership-aware cancellation cleanup that preserves completed links and never disconnects peers. Fresh role-specific verification still follows. The observer checks the unique BlueZ sender, retains only whitelisted link metadata and never grants presence by itself. Raw Connected, RSSI and advertisements are not authority. The five independent phone workers retain shared-radio scheduling and isolation.

Primary presence still requires a trusted live bond and successful mandatory Notification Source authorization. Optional Data Source discovery, Control Point discovery, Data Source subscription and Service Changed subscription run outside that recognition path. The worker continues fresh link checks while optional setup is pending. Secondary users retain their strict registered Address, Paired, Bonded, Trusted, Connected, ServicesResolved and not-Blocked checks, without subscribing to ANCS or reading notifications.

Lease loss publishes disconnection immediately and wakes the active worker. A BlueZ owner change revokes all old generations and starts fresh verification; failure of the optional observer alone does not invalidate an independently healthy verifier. Signal wakeups also interrupt active notice waits and secondary heartbeat pauses. No new generic Bluetooth commands, adapter resets, pairing prompts or OS packages are introduced.

The application can react immediately to verified evidence, but iOS can still delay service publication or authorization. Relevant contracts are the [BlueZ Device API](https://bluez.readthedocs.io/en/latest/device-api/) and [Apple ANCS specification](https://developer.apple.com/library/archive/documentation/CoreBluetooth/Reference/AppleNotificationCenterServiceSpecification/Specification/Specification.html). Apple's mandatory Notification Source is distinct from optional Data Source and Control Point.

## Published qualification

[0.3.9 Beta](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.9) is published from immutable source `544d817e40a1df9bf96ef152167d932492d03d97`. [Exact-source CI](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/40170730762) passed. The final clean Linux publisher passed **2,306 backend tests** in 294.25 seconds, **214 frontend tests**, **43 packaging tests** and both production builds. No new OS package, dependency or database schema is required.

Coverage includes actual USB controller policy with a fake physical switch, no repeated power cycling, saved preference retention, disconnect races, probe cancellation and last-phone event delivery without UI polling. Private Linux D-Bus sessions exercise all five phone workers, consent denial, secondary notification isolation, sender forgery rejection, incoming links during a 120-second backoff, slow optional discovery/subscription, BlueZ owner restart, incoming primary/secondary links while the shared radio queue is held, and an incoming connection during an unfinished Connect. Incoming verification in those fixtures must finish within two seconds without peer disconnects; that bound is not a physical iPhone measurement.

The earlier full run exposed three fixtures that expected disconnection to remain stale until worker cleanup. Their assertions now require immediate disconnection, while explicit stale-state injections continue proving that legacy/UI flags cannot restore calendar or voice authority. The earlier locally signed candidate `95c5ad7` passed its software/install gates but was not published: review identified the additional queued/outstanding radio case, which the final source fixes and tests. No previous published tag or asset was replaced.

The final-source complete remote browser fixture and all **24 themed shared-settings cases** passed, with no JavaScript errors or horizontal overflow. Three themes and 320/390-width phone views were exercised, including the shared cooling settings. Earlier candidate browser runs reproduced the pre-existing transient onboarding measurement race; the final exact-source run passed without changing an assertion or production layout.

Final lab: `/home/luma-build/luma-039-ship.JHMDKl4Y`. The exact signed archive passed successful install and forced health-failure rollback using both candidate code and the pinned published 0.3.8 installer at `6a688f3b2ef934121e89ced143d97724854267a0`, preserving synthetic settings, Google credentials, browser grants, profiles, timers and game state. Archive: **2,147,047 bytes**, **92 files**, SHA-256 `727151720ccd8dc6b43c794cba6a2ff7e6cf6997e2e408c04c919c575638e781`; source fingerprint `fa54038e62b12a3eadcca12f42d6c07b75065c40ee128c22a9884b81334adbf1`.

After publication, Luma's production `latest_release('0.3.8')` verified GitHub metadata, signature and payload and matched the qualified bytes. The release targets main, is not a draft/prerelease, and carries the owner-requested Beta headline. The private signing key stayed outside GitHub and the archive. Final reports, publisher log and cooling-settings screenshots are retained under workspace `qa/0.3.9-standby-reconnect`.

## Remaining owner acceptance

Install through the GitHub updater and verify the fan and mouse stay powered when the last registered phone disconnects. Verify Automatic remains selected and resumes its 70°C on / 60°C off policy after a verified phone returns, subject to the minimum-on delay. Check actual iPhone-to-wall recognition timing after an incoming connection, including returning after absence. Physical Pi switching and iPhone negotiation are not proven by the private Linux fixture; no actual Pi was controlled for this build. Preserve the existing card and working bonds.
