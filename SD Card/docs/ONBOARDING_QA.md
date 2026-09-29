# Guided onboarding — software QA, September 26, 2026

Scope: current source and locally built browser preview, **not** the delivered Pi image and not physical hardware.

## Automated evidence

- Backend `.venv/Scripts/python.exe -m pytest -q`: **272 passed**, one existing Starlette/httpx deprecation warning. Includes 17 new onboarding cases: fresh/private defaults; restart resume; explicit/idempotent finish; skipped voice retains enabled state; invalid/oversized payloads; remote token and cross-origin denial; actual summary vs review flags; preserved mute; corrupted-cache sanitization; no extra secret fields; immutable transition input.
- Frontend `node --experimental-strip-types --test tests/*.test.ts`: **72 passed**, including five new onboarding workflow cases and unchanged gameplay regressions.
- `node node_modules/typescript/bin/tsc -b`: passed.
- `node node_modules/vite/bin/vite.js build`: passed; static production preview rebuilt. No new runtime dependencies.

## Browser checks

- Walked welcome → network → space → privacy → calendar → phone → review in demo. Verified ordinary edit warning, save-and-continue, on-screen-key edit warning and explicit discard. No real passwords/PINs or credentials entered.
- Pairing preview disables Continue/Back/defer during the active session, exposes Cancel pairing, then allows finishing later. No radio operations in demo.
- Skipping optional connections reaches review without fake connected/tested badges. Reload without a forced demo step restores review. Native-sized screenshots inspected for Neon Grid welcome and Hearth review; Glass welcome also inspected. Existing Google colors preserved in the calendar panel.
- 36 DOM layout checks: welcome/space/calendar/review × Glass/Hearth/Neon Grid × 2048×1536, 1536×2048, 390×844. No horizontal overflow; one main landmark per wizard screen. Long setup pages intentionally scroll vertically.
- A further 45 checks covered network/privacy/phone/voice/remote at those same themes/sizes: no horizontal overflow (81 total). Finishing review successfully opened the ordinary dashboard with the selected theme.
- Browser automation's pointer coordinates were unreliable while the in-app viewport override was active. Verified workflow activation with supported keyboard controls at the normal viewport instead. This is **not** evidence that physical touch alignment works; that remains deferred.

## Remaining gates

### Later extras increment

September26 source now includes timer and opt-in weather preferences under a one-task chooser, not a growing mandatory form. New final-review rows use saved preferences, not navigation flags. Full suites322backend/78frontend pass; TypeScript/build pass. Browser exercised unsaved checkbox warning, invalid cool≥hot threshold, safe preview save and return to chooser. Nine expanded-threshold layouts (all3themes×2048×1536/1536×2048/390×844) had one main landmark and no horizontal overflow. Eighteen Home/Weather hint layouts also passed at those sizes. Viewport DOM dimensions were checked explicitly. No actual hardware, owner account or location submission.

The timer real-network test found and fixed a missing WebSocket dependency which in-process tests missed. Do not infer live-update support from old image HTTP checks; next packaged-image acceptance must include the actual event stream.

Rebuild a new immutable Pi image from final source; rerun image/static/ARM64 software qualification. Existing Tailscale image remains unchanged and does not include the wizard. On the assembled Pi, separately verify actual touch scaling/alignment, on-screen/system keyboard focus, captive portal return, Google OAuth consent/return, Bluetooth notification presence, microphone/echo handling, display/audio settings and reboot/power-loss behavior. Owner must initiate that hardware phase. Expansion-specific feature cards await their implementations as documented in `EXPANSION_PLAN.md`.
