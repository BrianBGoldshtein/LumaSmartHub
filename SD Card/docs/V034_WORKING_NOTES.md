# Luma 0.3.4 bell work and qualification

Owner requested a less electronic, iPhone-like notification bell in 0.3.3. Because 0.3.3 was already published, this change uses immutable follow-up version 0.3.4 Beta. Branch `codex/v034-notification-bell`; preserve the published assets and existing temperature readouts. No new dependencies, schema or copied proprietary media.

`notification_cue_pcm` retains strict 0–100 integer volume validation and delegates to a bounded eight-entry memory cache. It generates one 1.2-second, 22,050 Hz mono signed-16-bit bell: 659.25 Hz body with slightly inharmonic resonances, short smoothed attack, faster decay of bright modes and a smoothstep tail to zero. The sum of mode weights stays below one, preserving the old 12%-of-full-scale peak ceiling even at maximum chime volume. Actual perceived loudness/timbre requires owner listening.

Existing speaker-route selection, notification claim/at-most-once behavior, Sleep/screen-off/privacy silence and saved volume remain unchanged. Timer alarms are not changed. The same bell also supplies already-existing arrival/departure announcements. Settings copy names the bell without changing any control layout or theme token.

Release gates: focused PCM/claim/playback tests, full backend/frontend and packaging suites, both builds, exact-main CI, offline signature, exact-archive switch and forced rollback with both candidate and pinned published 0.3.3 installer (`59174f549adaa38d8674bb9763eb787fd0e1e0f9`), then production GitHub download equality. A clean lab must create the ignored `source/assets` directory before source-manifest/signing. Owner acceptance is the real speaker’s bell character, saved volume, privacy/night silence and unchanged timer sound.
