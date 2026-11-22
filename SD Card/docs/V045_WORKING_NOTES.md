# Luma 0.4.5 working notes

The owner requested remote access without a Bluetooth connection and publication through the normal signed GitHub update flow.

## Authority

Enrollment retains its live registered-phone and local PIN approval checks. Requests from an already approved browser use the current persisted grant, registered profile, phone binding, private HTTPS origin and Tailscale identity. A deterministic digest of that grant binds request challenges, slow-operation checks and primary PIN leases. A Bluetooth session changing has no effect on that remote authority.

The stored grant format is preserved for existing enrollments and rollback. Grant revocation, profile removal, remote policy changes and phone registration changes retain their existing invalidation behavior. Each proof remains single-use and request-bound.

## Private views

Remote previews use the authenticated profile’s calendar projection. The remote path explicitly permits an absent phone. Default projections and all wall projections still require live presence. The connected-users list and the preview’s phone-connected value continue reflecting actual Bluetooth presence.

Task completion through a signed remote checks its grant before provider calls, after awaited operations and before saving. Local wall task operations keep their presence checks. A remote can finish Google consent while away, while grant revocation still prevents credential commits.

## Verification

Check primary and secondary remote reads, calendar preferences, timers and task writes with all phones disconnected. Check primary PIN access, secondary restrictions, retained enrollment after restart, replay rejection, revocation during slow work, and Google consent while away. Run the signed browser fixture through disconnect, reload, primary Settings, background/offline clearing and revocation. Verify that the wall redacts private information on disconnect.

Run the repository’s required software checks and GitHub CI before publishing. Qualify the exact signed archive against the published 0.4.4 installer and its rollback path. Physical Tailscale access from the owner’s iPhone remains an owner acceptance check.
