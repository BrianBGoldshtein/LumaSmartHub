# Hardware commissioning — September 27, 2026

Owner paused additional feature implementation and requested setup of the hardware now available. The expansion goal remains paused; this work only packages and checks the current baseline, flashes the approved card if checks pass, and assists first boot.

## Latest outcome — September 28, 2026

The selected candidate is `image/commissioning-20260927/luma-pi4-UNVERIFIED.img.xz`. Raspberry Pi Imager visibly showed **Write complete** for Raspberry Pi 4 and reported that the SDXC card was automatically ejected safely. The card is written; do not rebuild or reflash it as a next step. This is not a physical boot qualification: Pi, display, touch, HAT audio, Stanford network, Google, iPhone, power recovery and other integrations remain untested. Continue with the HDMI/network first-boot checks only when the display path is ready. The thin panel's input is mini-HDMI, so a micro-HDMI-to-full-size-HDMI adapter needs a further HDMI-to-mini-HDMI link to connect directly to that panel. A regular HDMI TV/monitor can be used temporarily with the adapter and an ordinary HDMI cable; keyboard/mouse may replace touch for that temporary screen. No Ethernet cable is available.

## Card authorization

Owner confirmed **YES** to erasing the detected 128 GB microSD for Luma. Before the completed flash, read-only Windows inspection found disk 1, Realtek PCIE CardReader, 127999672320 bytes, MBR, non-system/non-boot, removable exFAT D:. Disk 0 was the Windows Samsung NVMe and was never selected. Raspberry Pi Imager later displayed successful completion and safe ejection. These disk numbers/letters describe the earlier inspection only; they are not a current connected-device identity.

## Build and software verification record

The old session references and interrupted-job notes below are historical. The final candidate was completed, compressed, checked and flashed; no image build or flash job is currently needed.

- Fresh Linux staging: `/home/luma-build/luma-commissioning-20260927`.
- Build log: `/home/luma-build/image-build-commissioning-20260927.log`.
- Original builder session 44070 disappeared before package assembly completed; process inspection confirmed no builder/compressor remains. Original staging/log preserved, no image produced.
- Retry snapshot: `/home/luma-build/luma-commissioning-20260927-r2`, dedicated user service `luma-commissioning-20260927-r2`, log `/home/luma-build/image-build-commissioning-20260927-r2.log`. Inspect service and log before retrying.
- Linux full backend: 878 passed after correcting test-only trusted-clock fixtures; terminal 0, session 40103. First run 64943 had two clock-assumption failures; production privacy rules unchanged. Receipt `/home/luma-build/qualification/commissioning-20260927-backend.txt`.
- Linux packaging/service checks: 22 passed. Corrected countdown/transit tests: 37 passed on Windows.
- Windows backend: 870 passed, 8 Linux-only skipped; terminal 0, session 68009.
- Frontend: 110 passed; TypeScript/Vite passed; terminal 0, session 11872.
- Frontend bundles: `index-BWAeLOj6.js`, `index-ClFeiWBa.css`.
- Existing public recovery key copied into staging; private key untouched and excluded.
- The final flashed candidate and its receipts are in `image/commissioning-20260927/`; other historical images are not the current card contents.
- Raspberry Pi Imager was used with its system-drive protection and verification left enabled. It reported **Write complete** for Raspberry Pi 4 and automatically safely ejected the storage. No active image writer remains to resume.
- Earlier build interruptions and the r2 recovery session below document how the candidate was produced; those session handles are no longer active. Do not resume/restart them based on this historical log.
- First-boot checker regression: 9 passed under Linux. Windows cannot import its Linux `pwd` dependency; no production change needed.

## Owner's available connections at the time of flash

Pi and power supply are present; the candidate is already written to the microSD. At the last owner update, the display was not connected and they were waiting for a micro-HDMI-to-HDMI adapter; no Ethernet cable is available. Confirm the adapter/cable ends: the original monitor brief specifies mini-HDMI at the screen. USB touch is separate from HDMI video. No Wi-Fi credentials, hotspot, network sharing or headless-network profile were requested/configured. Use the screen's local onboarding for Stanford Visitor or eduroam rather than speculative headless Wi-Fi. Do not claim reachable SSH merely because its public key is packaged.

The software/image gates described above passed before this card was written. Preserve the current candidate and receipts; do not reflash unless a concrete image fault is found. Physical touchscreen, HDMI, ReSpeaker, network and iPhone tests remain first-boot acceptance, not emulator claims.

## Interrupted expansion state

The older CURRENT_STATUS.md foundation-only scene heading is stale. Before the pause, production scene adapters, presence/runtime workers, local API, and themed scene editor were added, with source tests. They remain opt-in/disabled on a fresh image and are not fully qualified for appliance automations. Native voice scene dispatch, remote appliance allowlists, encrypted USB backup, full scene UI/race qualification remain unfinished. Do not enable room automations during initial commissioning or represent these extras as complete. No new feature implementation or game timing changes are part of commissioning.
