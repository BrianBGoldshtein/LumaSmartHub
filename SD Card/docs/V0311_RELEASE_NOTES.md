# Luma 0.3.11 Beta

## Find your phone in a crowded scan

The pairing list no longer silently drops devices after row 40. Readable names are prioritized, then stronger measured Bluetooth signals within named/anonymous groups. A readable remote name is used when the alias is just an identifier. Missing signal readings do not masquerade as strong signals.

Primary and secondary setup share one themed picker: name/address search, six results per page, full counts, signal labels and explicit page controls. Anonymous devices remain accessible. Secondary setup retains its existing exclusion of phones already registered to someone else; that check now reads the registry once instead of once per discovered device.

Device names and signal strength are only hints. Selection still requires the exact discovered device, rechecked identity and matching-code confirmation before a new bond is trusted or saved. No automatic pairing, widened privacy permission or secondary notification access is introduced. Keep iPhone Settings → Bluetooth open nearby while scanning. The existing bounded discovery timeout remains; this update cannot make an undiscoverable phone advertise.

## Install

Use Settings → Luma software → Check for updates → review **0.3.11 Beta** → Install, or the existing signed Pi Connect procedure with target `0.3.11`. Keep power connected through reboot, then confirm version **0.3.11**. Do not retry 0.3.9. No reflash, account reset or phone-bond deletion is required. Standby USB power, saved 70°C on / 60°C off cooling, twenty-second cursor hiding and 0.3.10 Bluetooth-load correction are retained.

After installation, scan with the phone's Bluetooth settings open. Check the named/strong-signal ordering, search by phone name or address, and page to other results. Real RF discovery and physical Pi behavior remain owner acceptance, separate from software/browser qualification.
