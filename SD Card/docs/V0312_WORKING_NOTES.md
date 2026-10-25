# 0.3.12 — recover latched USB fan faults from the phone

## Owner evidence and task

Phone pairing is now working. Owner sees USB power on, Keep USB on, Switching failed / automatic disabled, and cannot use physical-test verification buttons on the phone remote. Owner recalls no flicker and requests autonomous diagnosis, simulations and a published fix while they sleep; no further live commands should be requested tonight.

Actual read-only Pi report: onboard USB2 bus 1/device 2 and USB3 bus 2/device 1 all four PORT_POWER bits true; USB storage absent and update inactive. This proves current reported hub power is on, not fan RPM/physical voltage, and excludes those two guards at that instant. No failure-time journal or transfer error is available, so the original hardware trigger is not conclusively known.

## Proven code defects and corrections

The backend latches a fault and only reinitializes on an explicit acknowledged probe. The shared frontend simultaneously disables that probe whenever available=false: a permanent recovery deadlock on both wall and phone. Enable acknowledged retry with a valid status and verified phone even while faulted; retain standby, busy, confirmation, admin and hardware guards. Never enable automatic cooling merely because power currently reads on.

The raw Linux switch writes both onboard hub views then immediately demands matching status. The upstream [uhubctl implementation](https://github.com/mvp/uhubctl/blob/master/uhubctl.c) allows a 150 ms USB3 settling delay before readback. Add one bounded 150 ms settling wait after successful writes, without repeated off requests, automatic off retries or changed ioctl authority. Simulate delayed readback to show why the old implementation could falsely latch a healthy switch. This is a plausible trigger, not proof of the owner's exact historical fault.

Keep-on restoration currently runs outside the controller's fault-handling path; failures can become generic backup errors. Route restoration failures through the existing fail-on path and expose only fixed fault codes (no raw paths/exception text), preserving first cause until successful deliberate reinitialization. Persistent mismatch/I/O failure must still keep USB on best-effort and disable automatic control.

## Required verification and continuation

Add delayed/mixed/permanent hub-readback simulations, all-port restoration failures, safe recovery after a latched fault, no off before acknowledgment/phone/guard checks, explicit physical confirmation before automatic mode, and frontend failed-state button tests. Exercise the real signed primary remote with a fake root power controller in all themes, including checkbox → probe → independent restoration → confirmation → automatic. Test secondary refusal, disconnect cancellation, storage/update guard and failures; no real USB switching should occur in tests.

Then full software/build/CI gates, exact offline-signed install/rollback using published 0.3.8 and 0.3.11 installers, and production download equality before publishing a new v0.3.12 Beta. Preserve all saved settings/bonds, 70°C on / 60°C off, no discovery windows, standby power, pairing-list fixes and the root five-field wire contract. Do not weaken the physical-observation gate or claim a real Pi fan has been tested. Private key stays offline. Source edits are in the LumaSmartHub-0.2.4 repository, not the stale root SD Card folder.
