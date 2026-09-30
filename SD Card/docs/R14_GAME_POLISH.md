# r14 game polish (not included in r13 image)

This work began after the r13 image source was frozen. Do not describe it as part of r13 or install an unsigned build on the Pi. The app-only bundle is version `0.2.1`, newer than the image's `0.2.0`; its dependency and durable-data schema contracts must remain unchanged. Qualify it after the r13 platform is physically accepted and a safe deployment path is proven.

An offline-signed `luma-update-0.2.1.lup` candidate was built locally from feature commit `169b7bee171bb59712b6cc7c50d25de44e9587f5`. Its SHA-256 is `8df24ca9859ecdd0f2f45a4da0f6e718a35095f4bb1facc8c07c15937f258fbc`; the exact r13 verifier accepted all 31 signed payload files and confirmed its dependency/schema contracts. The archive is in the owner's local `SD Card/updates/r14-candidate-20260930` output folder, **not hosted or installed yet**. The private signing key stayed offline. Do not use the normal Settings updater for this unaccepted feature-branch candidate; its main-only release rule remains intact.

## Pong

Paddle impacts use contact offset and shot intent to choose an outgoing angle. That can occasionally coincide with the exact reverse of the incoming trajectory, creating a repetitive rally. r14 keeps the existing collision model but enforces a minimum 0.2-radian separation from the retrace angle. A regression test covers the near-retrace case. Ball and paddle tempo are not otherwise changed in this patch.

## Space Invaders

On each animation frame, r13 reconciles up to 55 individually translated alien sprites, each with an SVG drop-shadow in the Hearth and Luma Glass themes. Its physics is also subdivided at 120 Hz. This is a credible source of stutter on the Pi 4, but only hardware observation can confirm the cause. r14 moves the fleet with one group transform, memoizes its unchanged sprites, applies the visual glow once to the formation, and reduces collision-safe physics subdivision to 60 Hz. Existing movement, wave, scoring, lives, and evasion tests must remain green.

## Acceptance

- Watch at least two complete waves on the actual Pi in each theme; motion should remain steady without visible stalls.
- Confirm alien destruction updates the formation immediately and the group glow still looks cohesive.
- Confirm the ship keeps moving and still dodges shots; no skipped collisions or phantom life losses.
- Watch several Pong matches and confirm paddle hits visibly change the outgoing trajectory and avoid the repetitive retrace path.
- Verify scores and checkpoints persist across ambient scene changes and a browser/Pi restart.

An app-only signed release requires an accepted main-branch commit under the current updater policy. Until that release gate, Pi Connect may be used for diagnostics and development deployment only with an explicit, reviewed procedure that preserves `/var/lib/luma`; do not bypass the updater's signature check by placing a bundle in its release feed.
