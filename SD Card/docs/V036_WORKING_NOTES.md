# Luma 0.3.6 cooling update

## Approved behavior

On 2026-10-14 the owner reported that physical USB fan switching worked, identified the periodic discovery window as the unwanted restart, explicitly requested removing it, and accepted using a manual USB-power override for a drive. A clarification confirmed **ON at 70°C, OFF at 60°C**. The earlier suggestion of 60/50 is superseded. Do not modify the already-published 0.3.5 tag or archive.

## Implementation

Remove only the scheduled discovery-window branch and change temperature hysteresis to 70/60. Keep the sixty-second minimum on interval, five-second physical test, primary/PIN controls, USB-storage/update/media interlocks, independent root watchdog and twenty-five-second heartbeat safeguard. The API heartbeat remains independent of an open settings page. There is no limit on normal off time while temperature, qualification and controller health are valid.

Retain the existing `max_off_seconds` response key as null and explicitly report `discovery_windows: false`. The shared wall/phone panel reads threshold values from the controller, distinguishes Automatic mode from actual power, and explains manual access before plugging in USB devices. No dependency, schema, phone, calendar, voice or game-rule changes are included.

Regression coverage includes four hours of simulated healthy off-time with ambient fluctuations below 70°C, exact on/off boundaries, state retention in the 60–70°C band, minimum on time, manual recovery after an extended quiet period, attached-drive protection, heartbeat expiry, missing temperature, update/media protection and switching faults. These are fake-power tests, not independent physical fan measurements.

## Release gates

Before publication: run the full backend, frontend and packaging suites; build both production entries; check cooling copy in the themed phone settings; verify exact-source CI; sign offline; qualify the exact archive's installation and forced rollback with both its candidate installer and pinned published 0.3.5 installer (`eeea9bbd3d0beecb618ceae234525ec73c34a384`). Publish on main with a Beta headline, then verify production GitHub download signature and equality with the qualified local bytes. Do not claim owner acceptance of the revised thresholds before hardware feedback.
