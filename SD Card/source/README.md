# Luma source

The source tree is divided by runtime boundary:

- `backend/`: local API, state orchestration, persistence, integrations, and hardware abstractions.
- `frontend/`: kiosk dashboard and onboarding UI.
- `system/`: Raspberry Pi configuration, service units, and hardware helper scripts.
- `tests/`: read-only on-device preflight and its mocked Linux host tests; see `docs/HARDWARE_VALIDATION.md` in the delivery root. Image-level tools live in `image-builder/`.

Development must keep hardware access behind interfaces so the core behavior remains testable on non-Raspberry Pi hosts.
