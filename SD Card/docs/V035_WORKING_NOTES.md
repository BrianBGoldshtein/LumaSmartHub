# Luma 0.3.5 cooling and remote settings work

Draft development on `codex/v035-usb-fan`, starting from published 0.3.4. Nothing in this branch is signed or published yet. Keep existing SD state and all published release assets unchanged. Source version stays 0.3.4 until the candidate is complete and qualified.

## Implemented local changes

The wall cursor hides after twenty seconds without mouse activity. Mouse movement, a mouse click or scrolling restores it immediately. This applies to Luma's Chromium dashboard, setup and update screen, not independent operating-system windows or the phone remote. One timer and event listeners are cleaned up during development reloads.

Cooling uses coarse on/off switching, never variable USB voltage or rapid PWM. It is opt-in: default USB power stays on. The shared wall and primary-phone panel requires a five-second physical interruption test and explicit confirmation that the fan stopped and restarted before automatic cooling can be enabled. All four ports switch together. Remove USB storage before testing; use the phone remote to recover without a working mouse.

The existing protected USB backup broker owns power switching and an independent two-second watchdog. No new root service, package dependency, OS permission relaxation, shell command or caller-specified USB path is installed. Discovery accepts only Pi 4 Model B's onboard VL805 and both internal hub views. Device files must match their expected Linux USB character-device identity. The model is read through sysfs because the existing service hides non-process procfs entries.

Policy turns power on at 60°C, allows off at 50°C or lower after at least sixty powered seconds, and limits a normal powered-off interval to sixty seconds. The next powered discovery window lasts at least sixty seconds. A drive connected during an off interval cannot be discovered until power returns. A 25-second API-heartbeat expiry, invalid temperature, detected USB storage (including unmounted/unformatted interfaces), USB backup work, or a running update keeps/restores power on. The five-second test restores independently of another API request. Switching failures disable automatic control and attempt power restoration on every port. Normal broker shutdown also attempts restoration; kernel hangs, hard kills and failed hardware cannot guarantee restoration.

Only owner-confirmed topology and cooling mode are persisted under cache `device/usb_fan_v1`; existing settings, accounts, profiles and bonds are not migrated. Changing the detected topology requires requalification. Non-enumerating fan replacement cannot be detected: disable automatic mode and repeat the physical test after changing it. Hub power bits do not measure RPM or physical USB voltage.

The signed remote adds only fixed GET/POST `device/fan` operations with the existing primary PIN lease and live phone authorization. Secondary users cannot administer cooling. The root socket still requires the local Luma UID and a strict fixed request shape. No generic remote root/USB proxy is provided.

## Full primary remote requirement

Owner requests complete parity with the hub: guided setup, all individual settings, dashboard controls, and a guided secondary-user setup. Shared UI components and validated controllers should provide parity instead of maintaining two diverging forms. Phone-native input, responsive layouts and three existing themes must remain cohesive. Secondary remotes retain only their own personal controls and timers.

The safety reviewer blocked an attempted broad settings bridge before any file was applied. Explicit owner approval is pending for remote backup export/restore, PIN/token changes, Wi-Fi/Tailscale changes, Bluetooth pairing/forgetting, secondary-user management and signed updates. These can expose private data or disconnect access. Do not retry that bridge or an equivalent workaround without approval. The attempted `companion_settings.py` file does not exist.

After approval, inventory every setup screen and action, map only reviewed operations to the existing controllers, require fresh primary-PIN confirmation for destructive actions, and preserve independent target-user consent for Google. Never accept arbitrary upstream URLs, request headers, cookies, file paths, device-agent reports or callback submissions. Any delegated personal setup grant must be isolated to one approved browser/user and checked against that user's authorized phone. Reconnection, revoke/lock, missing primary, all four secondary users, unfinished setup and in-flight revocation need negative tests.

Phone Google sign-in must retain its HTTPS Web-client callback flow, not navigate to a Pi-local Desktop OAuth callback on the phone. Microphone calibration records the Pi microphone, not Safari's microphone. USB operations act on the Pi's attached drive. Wi-Fi/Tailscale changes need an interruption warning and recovery instructions. Backup game checkpoints must come from the hub, never overwrite them with the phone browser's local game state. These are parity adaptations, not reasons to omit those controls.

## Verification and remaining gates

Focused cooling/companion/backup checks: 51 passed, including 26 new cooling tests and a signed-remote primary-lock test. The earlier thermal/backup/companion baseline also passed 43 checks. All 13 selected secondary-user refusal cases passed, including both new cooling routes. Frontend: 207 passed, including cursor timeout/reveal/cleanup. Both wall and remote production builds passed in isolated `/tmp/luma-035-ui.0wEoRvx9` using installed 0.3.4 dependencies; `build.log` retains output. The final panel error-state change was rebuilt there. Do not treat a passing source test as physical USB qualification.

Before release: resolve the remote-access approval, implement and test shared settings parity, full backend/frontend/packaging suites, both production builds, phone/wall visual checks in all themes, and a signed exact-archive update/forced rollback using both candidate and pinned 0.3.4 installer. Preserve synthetic full SQLite dumps including secondary users and credentials. Publish only after all software gates pass; hardware fan operation remains an explicit owner test. No claim of automatic fan switching working on this Pi until the physical test succeeds.

Hardware checklist: compatible onboard USB power switching/firmware; five-second fan stop/restart; mouse return; attached unmounted drive protects power; update holds power on; actual temperature cools at a quiet physical fan setting; phone Keep USB on override; drive plugged during off is discovered within the bounded window; failed test leaves automatic disabled. A fan needs a real inlet/exhaust through the enclosure.

The [uhubctl Pi 4 hardware notes](https://github.com/mvp/uhubctl#raspberry-pi-4b) describe the two ganged hub views and VL805 firmware prerequisite `00137ad` or newer. Do not automatically modify firmware. Physical fan observation remains required even if reported hub status changes.
