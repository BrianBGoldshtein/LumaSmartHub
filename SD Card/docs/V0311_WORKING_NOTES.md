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

## Final-source qualification checkpoint — 2026-10-25

Final source: `50921b306f007c0f04c4ce80bba4fc5d29f57e22`. Clean lab: `/home/luma-build/luma-0311-final.9rJDwfA7`. The final publisher passed **2,351 backend tests** in 294.32 seconds, **219 frontend tests**, **43 packaging tests**, both production builds, and exact-archive switch plus forced health-failure rollback using candidate code and pinned published 0.3.8 and 0.3.10 installers. The earlier candidate archive is unpublished and superseded; no published artifact is replaced.

All **12 crowded-pairing browser cases** passed on final source: primary remote at 320/390 widths, primary 1024×768 wall and secondary wall, in all three themes. They verify six rendered rows, live count of 251, correct first named/strong-signal row, next/previous pages, no-match clearing, compact address search, accent-insensitive name search for the target beyond the old cutoff, no horizontal overflow, wall on-screen keyboard/remote native typing, exact selected path, matching comparison code, no trust before approval, and cancellation closing the driver. Screenshots were inspected for the primary remote, primary wall and secondary wall. No actual phone or radio is used. The complete private TLS remote fixture and all **24 themed shared-settings cases** also passed; final source required no retry or weakened assertion.

The same 1,201-device inventory against unchanged published 0.3.10 returned 40 and omitted the target. Final code returns all 1,201 and places the named, stronger target first. Unit coverage additionally tests a weak target remaining selectable beyond row 40, missing/malformed signals, readable Alias/Name fallback, identifier demotion, reverse-input deterministic ordering and constant-cost secondary registry reads with another user's bound phone still excluded.

Published archive: **2,152,471 bytes**, **92 files**, SHA-256 `e6df311521dd90a65c9cba26e5ff73caaa7e5f3ff69ab3c2af7a4902ae2234ed`; source fingerprint `cf6434ce2a3556e548ae27f20527cea7fcf7c6c8f110909c5af48e4342fa6dfb`. Verified contents include the actual backend sort/no-cutoff code, the secondary snapshot correction and the compiled shared picker—not just a changed version label. [Exact-source CI 40178201599](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/40178201599) succeeded before [v0.3.11 Beta publication](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.11). The release targets main and is neither draft nor prerelease. Luma's production `latest_release` from both 0.3.8 and 0.3.10 verified metadata, signature, payload and byte-for-byte equality with this exact archive. No previous tag/asset was replaced; the private signer stayed offline. Logs, before/after report and nine screenshots are retained under workspace `qa/0.3.11-pairing-list` without synthetic TLS keys/browser profiles. Do not claim physical iPhone discovery has been tested.

## Completion audit

| Requested result | Authoritative evidence |
| --- | --- |
| Readable names before identifiers | `readable_name`, backend ranking cases, first real browser result |
| Stronger signals prioritized | backend RSSI ordering/missing-value cases and browser signal label |
| Crowded scans do not silently omit phones | same-inventory 40-versus-1,201 report, full path-set equality test |
| Usable list for every eligible result | shared paging/search helper exhaustively visits 181 rows; 12 real browser cases test page/search controls |
| Primary and secondary themes stay cohesive | one shared component/CSS; three-theme wall/mobile screenshots, overflow and keyboard assertions |
| Pairing/privacy remain safe | comparison-code/trust-order tests, real UI exact-path selection/cancellation; secondary bound-phone exclusion retained |
| Publish through signed main updater | Immutable v0.3.11, exact-source CI success, production signed download equality from both supported installed versions |

Actual RF discovery, iOS advertising and physical Pi update acceptance remain owner checks. Keep iPhone Settings → Bluetooth open nearby and preserve the card and working bonds.

## Install via Pi Connect without a working wall mouse

Prefer Settings → Luma software when accessible. Otherwise run this once in Pi Connect's remote shell. It uses the existing signed broker, not an unverified pull or forced health bypass; settings/accounts/bonds are preserved.

```sh
sudo -u luma /opt/luma/venv/bin/python - <<'PY'
import asyncio, base64, json
from importlib.metadata import version
from luma.github_updates import latest_release
from luma.update_broker import update_request
current = version('luma-smart-screen')
print('Downloading and verifying the signed update...', flush=True)
release = latest_release(current)
if release.get('state') != 'available' or release.get('version') != '0.3.11':
    raise SystemExit('Expected update unavailable; nothing installed. Current: ' + current)
result = asyncio.run(update_request({'action': 'install',
    'bundle': base64.b64encode(release['bundle']).decode()}))
print(json.dumps(result, indent=2))
PY
```

Keep power connected through installation/reboot; an accepted request is not installation success. Reopen Pi Connect afterward and run:

```sh
curl --max-time 15 -fsS http://127.0.0.1:8742/api/v1/health
```

Require version `0.3.11`, status `ok`, database `ok`. Open iPhone Settings → Bluetooth before scanning. Search the iPhone's actual name (or address if known); unnamed/identifier-only results are still on later pages. If the phone is still missing from all results, report that rather than repeatedly forgetting bonds; the next distinction is whether BlueZ receives its advertisement/name at all. If installation rolls back, retain update/API logs rather than retrying or erasing the card.
