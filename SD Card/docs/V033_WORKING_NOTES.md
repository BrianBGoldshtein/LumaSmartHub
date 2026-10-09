# Luma 0.3.3 temperature work and qualification

## Scope and implementation

Owner requested temperature on wall Settings and the iPhone remote. Work branch: `codex/v033-temperature`. Preserve 0.3.2’s layout, progress/reboot behavior, user isolation and saved state. No dependency or database-schema changes; no new hardware, fan controller or game retuning.

`thermal.py` reads only `/sys/class/thermal/thermal_zone0/temp`, with a bounded 32-byte read and strict integer/range validation. No privileged executable, arbitrary path, persistent cache or private sensor contents are returned. Reports contain only Celsius, status and UTC sampling time. Unavailable data remains null.

The local read-only endpoint is loopback-only, rejects cross-origin requests and sets no-store. Both authorized remote projections include the same public device reading while retaining existing own-account/private field selection. Neither remote route nor mutation allowlist is widened.

The shared themed component uses existing fonts/colors and explicit warm/high text. Wall Settings polls every ten seconds with timeout, visibility gating and unmount cleanup. Remote reads use its existing five-second preview requests; all readouts expire after thirty seconds. Demo readings are explicitly examples.

## Release gates and remaining checks

Before publication: focused and full backend/frontend tests, both production builds, packaging suite, synthetic themed wall/mobile browser checks, exact-main CI, offline signature and exact-archive install/forced rollback. The publisher also pins the deployed 0.3.2 installer to `383552f5f545551f97e6df26574f770bacdc7b1f` and qualifies the same archive with it. Production GitHub download must match the qualified bytes before readiness is reported.

Hardware acceptance remains owner-led: confirm the Pi’s actual readable sensor, wall/phone samples, saved state and post-update reboot. Synthetic sensor tests do not prove hardware or Safari behavior. Publication and exact qualification evidence will be appended after these gates finish.

## Published qualification evidence

[0.3.3 Beta](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.3) was published October 8, 2026 Pacific time (October 9 at 06:35:15 UTC), targeting main with stable updater-compatible metadata and a Beta headline. Tagged source: `59174f549adaa38d8674bb9763eb787fd0e1e0f9`. [Exact-source CI 37893438834 passed](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/37893438834).

- Full local qualification: **2,184 backend / 206 frontend / 43 packaging tests**, both production builds. Backend runtime was bound to the new clean checkout/version.
- Wall Chromium fixture: `/tmp/luma-031-user-setup.Ve5oHlMV`; all theme layouts fit 1024×768, example labels are explicit, and live polling showed warm, high, unavailable and recovered normal readings without script errors.
- Authenticated TLS remote fixture: `/tmp/luma-030-mobile.WyyMFWBT`; 320/390-pixel layouts fit all themes, primary/secondary previews expose the sensor only while authorized, and existing privacy/own-account/settings/timer/update interactions passed without script errors.
- Build lab: `/home/luma-build/luma-033-release.W4vA06cb`. The initial publisher passed all tests but stopped because Git does not preserve the untracked assets directory. Creating its required empty directory allowed the source-manifest check and signing to run unchanged. No signed archive was overwritten and no source/test guard was bypassed. Future clean application build labs must create that directory before signing.
- Exact signed archive: `luma-update-0.3.3.lup`, **1,924,177 bytes**, 81 files. SHA-256: `871ed5e4f57badfa54fb1721755850483fb1f7cbf7889a33c8c234a34d439216`. Source fingerprint: `2110251dbb8b685b4b63d8eab2ed832e892ad55b3260113e1c9df2ba10683e8a`.
- Current and pinned published 0.3.2 installers both passed switch and forced health-failure rollback with the same archive. Full synthetic SQLite dumps remained unchanged, including all user profiles, scoped credentials/calendar caches, timers, grants, settings and games. Service/health responses were synthetic.
- `download-report.json` confirms the production GitHub updater signature-verified the download, matched every byte to that qualified archive and reports installed 0.3.3 as current. The offline private key was not uploaded.

Owner acceptance remains the real sensor, physical screen/Safari display and post-update reboot. No owner Pi or phone was operated during these checks.
