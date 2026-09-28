# Luma Smart Hub

A Raspberry Pi 4 wall-mounted smart display with a large-format themed UI,
local voice commands, Google Calendar/weather integrations, optional phone
presence and room-device controls.

## Project files

- [`SD Card/README.md`](SD%20Card/README.md) — application and appliance overview.
- [`SD Card/docs/FLASHING.md`](SD%20Card/docs/FLASHING.md) — owner-controlled SD
  imaging instructions. Hardware flashing/testing remains explicitly gated by
  the owner.
- [`SD Card/docs/UPDATE_DEPLOYMENT.md`](SD%20Card/docs/UPDATE_DEPLOYMENT.md) —
  signed, rollback-capable in-place software update procedure and key boundary.
- [`.github/workflows/luma-ci.yml`](.github/workflows/luma-ci.yml) — backend,
  frontend, and image-manifest CI checks; no signing key is provided to CI.

The application source and CI workflow are being developed on the
[`codex/luma-updater-ci-20260928`](https://github.com/BrianBGoldshtein/LumaSmartHub/tree/codex/luma-updater-ci-20260928)
feature branch. Hardware acceptance still requires the actual assembled Pi,
display, audio board, phone, and configured accounts.
