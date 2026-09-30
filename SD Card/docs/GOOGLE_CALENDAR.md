# Google Calendar connection and colors

Use the Google Calendar API directly, initially with read-only access. An explicit optional event-edit permission enables color-based task completion on the hub; see [calendar-backed to-dos](TODO_CALENDAR.md). The dashboard does not require a public calendar or an embedded Google webpage. The API client, OAuth endpoints, calendar selector, and five-minute sync worker are implemented in source. A real Google account has not yet been connected or tested on the target Pi.

## One-time setup on the Pi

1. In Google Cloud Console, create a project and enable Google Calendar API. Configure OAuth consent for your own account. Create an OAuth client with application type **Desktop app** and download its client JSON.
2. Open Luma on the Pi at `http://127.0.0.1:8742`, open the bottom-left controls, and choose **Google Calendar**.
3. Select the client JSON, then choose **Sign in with Google**. For a USB drive, insert it into a Pi USB-A port before opening the chooser; wait a few seconds and choose the drive from the picker's removable-media list. The image must include both `udisks2` and GVFS's desktop volume-monitor (`gvfs-backends`/`gvfs-daemons`) for GTK/Chromium to show removable volumes. Complete sign-in and the read-only consent in Chromium. The loopback callback is `http://127.0.0.1:8742/api/v1/google/callback`.
4. Under **Agenda calendars**, select all calendars to display, and optionally a separate to-do calendar. Under **Sleep schedule**, choose your sleep calendar and use daily timed events titled **Sleep** (the new-install default). Each event's start begins night mode and its end starts the five-minute wake; overnight and Google-expanded recurring occurrences work. Leaving all sleep calendars unchecked disables automatic calendar sleep; it no longer falls back to agenda calendars. A sleep-only calendar need not appear on the agenda. Existing saved custom titles are preserved, including the former `Sleep Time` default: change the field to `Sleep` if needed. Press **Save calendars**.
5. Return to Dashboard. Private events appear only while the privacy key or fallback PIN has unlocked the display. Google sign-in does not itself unlock the privacy screen.

Sleep matching ignores capitalization and surrounding whitespace, but otherwise matches the whole title. All-day, cancelled and declined occurrences do not control sleep. Overlapping/touching sleep intervals stay asleep until the combined end. Night & wake preferences choose either the dim clock or full screen-off; manual Good night, Good morning and temporary wake remain available. Sleep selection and title persist across restarts.

**Leave soon** has its own calendar selection in Extras and automatically uses eligible events on those calendars. **Important Dates** remains a list of manually saved dates or individually linked Google events; it is not populated from an entire calendar.

For to-dos, select a completed event color and save calendars. **Enable task updates with Google** requests additional `calendar.events` permission only when explicitly chosen locally. Google grants a broader event-edit scope; Luma limits its task writer to color changes on the selected to-do calendar's current all-day tasks. The calendar must also be writable. Manual Google recolors work with the existing read-only connection. See [task setup and rules](TODO_CALENDAR.md).

The initial setup must run in the Pi's own browser: `127.0.0.1` refers to the device running the browser. The preview at port 4173 uses sample calendars and cannot connect a real account. Keep the client JSON private. Luma stores the refresh token locally in SQLite; it never stores your Google password. Normal power cycles should not require sign-in again, but Google can revoke or expire a token. For a personal long-lived installation, check the consent application's publishing status; external apps left in Testing generally have seven-day refresh tokens for Calendar scopes.

## Sign-in reliability

If Google shows **“Access blocked: Luma Smart Hub has not completed the Google verification process”** with **403 access_denied** and says the app is being tested, this is a Google Cloud consent-screen audience setting, not a Pi or USB failure. On another device, open [Google Auth Platform → Audience](https://console.cloud.google.com/auth/audience) in the **same Cloud project that created the imported Desktop OAuth JSON**. While the app is in Testing, add the exact Google account selected on the Pi under **Test users** and save. Close the failed browser page, return to Luma's Calendar setup, and start sign-in again with that account. Do not send the client JSON, account password, or authorization code to support. If the account was already listed, confirm both the selected Cloud project and account before changing the Pi image. Google's [audience guidance](https://support.google.com/cloud/answer/15549945) explains the Testing restriction and seven-day authorizations for Calendar scopes.

Luma explicitly uses Google's S256 PKCE flow: the authorization request carries a challenge, while its secret verifier stays in a single private database record with the random state, issue time and client-configuration fingerprint. This record can survive an application restart during the 15-minute setup window. The local callback checks its exact loopback destination, state, code and age before claiming the attempt atomically. Concurrent/replayed callbacks cannot exchange it twice. The verifier is never returned to the setup page, included in URLs or logged by Luma.

If sign-in times out, is interrupted during the token exchange, or the client configuration changes, return to Calendar setup and start sign-in again. Established saved credentials are not cleared by a failed attempt. A successful replacement must include a refresh token for offline access. The token exchange uses HTTPS with a bounded timeout; no HTTPS verification or OAuth transport checks are disabled. A legacy unfinished sign-in from older builds must be restarted; already-saved account tokens remain compatible.

Cancelled/failed callbacks return to the themed Calendar setup with a fixed recovery notice, not a raw error page. **Reconnect Google** remains available for a revoked or failed connection; the browser preview only simulates that button. Callback redirects use no-store/no-referrer headers, and the main API disables request-URL access logs so short-lived callback codes/state are not copied into routine access logs. Provider errors/codes are not echoed into the recovery URL or notice.

Regression tests use the actual installed Google OAuth SDK and replace only its HTTP transport with synthetic replies. They verify the outgoing verifier matches the original challenge after recreating the client, refresh-token persistence, callback completion, single use, malformed/expired attempts, and failure retention. They do not authorize a real account or prove Google's consent-screen/Chromium behavior on the Pi. See [Google's desktop-app PKCE guidance](https://developers.google.com/identity/protocols/oauth2/native-app#step1-code-verifier).

## Color rules

- Read each calendar's personal name (`summaryOverride` when present) and `backgroundColor` from CalendarList. A custom RGB color takes priority over its palette ID.
- Read Google's separate calendar/event palettes using `colors.get`.
- If an event has `colorId`, resolve it through the **event** palette. Otherwise inherit the calendar color.
- Show the original color in the event's vertical stripe and a subdued version behind its large title. Themes never substitute their accent for a known Google color.
- Show the calendar name alongside an optional location, so color is not the only identifying cue.
- Cache names and colors with events for offline use. Privacy mode removes entire event records, including names and colors, from the frontend snapshot.

Calendar and event pagination are supported. The `primary` alias resolves to the primary CalendarList entry. Cancelled events are skipped. Sync covers one day back through seven days ahead and refreshes every five minutes; failed sync retains the previous cache. Calendar selection can also trigger an immediate sync.

References: [CalendarList](https://developers.google.com/workspace/calendar/api/v3/reference/calendarList), [Colors](https://developers.google.com/workspace/calendar/api/v3/reference/colors/get), [Events](https://developers.google.com/workspace/calendar/api/v3/reference/events), [OAuth installed apps](https://developers.google.com/identity/protocols/oauth2/native-app), [Token expiration](https://developers.google.com/identity/protocols/oauth2#expiration).
