# Room Wi-Fi through Luma — researched 2026-11-07

## Before buying: Stanford permission

Stanford's [residential network policy](https://thehub.stanford.edu/find-software-and-computers/computer-usage-policies) says routers, DHCP and NAT servers are generally not allowed. This exact routed hotspot needs approval from the responsible network administrator; choosing eduroam or Visitor does not grant that approval. Ask Student Technology Services whether your residence has an approved IoT/PSK network first. If so, that is the cheapest option: no extra hardware, and no continuously running Pi router. Do not buy an adapter or enable sharing until the permitted approach is clear. No administrator has been contacted and no permission has been obtained by this project.

## Recommended architecture if approved

`Approved upstream Wi-Fi → Pi built-in Wi-Fi → NetworkManager NAT/DHCP → USB AP radio → Luma-Devices → room devices`

The two radios must have different physical PHYs. Keep the built-in radio on eduroam and use a USB adapter for the 2.4 GHz WPA2 access point. Luma already includes opt-in sharing settings and rejects a second virtual interface on the same PHY. [NetworkManager shared IPv4](https://networkmanager.dev/docs/api/latest/settings-ipv4.html) supplies addressing, DNS/DHCP and NAT through the current default connection, not a bridge into campus. Internet access depends on upstream permissions, login and routing; an active hotspot alone proves none of these.

### Cheapest verified-price candidate found

[DIYgadget UWE5370 RT5370 adapter with antenna](https://www.diygadget.com/802-11b-g-n-nano-usb-wifi-adapter-dongle-with-external-antenna-for-raspberry-pi-ralink-rt5370): the listing says **$9.99, in stock**, before shipping/tax. It identifies RT5370, 2.4 GHz and 150 Mbps. This is the lowest verified listed price among the researched suitable-chipset candidates, not a guarantee of the lowest delivered price or of this seller's current inventory. Compare shipping, return terms and the exact shipped chipset before ordering.

[MediaTek's RT5370 specifications](https://www.mediatek.com/products/broadband-wifi/rt5370) document USB 2.0, 2.4 GHz and Linux AP support. The [Linux rt2800usb source](https://raw.githubusercontent.com/torvalds/linux/master/drivers/net/wireless/ralink/rt2x00/rt2800usb.c) includes USB ID 148f:5370. That makes the exact-chipset item a reasonable budget candidate, not a physically tested Luma recommendation. Require a return option and verify AP capability on the installed Pi kernel.

An Amazon alternative is [Panda PAU03](https://www.amazon.com/dp/B00762YNMG), linked by [Panda's product catalog](https://www.pandawireless.com/Products%20%7C%20Panda%20Wireless.html). Its current checkout price could not be verified; do not treat a historical price as a quote. Verify the seller's hardware revision and Linux AP support before buying. Avoid paying a premium just for Wi-Fi 6/6E: these IoT devices need a dependable 2.4 GHz link, not high headline throughput.

Do not buy by “Raspberry Pi compatible” alone. For example, [The Pi Hut's adapter](https://thepihut.com/products/usb-wifi-adapter-for-the-raspberry-pi) changed from RT5370 to MT7601U in 2022. Station/client compatibility does not establish AP capability. Luma's runtime AP check remains mandatory. CanaKit's own AP-capable adapter listing currently shows $74.95, so it is not the budget choice for this build.

## Important fan tradeoff

Luma currently controls all onboard USB ports as one power group. It cannot switch only the USB fan while keeping a USB Wi-Fi adapter powered. **0.3.13 holds USB power on whenever a USB network interface is present**, including down/idle Wi-Fi or Ethernet, and refuses/cancels interruption tests. Saved cooling preferences are retained; the network protection takes precedence. Therefore the existing USB fan runs continuously while the dongle is attached. Choose a tolerable physical low-speed setting and monitor CPU temperature. Software cannot provide independent quiet fan switching on this wiring.

**0.4.0 adds a separate option:** keep all Pi USB ports on and control an inline fan switch through BCM12. The existing fan still draws its power from USB, while Wi-Fi/mouse/drives stay connected. See [the cheap switch board, cables, wiring and guided setup](GPIO_FAN_SETUP.md). This requires the additional board and a new observed test; installing the update alone keeps the original connection. The board's normally-off startup behavior is documented there and is not hardware fail-on protection.

Before inserting the adapter, choose **Keep USB on · mouse & drives** in the primary remote. An unpowered dongle cannot enumerate, so no detector can recognize it while USB is already off. A powered USB hub is not an assumed workaround: many do not keep data/devices alive when upstream power is cut, and backfeeding is hazardous. Independent temperature-controlled fan wiring would require a separate hardware decision; do not connect a fan motor directly to a GPIO signal pin.

### Could the header power Wi-Fi instead?

The [Pi header has 5 V supply pins](https://www.raspberrypi.com/documentation/computers/raspberry-pi.html), but they are not a USB data interface. A USB Wi-Fi adapter still needs its USB data connection. Feeding it separately would require carefully isolated wiring and would not establish that the hub retains the link when its ports are disabled; do not splice 5 V onto a normal USB cable or rely on that arrangement for networking. The [Pi 4's onboard USB ports switch together](https://github.com/mvp/uhubctl#raspberry-pi-4b).

The useful alternative is to leave USB networking powered and move **fan switching** to a suitable separately controlled fan power circuit. The 5 V supply and GPIO signal serve different purposes; GPIO must not carry motor current. This is implemented as opt-in BCM12 control in 0.4.0, retaining 70°C-on/60°C-off cooling independently of Wi-Fi. [The setup guide](GPIO_FAN_SETUP.md) uses the installed V1 ReSpeaker's digital Grove connector, so the microphone stays installed. No physical board or wiring has been tested by the software qualification.

## Setup without erasing the card

1. Obtain network-owner approval, or use the approved campus IoT network instead.
2. Install 0.3.13 or newer through Luma's signed GitHub updater. Confirm the running version after reboot and refresh the phone remote. No SD reflash is needed.
3. From the primary remote, unlock All hub settings → Device → Fan cooling (called USB cooling before 0.4.0) and select Keep USB on in the original connection mode. GPIO mode already keeps the hub on. Insert the USB adapter. The built-in radio should remain on the existing upstream Wi-Fi.
4. A stock existing image explicitly installed Realtek firmware, not all MediaTek firmware. In Pi Connect's shell, install the official Debian packages once if missing:

   ```sh
   sudo apt-get update
   sudo apt-get install firmware-mediatek dnsmasq-base iw usbutils
   ```

   [Debian Trixie's firmware-mediatek file list](https://packages.debian.org/trixie/all/firmware-mediatek/filelist) contains `rt2870.bin`, used by the rt2800usb family. This is a one-time OS prerequisite, not something the signed application updater silently installs. Do not install arbitrary vendor scripts or DKMS packages. If your configured signed repositories do not provide it, report that before modifying repository/security settings. Reinsert only the new dongle after installation if firmware was missing; keep the existing upstream radio connected.
5. Read-only checks, if needed:

   ```sh
   lsusb
   iw dev
   iw list
   nmcli device status
   nmcli -f GENERAL.DEVICE,WIFI-PROPERTIES.AP device show
   ```

   Expect a second physical radio, its driver loaded and AP support reported for the USB interface. Do not rely on interface names such as wlan1 being universal. If no second AP-capable PHY appears, stop; return/replace the adapter rather than replacing working eduroam settings.
6. In primary All hub settings → Device → **Wi-Fi & appliance network** → Room-device Wi-Fi sharing, Check hotspot. Luma must report upstream Wi-Fi connected and a separate AP-capable radio. Select a **separate 16–63 character Wi-Fi passphrase**, confirm the current administrator PIN and the actual network-owner approval, then Turn on Luma-Devices. The old same-as-PIN option requires exactly eight digits and exposes the administrator PIN to anyone given the Wi-Fi key; it is not recommended.
7. Join **Luma-Devices** on the iPhone for device onboarding, then use VeSync/that device's official app and the new Wi-Fi passphrase. A plain Levoit Core 300 has no Wi-Fi; only a Wi-Fi-equipped model such as Core 300S can join. Temporarily disconnect the phone VPN only if the official onboarding flow requires local device discovery; reconnect afterward. Never send SUNet credentials to the purifier.
8. Confirm a connected phone gets internet with cellular data temporarily disabled, the device reaches its cloud service, Luma still has live weather/calendar and Pi Connect, and USB/fan power stays stable. Reboot once after initial success and repeat. The phone can then return to its normal Wi-Fi; BLE presence rules remain unchanged. If upstream uses a captive portal, accept its terms on Luma itself and expect session expiry/re-acceptance; the purifier cannot complete a captive portal.
9. To undo sharing, use **Turn off and remove hotspot**. This deletes only Luma's AP profile, not the saved upstream network. Before unplugging the dongle, keep USB on; once removed, the saved automatic cooling mode can resume with the existing minimum-on delay. Do not run the physical USB interruption test with network/storage devices attached.

## Scope and acceptance

The remote roster and USB-network guard can be qualified with synthetic Bluetooth/sysfs and real signed-browser tests. Those do not prove purchased adapter quality, regulatory/channel behavior, physical USB switching, DHCP/NAT on campus, Levoit cloud onboarding or administrator permission. No real radio was reconfigured and no device or adapter was purchased during this work. Keep this distinction when reporting readiness.
