# Weather hints — implementation checkpoint

September 26, 2026. Implemented in source and local preview; not yet packaged in a new Pi image. Hardware testing remains owner-deferred.

## Setup and behavior

Guided setup → Choose your extras → Weather hints, or All settings → Extras. Hints are **off until explicitly enabled**, including for existing installations. Preferences persist in SQLite independently of setup navigation. Saving does not claim that a forecast or hardware connection was checked.

The screen introduces one feature at a time; advanced thresholds are collapsed by default. Unsaved fields warn before leaving the wizard and block switching to another extra. A failed load offers Retry instead of showing saveable defaults over existing preferences. No location/network yet? Save preferences now and finish the rest later. The final review distinguishes enabled hints from a saved location and still requires a fresh forecast.

One short hint replaces the weather condition text on Home, Weather and private standby. It uses existing theme typography, colors and layout, not another overlay. Current condition icons and high/low temperatures remain visible. Hints are public, disclosed during setup. They are convenience information, not emergency alerts.

Within the next six hours, priority is precipitation → gusts → heat → cold. Defaults: precipitation probability ≥50%, gusts ≥25 mph, feels-like temperature ≥90°F or ≤45°F. Whole-number thresholds are validated on both sides; cold must be lower than hot. Snow/freezing conditions are not labelled rain. Mixed or otherwise uncertain precipitation types use general wet-weather wording.

## Provider and persistence contract

The existing 15-minute Open-Meteo request now includes hourly apparent temperature, precipitation amount and wind gusts. Units are explicit (°F, mph, mm); no new poller, account, background service or library. Configured coordinates are sent to the existing provider.

Open-Meteo defines precipitation/probability over the preceding hour and gusts as that hour's maximum; weather codes and apparent temperature are instantaneous. The rule uses upcoming interval ends and deliberately says “Next 6h,” not an exact rain-start prediction. Unix timestamps preserve repeated daylight-saving hours; the parser also accepts older ISO fixtures. [Official forecast API definitions](https://open-meteo.com/en/docs).

New forecast fields are optional for old caches. Missing, null, out-of-range or non-finite optional values stay unknown, never zero. An unknown hourly probability displays “—”. Forecasts explicitly marked stale, older than two hours or dated in the future produce no hint. Browser control-connection loss also immediately removes hints and marks weather last-known. Reconnection replaces it with a fresh server snapshot.

Rules are pure computation over the existing snapshot. They do not write per tick or store a derived hint in the forecast cache. Changed coordinates still clear the old cache; existing in-flight-location protection is retained. Preferences are local-only writes; remote Shortcut tokens cannot change them. Saved microphone, timer, calendar and game configuration is preserved.

## Verification

- 25 new backend cases: threshold equality/order, configurable rules, snow/rain distinction, six-hour bounds, stale/future/missing inputs, one provider request with explicit units, malformed optional arrays, DST folds, old-cache compatibility, no extra writes, private/public behavior, atomic validation, local-only access and preserved saved mute.
- Full backend suite: **322 passed**; existing Starlette/httpx warning remains. After adding final-review fields, the 42 onboarding/weather cases passed again.
- Frontend: **78 passed**, including three new pure state/validation tests. TypeScript and production build pass; gameplay tests unchanged.
- Browser preview: unsaved checkbox warning, invalid cool/hot relationship, successful isolated preview save and one-task navigation verified. All-theme Home/Weather hint matrix at 2048×1536, 1536×2048 and 390×844: 18 checks, no horizontal overflow. Expanded setup thresholds also checked in all themes; details in `ONBOARDING_QA.md`.
- No owner coordinates submitted to a provider during testing, no account enrollment or physical device tests. Demo `fixture=weather-hint` uses explicitly synthetic values.

Remaining: cross-feature integration, final immutable image rebuild, packaged WebSocket qualification, and later physical acceptance.
