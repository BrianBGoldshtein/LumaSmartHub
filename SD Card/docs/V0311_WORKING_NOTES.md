# 0.3.11 — find a phone in a crowded Bluetooth scan

## Objective and reproduced source defect

The owner cannot locate their phone in the pairing list. Publish a fix that prioritizes readable device names and stronger signals and makes every discovered device reachable. The previous backend sorts paired status and alphabetic name, then silently slices at 40 rows. RSSI is discarded. Both primary and secondary setup render the returned rows directly. A phone beyond the cutoff cannot be found even if BlueZ discovered it.

## Implementation checkpoint

Shared backend choices now prefer readable Alias (or Name when Alias is merely an identifier), then stronger valid RSSI within named/anonymous groups. Missing readings rank last in their group; existing bonds only break ties. MAC/UUID/hex/numeric/long mixed identifier names are ranking hints, not filtered devices. No device is hidden at a top-40 cutoff. All rows retain exact path/address for secure selection and subsequent real bond/code checks.

Secondary setup still excludes other registered users' phones; it now reads that bounded registry once rather than once per scan row, avoiding a new SD-backed N+1 lookup bottleneck when the old cutoff is removed. Existing response-size security limits remain unchanged.

Both primary Bluetooth setup and personal secondary setup use one themed picker: six results per page, name/address search, full count, explicit page controls, signal labels and bounded scroll region. Anonymous devices remain accessible. Existing scan/confirmation time limits, privacy authorization, phone isolation and 0.3.10 standby cooling/load fixes remain unchanged. No OS/dependency/schema/service/root-protocol change is intended.

Contracts checked against official [BlueZ Device API](https://bluez.readthedocs.io/en/latest/device-api/) (Alias/optional Name/RSSI) and [Adapter API](https://bluez.readthedocs.io/en/latest/adapter-api/) (auto transport and discovery). Names/signals cannot prove identity; never auto-pair or trust a phone based on ranking. An undiscoverable iPhone still needs Settings → Bluetooth open; this fixes list loss, not an iOS discoverability guarantee.

## Required gates and continuation

Add backend cases for crowded scans beyond 40, named/anonymous priority, RSSI/missing/invalid readings, alias fallback, deterministic ties, every device retained and exact selection beyond the former cutoff. Add frontend search/page/selection tests and live browser checks for both setup paths, all themes, wall/mobile sizes, and matching-code confirmation without actual pairing. Then full suites/builds, exact-main CI, offline signed archive, switch/rollback using pinned published 0.3.8 and 0.3.10 installers, production download equality. Publish new immutable v0.3.11 Beta on main only after these gates. Preserve the offline key and all user state. This checkpoint is not readiness or physical Pi acceptance.

Initial focused run: 88 pairing/secondary setup tests passed before the additional constant-registry-lookup test. New cases exercise 1,201 returned devices and a target beyond row 40 that cannot be trusted/saved before its exact code is confirmed. Shared frontend has five new pure paging/search/signal cases. The new isolated browser fixture supplies 251 synthetic nearby devices, checks primary remote/mobile and wall plus secondary wall in every theme, and stops at comparison-code display/cancel—never a real radio or actual phone trust operation.

Initial candidate `e311433474e6616c4f9abdb4903dfbb477767c12` runs in `/home/luma-build/luma-0311-release.cYdYyg8L`. All 34 new backend cases passed. Browser testing reached all six primary remote/theme/width cases and the first wall comparison code. Two fixture defects were found, not suppressed: wait for the lazy Bluetooth disclosure before clicking, and register test-only wall QA endpoints before the SPA fallback. The latter returned HTML instead of audit JSON. Their logs are retained. Commit the corrected fixture, then qualify the final exact source/archive again; do not publish the earlier candidate archive.
