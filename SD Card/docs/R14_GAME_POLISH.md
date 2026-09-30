# r14 game polish (not included in r13 image)

This work began after the r13 image source was frozen. Do not describe it as part of r13 or install an unsigned build on the Pi. Qualify it as an app update after the r13 platform is physically accepted and a safe deployment path is proven.

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
