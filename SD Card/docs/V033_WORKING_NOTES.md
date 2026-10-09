# Luma 0.3.3 temperature work and qualification

## Scope and implementation

Owner requested temperature on wall Settings and the iPhone remote. Work branch: `codex/v033-temperature`. Preserve 0.3.2’s layout, progress/reboot behavior, user isolation and saved state. No dependency or database-schema changes; no new hardware, fan controller or game retuning.

`thermal.py` reads only `/sys/class/thermal/thermal_zone0/temp`, with a bounded 32-byte read and strict integer/range validation. No privileged executable, arbitrary path, persistent cache or private sensor contents are returned. Reports contain only Celsius, status and UTC sampling time. Unavailable data remains null.

The local read-only endpoint is loopback-only, rejects cross-origin requests and sets no-store. Both authorized remote projections include the same public device reading while retaining existing own-account/private field selection. Neither remote route nor mutation allowlist is widened.

The shared themed component uses existing fonts/colors and explicit warm/high text. Wall Settings polls every ten seconds with timeout, visibility gating and unmount cleanup. Remote reads use its existing five-second preview requests; all readouts expire after thirty seconds. Demo readings are explicitly examples.

## Release gates and remaining checks

Before publication: focused and full backend/frontend tests, both production builds, packaging suite, synthetic themed wall/mobile browser checks, exact-main CI, offline signature and exact-archive install/forced rollback. The publisher also pins the deployed 0.3.2 installer to `383552f5f545551f97e6df26574f770bacdc7b1f` and qualifies the same archive with it. Production GitHub download must match the qualified bytes before readiness is reported.

Hardware acceptance remains owner-led: confirm the Pi’s actual readable sensor, wall/phone samples, saved state and post-update reboot. Synthetic sensor tests do not prove hardware or Safari behavior. Publication and exact qualification evidence will be appended after these gates finish.
