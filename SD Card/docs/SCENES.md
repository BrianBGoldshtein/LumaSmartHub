# Room scenes

Morning, Night, Arrive and Away start empty and disabled. The owner selects supported actions from the connected purifier, reviews their current binding, enables each scene, then separately opts in to an automatic trigger. The scene editor is local-owner-only. Pairing or account enrollment does not create an automation.

Night and Morning use fresh, selected Google `Sleep` calendar boundaries. Arrive requires a fresh authenticated nearby-phone connection held for 30 seconds; Away requires three minutes of confirmed disconnection. Startup, uncertain radio state, PIN unlock, token refresh and Tailscale alone do not count as arrival or departure. A verified clock, five-minute scene cooldown, per-device manual override and pre-dispatch capability/binding recheck protect automatic runs. Claims are journaled before I/O, and interrupted runs are not replayed after restart.

Manual scene run/cancel are available locally and through fixed Hey Luma phrases when authorized. Private iPhone Shortcuts can run only separately allowlisted, already-enabled scenes. That grant fingerprints the exact ordered actions and device bindings; editing, reordering, disabling or relinking invalidates it until local re-review. The restricted gateway returns only a generic acknowledgement and does not reveal private calendar or presence state.

Scene result statuses distinguish confirmed, unconfirmed, unavailable, rejected, not-sent, cancelled and overridden actions. Purifier speed or mode can turn power on; do not combine either with an Off action in one scene. Empty scenes cannot be enabled. Real-device, phone-presence, Google-sync and touch testing are still required before physical acceptance.
