# Luma 0.3.10 Beta

Fixes an expensive Bluetooth observation path introduced in 0.3.9: unrelated nearby-device updates no longer repeatedly open the profile database or delay Luma's event loop. Registered-phone wake hints use a bounded in-memory dispatch map; actual privacy authorization still reads current verified evidence. No secondary phone notifications are read.

Retains standby USB power for the fan/mouse, saved automatic cooling at 70°C on / 60°C off when a phone is present, incoming-phone recognition improvements, and all existing settings/accounts/saves. No reflash or re-pairing is needed. The existing health gate remains mandatory; a bounded startup stack diagnostic helps investigate any remaining real-Pi stall.

## Installation

The owner's 0.3.9 attempt rolled back to 0.3.8. Install **0.3.10**, not 0.3.9, through Settings → Luma software or the existing signed Pi Connect terminal procedure. Keep power connected through installation and the verified reboot. Confirm **0.3.10** afterward; an accepted download or reboot alone does not prove installation succeeded.

Verify actual fan/mouse power with all registered phones absent, the saved Automatic preference after a phone returns, and real iPhone recognition timing. Linux source, private-bus and install/rollback tests do not prove physical switching or iOS negotiation. If installation rolls back, retain the card and collect the updater/API failure logs; do not repeatedly retry or erase settings.
