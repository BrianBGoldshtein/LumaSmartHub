# Luma 0.3.4 bell work and qualification

Owner requested a less electronic, iPhone-like notification bell in 0.3.3. Because 0.3.3 was already published, this change uses immutable follow-up version 0.3.4 Beta. Branch `codex/v034-notification-bell`; preserve the published assets and existing temperature readouts. No new dependencies, schema or copied proprietary media.

`notification_cue_pcm` retains strict 0–100 integer volume validation and delegates to a bounded eight-entry memory cache. It generates one 1.2-second, 22,050 Hz mono signed-16-bit bell: 659.25 Hz body with slightly inharmonic resonances, short smoothed attack, faster decay of bright modes and a smoothstep tail to zero. The sum of mode weights stays below one, preserving the old 12%-of-full-scale peak ceiling even at maximum chime volume. Actual perceived loudness/timbre requires owner listening.

Existing speaker-route selection, notification claim/at-most-once behavior, Sleep/screen-off/privacy silence and saved volume remain unchanged. Timer alarms are not changed. The same bell also supplies already-existing arrival/departure announcements. Settings copy names the bell without changing any control layout or theme token.

Release gates: focused PCM/claim/playback tests, full backend/frontend and packaging suites, both builds, exact-main CI, offline signature, exact-archive switch and forced rollback with both candidate and pinned published 0.3.3 installer (`59174f549adaa38d8674bb9763eb787fd0e1e0f9`), then production GitHub download equality. A clean lab must create the ignored `source/assets` directory before source-manifest/signing. Owner acceptance is the real speaker’s bell character, saved volume, privacy/night silence and unchanged timer sound.

## Published release evidence

[0.3.4 Beta](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.4) was published October 8, 2026 Pacific (October 9 at 06:56:24 UTC), with stable updater metadata targeting main and a Beta headline. Tagged source: `55f9aadd3037f75c8df708a6ecf692dbc7c9f5e0`. [Exact-main CI 37895303009 passed](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/37895303009).

- Focused notification/presence tests: 38 passed. Full guarded publisher: **2,186 backend / 206 frontend / 43 packaging tests**, both frontend builds, offline signature and both current/published 0.3.3 switch/forced rollback paths. Entire synthetic SQLite dumps remained unchanged, including profiles, scoped Google data, timers, browser grants, settings and games. Service/health responses were synthetic.
- PCM checks confirm exactly 1.2 seconds at 22,050 Hz mono signed-16-bit, smooth zero-valued endpoints, ringing without a silent two-note gap, decaying energy, multiple resonances, volume scaling, zero at mute and no clipping. The eight-entry cache remains in process memory only. This is not physical listening acceptance.
- Build lab: `/home/luma-build/luma-034-release.WGu99hT7`; source/version binding was refreshed before the full suite. `publisher.log` retains all test/signing/qualification output.
- Signed archive: `luma-update-0.3.4.lup`, **1,924,476 bytes**, 81 files. SHA-256: `d22fcb7883baa590adbc10ea6ca6fa69f8255b100208f053388a90843923fa7d`. Source fingerprint: `7c37e002789e02dd0b3df08e81fe508b0449045b8bf892806ee716c3cceb742f`.
- `download-report.json` confirms production GitHub download signature verification, identical bytes to the qualified archive, and installed 0.3.4 reporting Current. No offline private key was uploaded, and 0.3.3 assets/tag were not changed.
- A generated 70%-volume preview WAV is outside the repository at `C:/Users/brian/OneDrive/Documents/ChatGPT/Smart Wall Screen/luma-notification-bell-preview.wav`. Playback gain on a laptop/phone differs from the real hub. The bell is original local synthesis, not an Apple recording.

Owner checks remain hearing a new alert on the Pi, retained volume/quiet behavior, unchanged timer alarm and successful post-update reboot. No owner Pi or speaker was operated during qualification.
