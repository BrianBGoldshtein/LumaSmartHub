# 0.4.0 — published independent GPIO fan switching

Owner goal, delivered below: research a cheap GPIO-controlled switch powered by USB, provide ordering/wiring details, implement a guided option in shared wall/primary-remote settings, and publish as **0.4.0 Beta** per the owner's explicit version request. Preserve microphone, USB Wi-Fi and mouse, current 70°C-on/60°C-off behavior, saved settings and the signed GitHub Beta update workflow. No live GPIO or Pi mutation authorized/performed. No subagents requested. Do not recreate this goal. Early lab names may contain 0314; they predate the owner's version instruction and are not release versions.

Baseline main 798489e8c128d21cbc8334740645844812b9c920; immutable published 0.3.13 source 1fbde838a8e0dd9249ff613b7b8e1f5fce514b78. Actual checkout is LumaSmartHub-0.2.4/SD Card. No preexisting uncommitted changes. Reference qualified lab/venv: /home/luma-build/luma-0313-qualified.xmxGwulp. Use WSL Debian root for its root-owned build files and per-command exact safe.directory for the Windows checkout. Native Windows Git is much faster for diff/add/commit than scanning OneDrive through WSL. Private offline signer stays at its established path; never print/read/copy/upload it.

Research: 8086 USB2 Power Switch, PiShop.us $3.45/in stock before shipping; maker Lectronz $2.68 before UK shipping. Active-high EN >2V, 5V-only USB input, micro-USB input/USB-A output, normally OFF pull-down; PiHut documents 2.5A switch rating but Pi4 total USB is 1.2A. See GPIO_FAN_SETUP.md. V1 ReSpeaker digital Grove exposes BCM12/13; BCM12 is physical pin 32, not I2S physical12/BCM18. Keep microphone; no V2 assumption. Needs power cable and Grove-to-jumper breakout/header match. Board default-off/line release is not hardware fail-on; never claim full crash protection. Root watchdog only covers loss of API/browser while broker runs.

Implementation: new gpio_fan.py uses fixed BCM12, Pi4 model + bcm pinctrl chip/line identity, exclusive GPIO ABI v2 atomic initial ON and readback; no caller-selected path/polarity/PWM, no packages or /dev/mem. GPIOFanController reuses qualified USB policy, ignores USB storage/network guards for the separate fan but retains update/thermal/heartbeat/physical-test gates. FanController coordinator restores/holds whole hub ON before GPIO activation and never cuts USB in GPIO mode. It allows moving away from a latched USB off-switch fault only when restored readback is ON. FanRuntime persists backend only for gpio12, preserves old USB cache format, disarms qualification on migration and fault, and leaves GPIO auto cooling active in standby while USB stays on. Shared FanControlPanel has guided connection choice/ack and fan-only test messaging. The outer Device summary is now Fan cooling; affected existing QA navigation labels updated. New QA-only fake hardware/clock endpoints never ship in the application. Not yet published.

Focused Linux checks in /home/luma-build/luma-0314-dev.cmCpj9hD passed **83 tests**, including C compilation against installed Linux GPIO headers (ioctl constants, sizes/offsets), fixed-pin-only requests, atomic initial high/readback, busy/wrong-model/line rejection, symlink/regular-file rejection, fd cleanup/retry, unchanged thresholds/minimum-on, heartbeat/probe restoration, invalid temperature, update cancellation, USB Wi-Fi/storage continuity, no repeated USB power writes, fault persistence, primary acknowledgment/revocation, secondary exclusion and cache migration/restart. An interrupted connection selection durably saves the disarmed wiring intent before a broker call. Frontend **224 tests** and both builds passed (the standard build already builds both clients; an unnecessary nonexistent build:remote command stopped an early pipeline before browser tests, not a product/build failure).

Guided browser QA had fixture timing assumptions corrected: wait for the loaded compact settings accordion, wait for completed asynchronous actions before asserting power state, and use the wall's directly rendered panel rather than assuming the phone accordion exists there. Six mobile/theme cases reached the wall stage before the latter fixture error. No controller assertion, timeout or privacy gate was weakened. The test clock advances must keep the real API heartbeat at five-second cadence when simulating normal operation; a >25s advance without one correctly invokes the watchdog. Run all nine cases again and then clean-source qualification; no readiness claim yet.

The original qualification plan below has now been completed; see Final publication. Physical owner testing remains explicit. Keep this distinction when resuming development.

## Final-source qualification checkpoint

The development nine-case GPIO browser rerun passed, zero JavaScript errors, in lab /home/luma-build/luma-0314-dev.cmCpj9hD, log gpio-browser-qualified.log, directory luma-030-mobile.yimwVld0. Screenshot review then found the inherited full-width checkbox style centering acknowledgments above their text. A scoped themed checkbox rule now aligns them alongside labels; each GPIO layout asserts 20–24px checkbox width and left alignment. Production source is **7f25edef2f4d3156be12707ec7fcbda2afd8711e**, pushed to main; preceding feature commit d5efc314b8c72bde17d9ce3edcc2a3dbd0dbbcbd is superseded and must NOT be published. Only styles and the layout assertion changed after d5; no backend test gate was weakened.

Final clean frozen-runtime lab: **/home/luma-build/luma-040-final.dj0yGqgI**. Full publisher (tests/builds, offline signing, candidate and pinned 0.3.8/0.3.13 switch/rollback) runs as exec **23854**, log publisher.log. Exact-source GitHub Actions run **42435069863**. Final six-browser pipeline runs as exec **62261**: gpio-browser, fan-browser, shared-settings-browser, remote-browser, roster-browser, pairing-browser logs in that lab. It has actual wall/primary-signed browser transport, fake hardware/accounts only. Watch these exact processes; don't restart on an observation timeout.

Superseded d5 lab /home/luma-build/luma-040-qualified.PsqjFAD5 had publisher51696/browser73592. Its backend pytest and QA harness were interrupted only after matching their /proc cwd and exact arguments to this obsolete lab, to release shared QA ports for final-source tests. QA harness cwd is frontend/qa, not frontend. An initial final-port wait40150 expired before cleanup and ran no UI cases; after revalidating/stopping that exact obsolete harness, final62261 started. This was source supersession, not a timeout-based test restart. Never claim the interrupted d5 full suites passed or publish an archive from it.

That checkpoint's publication gates are completed below. Full objective scope is software + ordering/wiring guidance + published release, not delivery/physical Pi acceptance. No purchased board or actual pin has been tested.

## Final publication — 2026-11-07

[Luma 0.4.0 Beta is published](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.4.0), stable/non-draft metadata targeting main, immutable tag/source **`7f25edef2f4d3156be12707ec7fcbda2afd8711e`**. The superseded d5 archive was never published. [Exact-source CI 42435069863](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/42435069863) succeeded. Final clean lab **`/home/luma-build/luma-040-final.dj0yGqgI`** completed **2,437 backend tests** (330.81s, three existing dependency/malformed-archive warnings), **224 frontend tests**, **43 packaging tests** and both production builds. No tests were skipped/weakened to pass.

All six final-source signed-browser suites passed, zero JavaScript exceptions: **nine GPIO** cases (primary remote320/390 and wall1024 in all three themes), **nine existing cooling**, **24 shared settings**, **six main remote layouts plus its complete lifecycle**, **18 connected-roster**, and **12 crowded-pairing** cases. Coverage includes real signed primary transport and PIN checks, secondary exclusion, wiring acknowledgment, disarmed migration, fan-only probe/independent restoration, physical-observation acknowledgment, 70/60 control with simulated normal API heartbeat, USB never cut despite storage/network, returning to hub control, narrow layouts, aligned theme checkboxes and existing private-data clearing. Corrected Hearth mobile and Neon wall screenshots were inspected. These are fake power objects/phones/accounts, not proof of a real fan or iPhone.

The exact same signed archive passed successful switch and forced health-failure rollback with candidate code and both pinned published installers: **0.3.8** `6a688f3b2ef934121e89ced143d97724854267a0`, **0.3.13** `1fbde838a8e0dd9249ff613b7b8e1f5fce514b78`. Synthetic settings, credentials, profiles, grants, timers and game state survived. Archive **2,162,781 bytes**, **92 payload files**, SHA-256 **`7ddedf7aa36cd6e8ed4c99536f51fbf7d2ebfc310efe06bf7acf294d1cf776ce`**; signed source fingerprint **`02097fecbf61808d15e68ebbad21dbf4bb238072d4576fec370fe444c7f48c8a`**. Storage schema remains 1 and dependency fingerprint remains `986f6f0a0f2eaa86c4bfd4b59ee98b564f6177920a70d79c7fa9808da50e83ba`. No OS package, service-unit, capability or /dev/mem change. The sole root-request expansion is a fixed usb/gpio12 enum, never arbitrary GPIO/path/polarity/PWM. The private key stayed offline and was never uploaded.

After publication, production `latest_release` checks with installed-version inputs 0.3.8 and 0.3.13 verified the signature and returned bytes identical to this qualified archive. Packaged wheel inspection confirmed the fixed BCM12 code, ioctl-v2 constants/NOFOLLOW, coordinator dispatch and protected selection commands; compiled JS/CSS contains the new guided panel and alignment rule. Full publisher, CI log, all six browser reports/logs/PNGs, verifier metadata and production-download report are retained outside Git at workspace **`qa/0.4.0-gpio-fan/final`**. No TLS private keys or browser profiles were copied. Linux originals remain in the final lab.

Primary references additionally verified the Raspberry Pi 6.12 driver label `pinctrl-bcm2711`,58 lines, and [Pi4 device-tree GPIO12 name/offset](https://raw.githubusercontent.com/raspberrypi/linux/rpi-6.12.y/arch/arm/boot/dts/broadcom/bcm2711-rpi-4-b.dts). This supports the fixed identity check; it does not replace an actual Pi test. Portable settings restore updates only its named cache entries and does not erase the target's device/fan cache; app updates retain it. Do not transfer a physical fan test approval to different wiring by hand.

## Install and configure

Install through **Settings → Luma software → Check for updates → review 0.4.0 Beta → Install**. Retain power through reboot, confirm **0.4.0**, refresh the phone remote. Do not reflash, reset or re-pair. Installing alone retains existing USB control and claims no GPIO pin. Leave it selected until the new board is wired with Pi power disconnected.

Follow [GPIO_FAN_SETUP.md](GPIO_FAN_SETUP.md): board listed at $3.45 before shipping, micro-USB supply cable and Grove-to-jumper leads, existing fan/microphone retained, BCM12/physical pin 32 to EN, ground to GND, board 5V header unused. Shared wall/primary remote **Device → Fan cooling → Move fan to a GPIO switch** saves the connection disarmed, then requires a new actual five-second stop/restart observation before Automatic. GPIO mode keeps USB on and continues 70/60 cooling in standby; software update, missing temperature or lost API heartbeat requests fan-on. Normally-off boot/released-line behavior means total broker/kernel/power failure is not hardware fail-on. Bypass to directly powered USB if the fan does not run.

## Install via Pi Connect

Prefer Settings. If it is inaccessible, run once in Pi Connect's shell. This accepts only the signed 0.4.0 release and uses the existing health-check/rollback installer; older version-pinned instructions deliberately refuse newer releases.

```sh
sudo -u luma /opt/luma/venv/bin/python - <<'PY'
import asyncio, base64, json
from importlib.metadata import version
from luma.github_updates import latest_release
from luma.update_broker import update_request
current = version('luma-smart-screen')
print('Downloading and verifying Luma 0.4.0...', flush=True)
release = latest_release(current)
if release.get('state') != 'available' or release.get('version') != '0.4.0':
    raise SystemExit('Expected update unavailable; nothing installed. Current: ' + current)
result = asyncio.run(update_request({'action': 'install',
    'bundle': base64.b64encode(release['bundle']).decode()}))
print(json.dumps(result, indent=2))
PY
```

Keep Pi power connected through installation and reboot. Accepted is not installation success. Reopen Connect afterward:

```sh
curl --max-time 15 -fsS http://127.0.0.1:8742/api/v1/health
```

Require version **0.4.0**, status **ok** and database **ok**; refresh the remote. If it rolls back, preserve update/API logs and report, rather than repeatedly retrying or erasing the card.

## Completion audit and physical acceptance

| Owner requirement | Current evidence |
| --- | --- |
| Cheap board, GPIO control and USB fan power | Maker's active-high5V USB2 switch spec, current PiShop/maker prices, cable/SKU list and wiring diagram in GPIO_FAN_SETUP |
| Settings option and execution on hub/primary remote | Shared guided FanControlPanel, strict FanCommand, fixed-line protected broker; signed-primary/secondary tests, nine themed wall/mobile cases, compiled archive inspected |
| Keep USB Wi-Fi powered while controlling only the fan | Coordinator simulations with network/storage present, all nine GPIO browser cases assert no USB-off requests, heartbeat/thermal/update/fault tests |
| Existing settings and safe update workflow | Preserved cache format/default USB, durable disarmed selection, three exact-archive switch/rollback paths and production download equality |
| Publish as 0.4.0 | Immutable v0.4.0 Beta tag/release on main, exact-source CI success, signed published archive verified through production updater |

The requested development, instructions and publication are complete. Actual board delivery, wiring, fan current/startup, physical stop/restart and 70/60 cycling, USB continuity, microphone/speaker function and reboot startup remain owner hardware acceptance. No actual GPIO or physical fan switching was performed for this release.
