# Luma 0.3.6 Beta

Automatic USB cooling now turns the fan on at 70°C and off at 60°C or lower, after at least sixty powered seconds. Between those temperatures it retains its previous state. Periodic sixty-second USB discovery windows are removed: normal quiet operation no longer starts the fan just to scan for a drive.

## USB access

All four onboard USB ports still switch together. While power is off, neither the mouse nor newly plugged USB devices will work. Before using the mouse or connecting a USB stick, open your enrolled primary phone remote → Settings → unlock → All hub settings → USB cooling → **Keep USB on · mouse & drives**. Leave power on during USB use; afterward select **Automatic cooling** again.

The cooling panel shows the selected mode separately from actual USB power. Automatic can legitimately show power on while cooling or during a safety override; that does not mean your saved preference was reset.

## Retained safeguards

Detected USB storage, backup work and software updates keep power on. Missing/invalid temperature, an expired controller heartbeat and normal controller shutdown restore power. Switching faults disable automatic operation and attempt restoration. The five-second test and saved physical-switch qualification remain in place. Hardware or kernel failure cannot guarantee restoration.

This application-only update preserves the existing SD card, settings, accounts, user profiles, phone bonds and game saves. No new package, firmware, schema migration or OS image is required. Physical fan switching was reported working by the owner on 0.3.5; the revised 70/60 cycle still needs an on-device check after installation. Keep the fan continuously powered if a fault appears.

## Installation and checks

After the signed release is published, use Settings → Luma software → Check for updates → review 0.3.6 → Install. Keep Pi power connected through the successful-update reboot and verify version 0.3.6.

With no USB drive attached, choose Automatic and check that the fan stays off beyond one minute while the CPU is below 70°C. Do not artificially heat the Pi: observe ordinary use until it reaches 70°C, then confirm cooling continues until 60°C or below. Check the phone's Keep USB on override before connecting a drive, and confirm saved settings, voice, phone presence and dashboard still work.
