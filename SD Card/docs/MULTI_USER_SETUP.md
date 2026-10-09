# Multi-user setup — Luma 0.3.1

Use these steps after installing the verified 0.3.1 Beta. One primary and up to four secondary users have separate accounts and timers. Do not reflash, unpair a working primary phone or share its Google/Tailscale login to add someone.

## Primary: add a person

1. Open **Settings → Users** and unlock with the primary hub PIN.
2. Under **Add someone**, enter a unique nickname, then tap **Approve & begin guided setup**. The name identifies their roster, calendar panel and arrival screen; it does not authenticate them.
3. Hand the wall screen to that person. They can complete their approved personal setup without your phone remaining connected. Global settings, user management and updates remain primary-only.

The hub supports five profiles total. **Open personal setup** resumes an existing person's flow. **Rename** changes their display name, not their phone or credentials. **Change phone…** clears that person's registration and access grants, retaining Google choices; it does not erase a Bluetooth bond. **Remove user…** deletes their Luma credentials/cache/timer/grants, never their Google calendar events. Review these confirmations carefully.

## Secondary: finish your own setup

1. **Your iPhone:** pair your own phone and compare the six-digit pairing code on both devices. Enable **Share System Notifications** on the iPhone's Luma Bluetooth entry. Pairing alone is not enough: wait for authorized notification services.
2. **Phone remote:** optional. Enroll your own Safari or Home Screen window using the private link and matching browser code. Use your own Tailscale identity; never sign in as the primary. You may skip the remote and continue all remaining steps on the hub.
3. **Your Google:** optional. Sign in to your own account using the configured Google consent flow. The primary configures the application's OAuth client; do not upload private client JSON to GitHub. Enable task updates only if you want Luma to recolor your selected task calendar.
4. **Your calendars:** select every agenda calendar you want. Choose your all-day task calendar and its completed color, then save. Only that chosen completed color marks tasks done. Your account cannot change the room's primary Sleep calendar.
5. **Ready:** explicitly choose whether your calendar/tasks may appear on the shared wall while your authorized iPhone is connected. Others in the room may see shared details. Turning sharing off retains your own remote preview and timer.

Progress and settings save on the Pi. After a disconnect, reconnect your registered authorized phone and resume. You do not need the primary PIN for personal calendars or timers. If first approval expired before pairing, ask the primary to reopen your personal setup. The primary PIN is never needed to enroll a secondary browser.

On your enrolled phone, **My calendars** resumes the saved private-link → Google → calendars → ready guide. Google can be skipped; your timer still works. Safari and a Home Screen window enroll separately. Hidden/offline/disconnected windows clear private content and stop polling.

## Optional secondary phone access, or primary-only fallback

Secondary remotes require private Tailscale transport to the Luma node using each person's own identity, plus their own enrolled browser key and live authorized phone connection. Tailscale reachability alone never unlocks data. Keep HTTPS enabled and public Funnel disabled.

To give a secondary user private transport without adding them to your whole tailnet:

1. In the primary's Tailscale admin console, open **Machines → Luma → Share** and create a single-use invitation for that person. Keep the link private.
2. Have them accept using their own Tailscale account, sign their iPhone into that account and enable Tailscale. Share only Luma, not your laptop or recovery credentials.
3. Review the tailnet access rules: allow that recipient only Luma's HTTPS port **443**, preserving your own maintenance access. Rules are additive; an existing wildcard allow can also grant access and must be reviewed. Do not replace the entire policy with a sample or expose SSH just to enable the web remote.
4. With their authorized Bluetooth link active, resume their Luma setup and enroll the Safari/Home Screen window. Use the full private `https://…ts.net` address from Luma, not `luma.local`.

[Tailscale device-sharing instructions](https://tailscale.com/docs/features/sharing) describe invitations, private DNS and access rules. [Serve identity headers](https://tailscale.com/docs/features/tailscale-serve#identity-headers) also cover individually shared users; Luma still requires its own approved browser and live phone authorization.

If that transport is impractical, the primary opens **Settings → iPhone remote → Who can use an iPhone remote? → Use primary-only remote**, enters the required PIN and confirms revocation. Secondary calendars, local guided setup, Bluetooth presence and timers stay available. Already enrolled secondary browsers are revoked and pending consent/enrollment is canceled. **Allow secondary remotes** permits new enrollment; it never revives an old revoked grant.

The primary remote may unlock primary settings using the hub PIN. This permission is deliberately absent from secondary remotes. Do not share that PIN or the primary browser's enrollment.

## Everyday use and testing

Tap your connected nickname on the wall to open your personal timer. The generic Timer control and anonymous voice timers are shared room timers. Timers do not require primary permission. Task buttons need fresh Google write consent and a personal wall approval; they update only that account's chosen task calendar.

All authorized present users appear in the corner, even if they skipped Google. Calendar/task panels appear only for configured consenting users; if nobody present has private information, public standby still runs. Leaving immediately hides that person's private data. The primary Sleep schedule still controls the room when they leave.

For acceptance, start with two real phones/accounts. Check independent pairing, range return, privacy, task edits and timers; then expand to five concurrent authorized phones and reboot recovery. Synthetic build-host tests are not proof of real radio or Safari behavior. Keep working bonds intact and report exact connection/version messages when something fails.
