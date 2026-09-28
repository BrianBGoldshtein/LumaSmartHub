# Final non-hardware review — September26,2026 UTC

Scope: the completed `tailscale-20260926` candidate, after feature implementation and image integration. This is a software/file/architecture review against the supplied Pi4/Thinlerain/ReSpeaker brief. It is **not physical acceptance, a penetration test, or certification of every upstream OS package**. The owner explicitly deferred all real hardware testing.

## Exact artifact and evidence

Archive SHA256: `22c0c58ef341a57d4c6d7f86dd56eb10abc0e1a7ba7a1250c2e7cc3ca99a0860`;612409576bytes. Source fingerprint: `8001c2fddd91a249dbeef9e2365b93106f91e09ce4901e73e1cfdc9f2055a35b`. Matching receipts are in `image/qualification-tailscale-20260926/`.

- **112 shipped files compared byte-for-byte:** every installed Luma Python module/resource, complete built frontend (including fonts/notices), complete Vosk model, asset licenses, all mapped system configuration, qualification tools, keyboard source archive/patch/recipe, and the HAT boot overlay/configuration. Every `source/system` input was explicitly classified. `file-audit.json` lists each digest; `image-builder/audit-image-files.py` reproduces the read-only check. Build-only installer inputs are fingerprinted rather than mistaken for runtime files.
- The actual raw root partition matches the ext4 sidecar: `395075ed96a5db016cd9f9172ffd9811e78131a0b01884518417672ca5e16050`. The separate raw check additionally verifies pinned Tailscale binary bytes, sensitive file modes, scoped campus trust, wireless country, first-boot SSH key generation and disabled transport defaults.
- Tailscale/tailscaled and the generated native keyboard are AArch64 ELF. All12 native libraries in the installed Python environment were inspected: AArch64, not Windows/x86 binaries. These include Vosk, evdev, spidev, pydantic, CFFI and cryptography. Python3.13 is actually installed in the image.
- **255 backend +67 frontend +18 packaging +9 checker tests passed.** Frontend TypeScript and production build passed. Tetris timing was not changed; bundle `index-DAC0tGYc.js` is the verified image bundle.
- An isolated180-second ARM64 emulator run returned API/database health at86.554257guest seconds, then gateway authentication rejection and the real Tailscale broker's NeedsLogin response at101.801182. Runner exit0; underlying QEMU timeout124 is the deliberate stop *after* required markers, not the success criterion. No network adapter, account enrollment, base-image mutation or concurrent compression.
- Separate isolated network tests permit443 and deny22/8742/8743 for IPv4 andIPv6. Rules reload without erasing unrelated tables. This does not prove a live tailnet or campus certificate flow.
- XZ integrity and portable checksum passed; Windows independently hashed the delivered copy. Older candidates and their evidence were preserved.

## Hardware and runtime mapping

| Constraint | Packaged implementation | Remaining physical gate |
| --- | --- | --- |
| Raspberry Pi4,ARM64,2GB | Pi4 image layer; kernel6.18.50+rpt-rpi-v8; Python3.13.5; ARM64 native libraries | Sustained RAM/CPU/thermal behavior with Chromium+voice+animations+VPN |
| Thinlerain9.7in,2048×1536,4:3 | Chromium153.0.8010.52; labwc0.20.1; responsive local UI; wlr-randr power/rotation | Actual EDID/native mode, touch mapping and fullscreen rendering; no invented HDMI timings |
| ReSpeaker2-Mics V1,WM8960 | Exact pinned overlay plus kernel WM8960,bcm2835-I2S and simple-card modules; PipeWire1.4.2/WebRTC AEC, WirePlumber0.5.8 | Capture/output routing, real echo cancellation, LED wiring and far-field calibration |
| Campus-only internet | NetworkManager; manual Visitor portal; pinned Stanford SUNet TLS profile | Association, terms page, actual server rejection, NTP/time and reconnect |
| Private iPhone commands | Pinned Tailscale1.102.4, kernelTUN/nftables modules, private HTTPS to8743, fixed-action local broker | Sign-in, certificate issuance, account policy, iPhone/campus reachability |
| Nearby-phone privacy | Selected bonded/trusted authorized ANCS, expiring PIN, private startup | iPhone permission/range/reconnect; VPN is never presence |
| EnduranceSD/outages | Immediate SQLite FULL/WAL commits, seven backup slots, validated restore, game checkpoints | Power cuts and card/controller behavior; same-card backups do not cover card failure |

Versions above come from the exact build inventory, not assumptions about current upstream releases. The SPDX2.3 inventory contains2721package and37908file entries; SHA256 `d01980b315f31810919533aa1042bad3a235bad26c1b55e490257fc67099b579`.

## Security, persistence and maintenance review

The privileged API is loopback8742; the optional command gateway is loopback8743 with a fixed command vocabulary and token verification. Fresh-image daemon/gateway are disabled. Setup is local-only, bounded, UID-checked and does not accept shell arguments, URLs, routes or credentials. Saved VPN identity is root-only and outside SQLite backups; no identity is in the image. No Funnel, VPN SSH, subnet routes or exit node is enabled. Token replacement is local and invalidates old commands. Keep a personal two-device account with narrow access rules.

The approved recovery administrator intentionally has full sudo through its dedicated key; the kiosk has no sudo grant. Private keys were neither read nor copied. SSH on the physical campus interface still depends on key-only policy; this Tailscale integration does not make it remotely available. File permissions are not encryption against SD theft.

Source review and tests cover calendar colors, sleep/privacy transitions, stale provider caches, bounded voice/calibration, authenticated pairing, protocol parsing, persistence and autoplay lifecycle. No unimplemented feature placeholder was found in the current application paths. Default Hey Luma is local bounded recognition, not a general assistant or trained speaker identity. Siri-only Bluetooth audio was superseded by the owner's accepted Siri-on-phone/local-voice split. ANCS islands remain notifications, not authoritative cross-app active-call status.

Documentation now points to the actual delivered image and distinguishes source/emulator evidence from physical acceptance. [Third-party notes](THIRD_PARTY.md) record included notices and corresponding keyboard source; the React MIT notice was added alongside the delivered archive. This is not a public redistribution/license-clearance claim. Build recipes record versions but apt/pip downloads are not a complete reproducible lock; future builds need new verification. Static Tailscale and campus certificates require reviewed maintenance.

## Concerns to resolve on the assembled device

1. **2GB performance/heat:** architecture is compatible, but no host or emulator test establishes acceptable wall-mounted frame rate, microphone latency or thermal margin. Use the planned cooling/ventilation. If measurements require reducing rendering load, discuss the visual tradeoff; do not retune frozen games silently.
2. **Brightness and display timing:** DDC/CI may not exist on this panel. The app reports unsupported brightness instead of pretending success. If native EDID/touch/brightness fails, inspect the real controller first; custom timings, touch transforms or a software-dimming fallback need a device-specific decision.
3. **Time and power:** Pi4 has no on-board battery-backed RTC. After an extended unpowered period, accurate time/TLS/calendar scheduling depends on restoring network time. Do not assume offline timekeeping is exact. Confirm a stable separately powered display, correct HAT orientation and adequate Pi supply; avoid unverified back-power wiring.
4. **External authorization:** Google production OAuth setup, phone ANCS permissions, Tailscale approval/HTTPS and campus policies cannot be completed or proven without the owner's devices/accounts. Saved authorization survives ordinary reboots but providers can revoke/expire it.

These are documented acceptance gates, not fabricated passes or reasons to change the selected hardware now. No consequential architecture change was made during this review. Do not flash or test physical hardware until the owner prompts. Follow [the complete physical checklist](HARDWARE_VALIDATION.md) then.

## Optional next features — proposals, not installed promises

After the baseline passes hardware acceptance, the best small additions would be:

- A large **focus/countdown island**, controlled by touch and Hey Luma, that remains readable during normal screen cycling.
- A private **leave-soon card** using the next event's time and a manually chosen preparation buffer, without collecting location history.
- A **frame-friendly night clock** at very low brightness for nights when the owner explicitly wants a clock instead of full screen-off.
- A **USB backup reminder/export workflow** so the existing recovery snapshots also protect against card failure; any export containing tokens must be protected and explicitly approved.

They are deliberately light on RAM and third-party accounts. They do not alter the accepted sleep/privacy behavior unless enabled. Additional hardware/appliance automations require the actual appliance and desired action before implementation; do not invent or trigger household actions.
