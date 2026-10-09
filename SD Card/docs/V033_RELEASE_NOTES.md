# Beta — Luma 0.3.3

Luma 0.3.3 adds a themed Raspberry Pi CPU temperature readout in wall Settings and the iPhone remote’s Hub page. It uses the built-in sensor; no external probe is needed and it does not measure room temperature.

## Temperature readout

The wall refreshes every ten seconds while Settings is visible. Authorized primary and secondary remotes receive a fresh reading with their existing five-second preview refresh. Values use Celsius to one decimal place. Luma shows Normal below 70°C, Warm from 70°C and High from 80°C. The 70°C warning is Luma’s early-warning policy, not a throttling measurement. Pi documentation describes thermal throttling between 80°C and 85°C; this readout does not claim that throttling is currently active. See [Raspberry Pi temperature documentation](https://www.raspberrypi.com/documentation/computers/config_txt.html).

A missing, unreadable or malformed sensor displays Sensor unavailable, never zero. A reading older than thirty seconds also becomes unavailable. Demo Settings labels its synthetic reading Example. The fixed sensor path is read without root commands or caller-selected filenames. Remote enrollment and authorized-phone checks remain unchanged; secondary users gain no room-settings or updater permissions.

## Installation and owner check

Once the signed Beta is published, use Settings → Luma software → Check for updates → review 0.3.3 → Install. A primary iPhone remote can also install through Software. Keep power connected through the progress screen and graceful reboot. Accounts, settings, phone bonds, timers and saved games stay on the existing card; no flash is required.

After installation, confirm version 0.3.3 and compare the wall and remote CPU readings. Small differences are expected because they sample at different times. On the Pi, `cat /sys/class/thermal/thermal_zone0/temp` returns millidegrees Celsius; divide by 1,000 for comparison. Actual sensor permission, screen rendering and Safari behavior require this owner check. No fan control or game changes are included.
