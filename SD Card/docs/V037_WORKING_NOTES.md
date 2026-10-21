# Luma 0.3.7 release qualification

## Scope and gates

Requested changes are secondary presence without notification permission, no secondary phone notification access, and three existing bell strikes for arrivals versus one for ordinary notifications. Primary authorization, per-user privacy, sharing approval, browser grant generations, mute/sleep priorities, settings and working bonds must remain intact.

Secondary runtime branches before any GATT notification subscription. A fresh Device1 query must match the selected address, Paired, Bonded, Trusted, Connected and ServicesResolved, and must not be Blocked. Device property loss/removal immediately revokes the session; its heartbeat expires after fifteen seconds. Advertisements and saved pairing alone do not grant presence. The public BlueZ flags do not establish an independently verified encrypted link. Primary runtime retains its ANCS consent requirement. Only the primary's absent bond triggers notification-service solicitation advertising; the advertisement itself is broadcast, not addressed to an individual phone.

The arrival cue mixes three copies of the unchanged single-bell PCM at 0, 220 and 440 milliseconds into one bounded local playback. Claiming remains once-only; pure departure cues and primary notifications stay single-strike. Timer alarm audio is untouched.

## Published qualification

[0.3.7 Beta](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.3.7) is published from immutable source tag `d414e946fc664895339a891c5fde32112c295fee`. [Exact-source CI](https://github.com/BrianBGoldshtein/LumaSmartHub/actions/runs/39652947531) passed. The Linux build passed **2,256 backend tests** in 316.48 seconds, **210 frontend tests**, **43 packaging tests** and both production builds. Private D-Bus tests cover five concurrent phones, no secondary ANCS, secondary notification permission loss, primary subscription loss, blocked/disconnected/unresolved secondary phones, peer isolation and explicit secondary notification rejection. PCM tests verify the exact three-strike mixture and single local playback; existing mute, sleep, claim and timer rules pass.

The complete remote-browser fixture passed personal calendars, timers, setup, sharing, enrollment and disconnect/revocation checks. The 24-case shared-settings audit passed on a complete rerun across three themes at 320/390 widths, with no JavaScript errors. The earlier run caught the existing transient 320-pixel onboarding overflow; no assertion or UI layout was weakened. Reports and representative screenshots are retained under workspace `qa/0.3.7-presence-chimes`.

Build lab: `/home/luma-build/luma-037-release.I6fmIU7l`. The first signing attempt stopped before producing an archive because the fresh checkout lacked the ignored `source/assets` directory. After creating that empty directory, signing resumed without changing tracked source or test results. The exact archive passed installation and forced rollback twice: with the candidate installer and the pinned published 0.3.6 installer. Qualification includes preserved synthetic settings, credentials, secondary profiles, timers and game state. Logs are `publisher.log` and `signing-qualification.log`.

Artifact: **2,136,762 bytes**, **92 files**, SHA-256 `be4269efdf6c25ba1eee5235811f69b2668d01aa1a960720fadcb189971de9a4`; source fingerprint `1b915b993089a4272c128a2a7f9caef4489f17aad5b450df33b84385a5a685b7`. Luma's production `latest_release('0.3.6')` fetcher downloaded GitHub's release, verified metadata/signature/payload and matched the qualified archive byte for byte. The release targets main, is not a draft/prerelease, and has a Beta headline. The private key stayed offline. Earlier release tags and assets remain unchanged.

Physical Pi/iPhone background reconnection and subjective speaker acceptance remain owner checks; build-host tests cannot establish those.
