# Luma 0.4.5 Beta

An enrolled Luma remote now works over its private Tailscale connection even when the registered iPhone is away from the hub or Bluetooth is turned off.

- Primary and secondary users can see their own calendars and to-dos, update tasks, and use personal timers while away.
- The primary user can unlock Settings with their PIN and manage the hub remotely, including installing updates.
- Google sign-in from an enrolled remote can finish without staying near Luma.
- The Connected now list continues showing which registered phones are physically connected to the hub.

Your existing approved browser enrollment continues working after the update. Keep Tailscale connected on the phone and open the same private Luma URL. Connect the registered phone to Luma when enrolling a new browser.

The wall continues using Bluetooth presence and each user’s sharing choices to display private information. Remote access checks the saved browser key, Tailscale identity, selected profile and current remote permissions. Revoking the browser, changing its phone registration, removing the profile or disabling its remote access blocks further requests. Primary PIN checks still apply to hub administration.

Install through the primary remote’s **Software → Check for updates**, review **0.4.5** and choose **Install**. On the wall, use **Settings → System & updates → Software updates**. Keep the Pi powered through the automatic reboot.

After installation, turn iPhone Bluetooth off, keep Tailscale connected and reopen the remote. Check your calendar and a timer. Confirm that the wall enters privacy standby. Reenable Bluetooth afterward to check that the wall returns to showing the connected user’s information.
