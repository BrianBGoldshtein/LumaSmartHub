# Luma 0.3.12 Beta

## Recover USB cooling from the primary phone

The physical-test button no longer deadlocks after a latched switching fault. With a registered phone connected, unlock primary Settings → Device → USB cooling → Verify physical fan switching. Remove USB drives, leave the fan's switch on, acknowledge the interruption and choose **Retry physical fan test**. USB power is restored by the independent controller after five seconds. Confirm only if you actually saw the fan stop and restart; only then enable Automatic cooling. A fresh acknowledgment is required after a failed attempt. Keep USB on remains available.

The low-level switch now waits one bounded 150 ms for USB3 status to settle, following the upstream uhubctl approach, before checking both onboard hub views. It does not repeatedly issue off requests. Persistent errors still latch a fault, attempt power-on restoration and disable automatic control. Fixed diagnostic codes preserve the first fault without exposing raw device paths. Duplicate tests cannot extend the five-second interruption; stale polls cannot overwrite newer control responses.

The owner's readings showed all eight reported hub bits on, no USB storage and no active update. These do not identify the original failure-time cause, prove fan RPM or prove physical voltage switching. Delayed readback is a reproduced software failure mode, not a confirmed diagnosis of that historical Pi event.

## Install without erasing settings

Use Settings → Luma software → Check for updates → review **0.3.12 Beta** → Install. Keep power connected through reboot, then confirm version **0.3.12**. The existing signed Pi Connect update procedure also supports target `0.3.12`. No reflash, Google reset or Bluetooth re-pairing is required. Keep USB power on until you are present for the physical test above; a software simulation cannot replace that observation.

70°C on / 60°C off, the minimum-on interval, standby mouse power, storage/update guards, primary PIN protection, secondary restrictions and crowded pairing-list fixes remain unchanged. No discovery-window cycling, firmware update, new root operation or permissions expansion is introduced.
