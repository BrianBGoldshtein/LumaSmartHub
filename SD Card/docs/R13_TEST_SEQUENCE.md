# r13 focused owner test sequence

The r13 image is a **new OS flash**, not an app-only update. It erases the
current card's settings, phone bonds and account enrollments. Keep r12
available until r13 boots and these checks pass. Do not call r13 v1 yet.

1. After the flash, connect the HDMI display, USB touch lead, ReSpeaker V1 HAT,
   Pi power and Wi-Fi. Confirm touch and network work. Set Toyon weather to
   latitude `37.426`, longitude `-122.164`; a positive longitude is wrong for
   Stanford. Confirm current and next-four-hour forecast looks plausible.
2. Open **Device setup → Connections → Raspberry Pi Connect**. Tap **Start Pi
   Connect sign-in**. A QR/link must appear. Scan it, approve the Pi, refresh
   until **Pi linked · shell off**, then tap **Enable admin remote shell** and
   connect from the Connect website. Reboot, then confirm the shell still
   works. Report the exact stage/error if any step fails; do not send the QR.
3. Insert the Samsung USB stick. In the native file chooser, open the stick
   and locate the Google Desktop OAuth JSON. Do not share its contents. The
   r12 “polkit authority not available” error must be gone. The backup drive
   list and actual encrypted backup remain separate tests.
4. Open **Hey Luma → ReSpeaker capture**. It should report the V1 card and
   input path, with a live gain value. Start at the published V1 default of
   `39`. Tap **Check my voice** and speak normally from the intended room
   distance. The meter must move and all three phrases should pass. If it is
   quiet, try gain `43`, save and repeat; avoid clipping. If it says the HAT
   is missing, stop adjusting gain and report that text. If the card is
   detected but the meter stays zero, report both statuses; remote shell can
   then test the physical source versus the virtual `luma_mic` without another
   blind image change.
5. Let Pong play and confirm the small ball-speed lift looks natural; an old
   checkpoint should keep its score if restored through a supported path.

The ordered [full hardware checklist](HARDWARE_VALIDATION.md) still applies,
including Bluetooth, audio alarm, OAuth, backup restore, power loss and signed
updater rollback. These five checks are the immediate r12-regression gates.
