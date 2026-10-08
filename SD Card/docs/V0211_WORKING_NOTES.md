# 0.2.11 working checkpoint — October 8, 2026

Status: **0.2.11 Beta is signed and published** on the normal GitHub channel. Owner's last reported Pi version is 0.2.10. Install through Settings → Luma software → Check for updates → review 0.2.11 Beta → Install; no SD flash or account/bond reset.

## Owner-confirmed defect and recovery

After updating to 0.2.10, Google setup still displayed an old error-only page with no reconnect control. API/served asset probes returned 0.2.10 and the published reconnect fix. A kiosk restart did not resolve the visible problem. Opening `/?setup=google` with a unique query through Chromium did: owner reached Google setup and successfully renewed Google access. The exact browser caching/window cause is not independently proven.

## Requested permanent correction

- Serve dashboard HTML, direct HTML files, and SPA fallback HTML with `Cache-Control: no-store`. Hashed assets and API routing retain existing behavior.
- After a successfully health-checked installation, navigate to a fresh HTML URL with the installed version and refresh timestamp rather than ordinary `location.reload()`. Preserve the setup route, theme and fragment; failed installs must not take this path.
- Google setup requests use `cache: no-store`. If local setup loading fails, offer both a retry and a fresh-page **Reload Google setup** action. Protected Google catalog failures still leave the existing reconnect action available while editing/saving remains disabled; no empty choices may overwrite saved calendar selections.
- Do not delete Chromium profiles, Google credentials, client JSON, saved settings or Bluetooth bonds. Do not reflash the SD card.

## Speech-output latency

Owner reports 10–15 seconds between a command and spoken output, usually while the orb says speaking. Inspection found speaking was set before synthesis/playback, lazy Piper startup, serial full-WAV synthesis, and unconstrained native thread allocation. No stage-level owner-Pi timings establish which dominates there.

- Preload the installed Kristin worker and perform one fixed-phrase silent inference warm-up before opening microphone capture. Missing assets retain the existing explicit fallback; startup failures are bounded and never weaken wake verification.
- Use pinned Piper 1.8.0's sentence audio iterator. Bounded PCM frames start playing before later sentences finish, while single-sentence replies still require their first sentence's inference. Keep legacy WAV requests for the signed voice installer's existing smoke contract.
- Limit ONNX Runtime to two intra-op threads and one inter-op thread; disable idle spinning to share Pi 4 CPU with recognition and Chromium. No runtime/model sidecar changes are required.
- Show thinking during synthesis; speaking begins only after PCM submission, not proof of audible sound. Bound this best-effort UI phase call so it cannot introduce a long PCM stall.
- Reject malformed/oversized/truncated streams, bound pipe backpressure, clean up failed processes, and never play a duplicate fallback after even partial PCM submission. A speaker-only interrupted stream resets its protocol process but does not put a healthy model in failure cooldown.
- Voice settings expose last-reply numeric preparation, route setup, first-PCM generation, submission and total times. They are owner-local, bounded, and held in memory only; no transcript/audio is added to diagnostics. Total includes playback duration, and measurements begin after recognition.

Wake/command verification, pairing/ANCS privacy, Tetris/Pong/game state, Google grants and persistent settings remain unchanged by this speech correction.

## Verification and remaining work

Source changes and regression tests pass in the isolated Linux lab `/home/luma-build/luma-0211-verify.Us8bYwEg`: **34 targeted backend tests** (cache serving, Google OAuth, core API; 5 dependency warnings), **173 complete frontend tests**, and TypeScript/production build. The existing >500 kB frontend chunk warning remains. New tests cover HTML routes/cache policy, refreshed release HTML with settings preserved, unchanged assets/API routing, and refresh URL preservation/replacement. Existing rejected-grant Google tests remain applicable. These are source/build checks, not on-device browser acceptance or signed release qualification. An initial lab-copy attempt copied the ignored Windows venv; its specific copy process was stopped, and the successful run used source-only copies plus the existing Linux runtime. No Pi state was accessed or changed by these tests.

The guarded publisher completed all release gates. Source tests and native-host probes are not physical Pi/browser acceptance; the owner still needs to check output latency, audibility, Google recovery and saved state after installation.

### Latest qualification evidence

- Final guarded publisher passed **1,558 backend tests** (26 dependency/intentional archive warnings), **173 frontend tests**, **43 packaging tests**, and TypeScript/production build, including the first-frame partial-write regression and bounded speaking-phase call. Existing frontend chunk warning remains.
- Actual pinned Kristin model extracted from the signature-verified 0.2.4 voice package, using real native-host Piper 1.8.0, passes streaming requests, repeated worker reuse, and legacy WAV installer smoke. Native host measurements: startup including silent warm-up 1,110.7ms; short replies first PCM 66.1/78.8ms; three-sentence reply first PCM 48.8ms versus total generation 167.7ms. These are **not Raspberry Pi latency or speaker audibility results**. Probe/report: `source/tools/probe-voice-output.py`, lab `real-piper-streaming.json`.
- Real pipe/player process test requires first PCM submission before the simulated worker can generate its next sentence; tests cover invalid audio, bounded framing, no duplicate fallback, phase order and numeric-only timing validation. An initial targeted run correctly caught an outdated keep-worker test for interrupted streams; it now distinguishes pre-synthesis route failure from unread stream tails. A transient test-file indentation error was fixed before the successful rerun (119 targeted tests at that point).
- Disposable headless Chromium with a synthetic, loopback-only API verifies Google reconnect despite rejected calendars, themed initial-error recovery and fresh-page reload in all three themes. It also verifies successful reviewed updates navigate to the installed-version URL, while failed updates do not. No real Google consent, updater installation, owner browser or Pi state was accessed. Fixture/report: `backend/tests/google_recovery_preview.py`, `frontend/qa/google-recovery.mjs`, lab `browser-google-checks.json`.

### Publication evidence

- Accepted source: **68ca52aea57997fef83f8ea7368751c43f989963**, immutable tag `v0.2.11`; [exact-commit CI](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/37758800298) succeeded.
- [Published release](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.2.11) has a Beta headline and stable/main metadata required by the deployed updater.
- Offline-signed archive `luma-update-0.2.11.lup`: **1,305,560 bytes**, **31 payload files**, SHA-256 **e2f16250ef624c9df4e7ab2b921c387b84843ccaaa0d673e90c8836950fa9cb4**. Signed source digest **3030496936a537df4640fe10022cc38b48b5e8ad96a99e6f38e960e5c612f560**.
- Exact signed archive passed switch/health-success and failed-health rollback against 0.2.10. The production `latest_release('0.2.10')` downloaded GitHub's asset, verified metadata/checksum/signature/payload, and matched the qualified bytes exactly after publication.
- Schema 1 and dependency fingerprint remain unchanged; voice 0.2.4 and wake 0.2.9 pins remain. Private signing key was not sent to GitHub. Publisher log: `/home/luma-build/luma-0211-release-20261008/publish-log.txt`.

## Next release, only after 0.2.11 publication

Owner requests a cohesive minimal iPhone remote/preview companion for **0.3.0**, with no games/animations, settings and update controls, Google/calendar management, and synchronization only while the selected paired phone is Bluetooth-connected. Reuse the private Tailscale path where suitable, without special developer modes/carrier apps. Prioritize phone-specific enrollment/revocation protected by the hub PIN, a simple hub QR setup, privacy fail-closed behavior, and a deliberate architecture/security plan before implementation. Recommended assumptions may guide independent work while optional owner questions await answers. Do not mix this scope into the 0.2.11 release or mark the expanded goal complete after publishing 0.2.11 alone.

Migration caveat: the currently loaded 0.2.10 updater still uses ordinary reload. New navigation applies once the 0.2.11 frontend is running; older loaded pages cannot be retroactively changed by source edits. Owner should verify the new interface after installation and use the known fresh-URL recovery if needed during this transition. A future full reboot after successful updates remains a separate unimplemented request; no automatic reboot is claimed here.
