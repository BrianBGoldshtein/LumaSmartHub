# Flashing Luma

## Before writing

A checked software candidate is delivered in the user-visible output folder at `image/r11-candidate-74d1f71-20260929/luma-pi4-UNVERIFIED.img.xz`, with its checksum, manifests and validation receipts. Read the [r11 candidate handoff](R11_HANDOFF.md) first. It includes the room-device setup and recovery fixes added after r10. Other image folders are preserved older builds. None is a production release. These are instructions for an owner-directed hardware test, not an instruction to flash now.

A candidate named `luma-pi4-UNVERIFIED.img.xz` may be handed off for **controlled physical testing** after its software/image checks pass. That testing is how the remaining [hardware acceptance gates](HARDWARE_VALIDATION.md) are evaluated. It is not yet qualified for unattended wall-mounted use. The release name `luma-pi4.img.xz` is reserved for the later qualified delivery.

Writing an image erases the entire selected card, including any existing Luma settings/accounts. Back up any needed data first. Confirm the physical card, capacity and selected device; stop if identification is uncertain. Leave system-drive exclusion enabled. No card has been written by the build process.

If this is the already-personalized Pi card, **stop before writing** until there
is either a verified copy of the old card or explicit agreement to set up
Google, Tailscale and other accounts again. The new image does not silently
import the old card's private database or tokens. Raspberry Pi's
[official backup guide](https://magazine.raspberrypi.com/articles/back-up-raspberry-pi)
describes making a whole-card image on Windows with Win32 Disk Imager's
**Read** action; allow storage for the full card capacity and verify the
output before overwriting the card. Such a clone is a rollback copy, **not**
an automatic migration into the new Luma version. Treat it as sensitive:
it contains saved credentials and personal information; never upload it to
GitHub or sync it casually. Microsoft's
[WSL disk-mount documentation](https://learn.microsoft.com/en-us/windows/wsl/wsl2-mount-disk)
explicitly says `wsl --mount` does not support USB flash drives/SD readers, so
that is not a backup shortcut here. A migration, if desired, needs a separate
verified extraction/import procedure before this becomes the final flash.

## Write the handed-off image

1. Install Raspberry Pi Imager on a desktop computer and select Raspberry Pi 4.
2. Insert the intended SanDisk High Endurance microSD card.
3. Choose **Use Custom** and select the exact handed-off `.img.xz` archive after comparing its SHA256 with the supplied checksum.
4. Select the confirmed microSD card. If OS customisation is offered, choose **Skip customisation** for this appliance: Luma already supplies its service user and approved key-only SSH policy. Do not inject a replacement user/password, Wi-Fi profile or remote-access setup. Campus Wi-Fi is configured through Luma after boot.
5. Review the target again, approve erase/write, and allow Imager to finish verification. Safely eject the card.
6. With the Pi powered off, fit the card and ReSpeaker HAT, then connect the display, touch USB, speaker, and Ethernet if available. Do not fit/remove the HAT while powered.
7. Apply power. The first boot may take several minutes while the filesystem grows and services settle. For an UNVERIFIED candidate, follow the hardware acceptance checklist with synthetic data before adding personal accounts.

Imager's custom-image selection, storage precautions and write/verification flow are documented in the [official Raspberry Pi setup guide](https://www.raspberrypi.com/documentation/computers/getting-started.html#install-using-imager). Skipping customisation above is specific to this preconfigured Luma appliance.

Do not copy the `SD Card` folder onto a blank FAT-formatted card. The `.img.xz` file contains the partition table, boot firmware, operating system, and application.

The image contains no personal account credentials. Luma provides device settings for location, PIN, Google Calendar, preferred calendars, audio route and the paired iPhone address. The r11 candidate includes the Wi-Fi picker with a pinned Stanford SUNet eduroam profile, captive-portal launcher/status notice, touch Bluetooth matching-code pairing, and the optional PIN-protected Levoit AP. Do not enable campus internet sharing without explicit approval from the responsible network owner. The candidate remains unverified on physical hardware; Tailscale enrollment/certificates and campus behavior remain pending. Follow [campus network requirements](CAMPUS_NETWORK.md), [first-boot instructions](FIRST_BOOT.md), [private commands](TAILSCALE.md) and [iPhone pairing instructions](IPHONE_AND_SIRI.md).
