# Luma 0.3.6 cooling update

## Approved behavior

On 2026-10-14 the owner reported that physical USB fan switching worked, identified the periodic discovery window as the unwanted restart, explicitly requested removing it, and accepted using a manual USB-power override for a drive. A clarification confirmed **ON at 70°C, OFF at 60°C**. The earlier suggestion of 60/50 is superseded. Do not modify the already-published 0.3.5 tag or archive.

## Implementation

Remove only the scheduled discovery-window branch and change temperature hysteresis to 70/60. Keep the sixty-second minimum on interval, five-second physical test, primary/PIN controls, USB-storage/update/media interlocks, independent root watchdog and twenty-five-second heartbeat safeguard. The API heartbeat remains independent of an open settings page. There is no limit on normal off time while temperature, qualification and controller health are valid.

Retain the existing `max_off_seconds` response key as null and explicitly report `discovery_windows: false`. The shared wall/phone panel reads threshold values from the controller, distinguishes Automatic mode from actual power, and explains manual access before plugging in USB devices. No dependency, schema, phone, calendar, voice or game-rule changes are included.

Regression coverage includes four hours of simulated healthy off-time with ambient fluctuations below 70°C, exact on/off boundaries, state retention in the 60–70°C band, minimum on time, manual recovery after an extended quiet period, attached-drive protection, heartbeat expiry, missing temperature, update/media protection and switching faults. These are fake-power tests, not independent physical fan measurements.

## Published qualification

[Luma 0.3.6 Beta](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.6) is published on the main-targeted signed channel from immutable source tag `0dd1d84cbd69e25d48b65bb64f27cfeab451043e`. [Exact-source CI](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/38683556345) passed. The guarded local publisher passed **2,240 backend tests** (286.42 seconds), **210 frontend tests**, **43 packaging tests** and both production builds. The exact signed archive passed installation/service switching and forced health-failure rollback with both the candidate and pinned published 0.3.5 installer, retaining synthetic database state.

The first mobile audit reported horizontal overflow on the 320-pixel onboarding view; the complete rerun passed all 24 cases, including expanded cooling copy at 320/390 widths in all three themes, native phone inputs and disconnect clearing, without JavaScript errors. No onboarding CSS was changed. The final report and cooling screenshots are retained under workspace `qa/0.3.6-cooling`. The initial audit log remains `shared-qa.log` and the successful rerun `shared-qa-retry.log` in `/home/luma-build/luma-036-release.ysuk8Hpl`.

Artifact: **2,134,940 bytes**, **92 files**, SHA-256 `50cc1d7e38d702b841df4b61a1701ca54bb89a36129320c33c1e1ef376780498`; source fingerprint `a90a8916ed448947a1ae67134b74ffb960c88bc67922689a7ea713418ef92b6a`. Luma's production `latest_release('0.3.5')` fetcher downloaded GitHub's release, verified metadata/signature/payload and matched the qualified local archive byte for byte. The offline private key was not uploaded. No Pi was operated during this release; the owner's revised threshold and manual USB checks remain in the release notes.
