# Luma 0.3.7 release qualification

## Scope and gates

Requested changes are secondary presence without notification permission, no secondary phone notification access, and three existing bell strikes for arrivals versus one for ordinary notifications. Primary authorization, per-user privacy, sharing approval, browser grant generations, mute/sleep priorities, settings and working bonds must remain intact.

Secondary runtime branches before any GATT notification subscription. A fresh Device1 query must match the selected address, Paired, Bonded, Trusted, Connected and ServicesResolved, and must not be Blocked. Device property loss/removal immediately revokes the session; its heartbeat expires after fifteen seconds. Advertisements and saved pairing alone do not grant presence. The public BlueZ flags do not establish an independently verified encrypted link. Primary runtime retains its ANCS consent requirement. Shared notification-service advertising now includes only the primary.

The arrival cue mixes three copies of the unchanged single-bell PCM at 0, 220 and 440 milliseconds into one bounded local playback. Claiming remains once-only; pure departure cues and primary notifications stay single-strike. Timer alarm audio is untouched.

## Verification before publication

Run selected-bond invalidation and real private D-Bus five-phone sessions, including absent secondary ANCS, secondary notification permission loss, primary ANCS loss, disconnects and independent peers. Check exact three-strike PCM, one local playback, cue selection, failure/no replay and existing suppression rules. Run complete backend/frontend/packaging suites, both UI builds and themed guided-setup browser checks.

Publish only a clean exact-main candidate after CI passes. Sign offline, then qualify the exact archive with candidate and pinned published 0.3.6 installers, including forced rollback and preserved state. Verify the GitHub-downloaded bytes with Luma's production release fetcher after publishing. Record hashes, counts and reports here.

Physical Pi/iPhone background reconnection and subjective speaker acceptance remain owner checks; build-host tests cannot establish those.
