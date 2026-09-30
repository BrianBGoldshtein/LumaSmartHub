# Room device integration

Luma's optional room-device integration supports a selected Levoit Core 300S/300S-P purifier through VeSync. Connecting an account never enables a scene or remote control by itself. The purifier must be enrolled in the vendor app on a permitted network before Luma can discover it. The exact returned model and available capabilities determine what controls appear; do not assume another Levoit model is interchangeable.

The pinned `pyvesync` adapter uses bounded network calls, conservative polling and backoff. Credentials are used for enrollment and are not exported in portable backups. Persisted sessions are preferred over repeatedly entering a password. A command can be accepted without an immediate state change; Luma performs a separate readback and distinguishes confirmed, unconfirmed, rejected, unavailable and not-sent outcomes. Busy work is not queued for later replay.

Fresh supported capabilities may include power, speed, mode and purifier display. Manual control pauses the device's scene changes for one hour. Scenes are empty and disabled until the owner chooses actions and separately enables triggers. The exact action binding is rechecked before dispatch; relinking the purifier invalidates prior scene/remote review. See [SCENES.md](SCENES.md).

The optional 2.4 GHz hotspot for purifier onboarding is documented in [CAMPUS_NETWORK.md](CAMPUS_NETWORK.md). It requires campus permission and a compatible second Wi-Fi radio; software support does not establish Stanford policy approval or real-device success.

Synthetic tests cover persistence, stale capabilities, API authentication, command outcomes, no-retry behavior and scene binding. Still required: all-theme touch/error/reconnect checks, actual Pi networking, vendor-account enrollment, supported-model confirmation, command readback, outage recovery and power-loss persistence. Do not infer hardware acceptance from the source tests.
