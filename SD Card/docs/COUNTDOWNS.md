# Important-date countdowns — implementation checkpoint

September26,2026: source implementation and software UI/integration checks are complete: store, API, exact Google-reference refresh, themed Dates slide, date/event picker, Extras/onboarding integration and offline voice navigation. No final-image update, owner-account call or hardware test was performed. Feature7 is source-qualified, not Pi-qualified.

## Implemented contract

- At most12 records, stable UUID IDs and optimistic revision checks. Manual title/date/optional time/timezone/annual/public; public defaults false. SQLite cache `countdowns/items`, version1. Writes occur on edits/provider refresh, never countdown ticks. Disk-write failure restores in-memory state. Corrupt/unknown stores remain untouched and report recovery_error rather than silently overwriting data.
- Dates2000–2100; IANA timezone per item. Current settings timezone changes do not silently move an existing manual date. Repeated DST hours use the first occurrence; explicit nonexistent wall times are rejected. A future annual occurrence landing in a DST gap moves forward by that gap. Annual February29 uses February28 in non-leap years and returns to February29 in leap years.
- Date-only labels Today/Tomorrow/days; timed targets within24hours use rounded-up hours, then Reached. Ordinary past dates stop appearing on the slide after their local date ends, but remain in configuration for editing/removal. Annual records advance after their anniversary day ends. No automatic deletion or score/game changes.
- Private records are omitted from ordinary private snapshots; explicitly public records may appear. All dates are suppressed during night/off/waking/untrusted-clock states. Setup endpoints are loopback-only and require the private dashboard to be unlocked after commissioning; first-run setup can save dates before optional phone/PIN enrollment.
- Google pins refer to one exact occurrence ID, not a repeating series. Original Google calendar/event colors and live title/start changes are retained. Pinning refetches the event, rejects cancelled/declined/series records and duplicate pins, and never writes to Google. Stale/unavailable/deleted/unlinked are distinct;404 is unavailable (could be lost access),410/cancelled is removed. Old data is retained rather than invented or replayed.
- On-demand selection uses one25-result page in an explicit1–93day future window, through2100. A next-page token supports more results. No year-long bulk sync, no title query in URLs. Searches have a five-second throttle. Provider calls use existing read-only consent and bounded existing transport/no retries.
- Independent300-second refresh loops only over saved Google pins (maximum12), serializing each provider operation through the existing Google lock. Empty/manual-only configurations make no provider requests. Manual refresh is globally limited to once a minute and cannot overlap an existing refresh. Slow responses use revisions and cannot restore an item removed/changed during the request. Privacy is rechecked before search results or pin mutations return.

## API interfaces

`GET /api/v1/countdowns` → `{items,views,limit,recovery_error}` with no-store. Each raw item includes id/revision/source/title/public; manual records add date/time/timezone/annual; Google records add calendar_id/event_id/start/all_day/timezone/colors/state/checked_at.

- `POST /api/v1/countdowns/manual`: `{title,day,at:null|HH:MM,timezone,annual:false,public:false,item_id?:uuid,revision?:uuid}`. Add when ID absent; editing needs current revision.
- `PATCH /api/v1/countdowns/{id}/visibility`: `{revision,public}`.
- `DELETE /api/v1/countdowns/{id}`: JSON `{revision}`. Local unpin only, never Google deletion.
- `POST /api/v1/countdowns/search`: `{calendar_id,start:YYYY-MM-DD,end:YYYY-MM-DD,page_token?:string}`. End is exclusive. Returns minimal event records `{id,calendar_id,title,start,end,all_day,color}` plus next_page.
- `POST /api/v1/countdowns/google`: `{calendar_id,event_id,public:false}`; uses server-fetched title/date/colors, not client-supplied metadata.
- `POST /api/v1/countdowns/refresh`: no payload.

Dashboard snapshot has `countdowns`: only display-safe views containing id/title/public/source/target/date/timed/label/value/unit/state/past/color. The frontend uses these views without keeping event contents in browser storage.

## Frontend implementation and checks

- Dates slide: at most3 entries,8-second pagination, remembers only next page number between slide visits. Large single-date treatment, long-title clamp, safe Google colors, pixel-theme units. Five-digit values use a bounded size to fit portrait without changing all title typography.
- Dates joins cycling only when display-safe dates exist. Private entries are removed on connection loss; retained public Google-ready entries become stale. Private standby shows explicit public entries only. Night suppression remains backend-authoritative.
- One-task CountdownSetup inside Dates & travel: manual first; optional time/timezone/annual collapsed; public disclosure; read-only Google calendar/date-window/paged occurrence search; exact-event refetch before pin. Save/discard/unpin confirmation, busy state, local403 recovery and parent unsaved guards. Native date/time inputs handle input as well as change events, preventing a visible value from saving the old React state in the browser QA environment. Native picker icons use dark color scheme.
- Onboarding review uses saved private/public counts. First-run manual setup needs no phone or Google. After commissioning, setup hides/unmounts when privacy locks. Voice supports “show countdowns” and “show dates”.
- Owner clarified that whole-calendar countdowns refer to **Leave soon**, not Important Dates. This feature remains manual dates or individual Google occurrence links.

## Remaining delivery integration

Feature10 must include dates in settings-only encrypted export with a strict allowlist; Google-linked entries restore unlinked, without cached account data. Include source in the new immutable image and exact-file audit. No owner account or physical testing was performed.

## Evidence and sources

Latest full suite:560backend and95frontend tests pass; TypeScript/build pass. Five frontend countdown tests cover pagination/colors/cycle/privacy/stale handling. Backend date tests cover annual/DST/CAS/errors/recovery/limits/Google refresh/concurrent privacy and unpin races.

Real browser with temporary `tests/countdown_preview.py` on8747: manual save/edit/reload retained December10 (caught and fixed native-input old-state issue), dirty guard/discard, paged synthetic Google search including429 recovery, public pin and local unpin. `tests/countdown_live_check.py` passed real HTTP/WebSocket full-to-private transition, persisted browser edits, public-only snapshot and configuration403. Browser locked setup confirmed no titles; no external provider or hardware worker ran. Fixture stopped after QA. Script is intentionally for this temporary fixture only and expects browser-created sample records.

18 layout cases: Dates with long titles/five-digit values and expanded date setup ×3themes×native landscape/portrait/narrow. Initial portrait number overflow corrected and rechecked. All12sample dates reachable across4pages; private preview shows only public entry. Single-date hero visually checked. These are software checks, not target-panel qualification.

Google's [events.list reference](https://developers.google.com/workspace/calendar/api/v3/reference/events/list) specifies occurrence expansion, result pagination, exclusive date bounds and read-only scope support. The [events.get reference](https://developers.google.com/workspace/calendar/api/v3/reference/events/get) provides the exact-ID lookup used for pins. Future links use these APIs, not scraping or bulk annual calendar downloads.
