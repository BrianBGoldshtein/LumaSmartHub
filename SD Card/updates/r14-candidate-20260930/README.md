# Signed r14 test candidate — not a stable release

`luma-update-0.2.1.lup` is an app-only update for a physically checked r13 Pi running Luma `0.2.0`. It contains the r14 Pong and Space Invaders polish from source commit `169b7bee171bb59712b6cc7c50d25de44e9587f5`. It is not an OS image and must not be flashed.

SHA-256: `8df24ca9859ecdd0f2f45a4da0f6e718a35095f4bb1facc8c07c15937f258fbc` (1,085,719 bytes). Its signature, payload, dependency contract and storage schema were verified with the exact r13 verifier and image-pinned public key. The offline signing key is not in this repository or on the Pi.

This artifact-only branch exists so an owner-approved Pi Connect session can fetch the **exact commit URL** and install the signed candidate without a full-card flash. The normal Luma Settings updater intentionally ignores feature branches and test candidates; only accepted stable `main` releases appear there. Do not merge this binary branch into `main` or use it as a v1 release. Real-Pi visual smoothness, service restart and settings persistence still require owner-led testing.
