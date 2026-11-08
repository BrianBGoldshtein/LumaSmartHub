# Independent USB fan switching — BCM12

Researched 2026-11-07. Available in [0.4.0 Beta](https://github.com/BrianBGoldshtein/LumaSmartHub/releases/tag/v0.4.0). Do not select GPIO mode until the switch is wired; software readback is not proof that a fan runs. [Release evidence and Pi Connect update](V040_WORKING_NOTES.md).

## Buy a switch, keep the existing fan and microphone

Recommended: **8086 Consultancy USB2 Power Switch**, a solid-state inline 5 V USB power switch. [PiShop.us lists it at $3.45, in stock](https://www.pishop.us/product/usb-power-switch/) before tax/shipping. The [maker's Lectronz listing](https://www.lectronz.com/products/usb2-power-switch) lists $2.68 before UK-to-US shipping. Compare delivered prices; neither is a delivered-price guarantee. [The Pi Hut also stocks this module](https://thepihut.com/products/usb-power-switch-module). No board was purchased or physically qualified by this project.

The maker documents active-high EN above 2 V, so the Pi's 3.3 V signal is suitable. The module is normally OFF with its supplied pull-down. The Pi Hut documents a 2.5 A switch rating; the Pi 4's combined USB power budget is lower (1.2 A), and includes the Wi-Fi adapter, fan and other attached devices. Check the fan's actual label/current and leave startup margin. Use this only with a 5 V USB fan and 5 V supply, not mains or a USB-PD higher-voltage trigger. No mechanical relay clicks and no rapid power PWM are involved; this preserves coarse 70°C-on/60°C-off control.

Also needed: a USB-A-to-micro-USB power cable for the module, and two signal connections. Your existing fan's USB-A plug fits the module's output. For the installed **ReSpeaker 2-Mics V1/WM8960**, a **Grove 4-pin-to-jumper breakout cable** accesses its digital GPIO12 connector without removing the HAT. [Seeed SKU 110990028](https://www.seeedstudio.com/Grove-4-pin-Female-Jumper-to-Grove-4-pin-Conversion-Cable-5-PCs-per-PAck.html) is a five-pack listed at $3.99 before delivery; only one cable is needed. Match the jumper ends to the board's actual header; confirm whether headers are fitted before buying. A plain JST cable is not automatically Grove-compatible. Do not confuse this with the I2C Grove socket or the V2/TLV320 board. See [Seeed's V1 hardware overview](https://wiki.seeedstudio.com/ReSpeaker_2_Mics_Pi_HAT/), which identifies the digital socket as GPIO12/GPIO13. A stacking-header alternative is possible only if its mechanical clearance is checked.

## Wiring, with all Pi power removed

1. First choose **Keep USB on** in Luma, shut down the Pi normally, and disconnect its power supply. Leave the microphone installed. Never move header wires with the Pi powered.
2. Connect a Pi USB port to the switch's **micro-USB input** using the power cable. This supplies the fan's current; the GPIO does not supply motor power.
3. Plug the fan into the switch's **USB-A output**. Leave the fan's own physical power/speed switch on, at a setting that reliably starts it.
4. Connect **BCM GPIO12** to the module's **EN** pin. On the 40-pin header this is **physical pin 32**. **Physical pin 12 is BCM18/I2S and must not be used**; it belongs to the audio interface. Prefer the HAT's digital GPIO12 Grove breakout if accessible.
5. Connect a Pi/HAT **GND** to the module's **GND** pin. Header physical pin 6 is one ground option. Verify the Grove breakout's printed signal/pin mapping; do not rely only on wire color. Leave the GPIO13 branch and Grove power branch individually insulated and unconnected.
6. Leave the module's **5V header pin unconnected**. USB already supplies it. Do not connect it to a GPIO, the Pi's 3.3 V rail, or another supply. Keep the board's default pull-down configuration; do not change it to pull EN up to USB 5 V.
7. Keep the USB Wi-Fi adapter and mouse in their normal Pi ports. Secure/insulate the board so exposed contacts cannot touch the enclosure or heatsink, then reconnect Pi power.

```
Pi USB ── USB-A/micro-USB cable ── [8086 USB2 switch] ── existing USB fan
Pi BCM12 / ReSpeaker GPIO12 ───────────── EN
Pi GND ───────────────────────────────── GND
                                         5V header: unused
Pi USB ── Wi-Fi adapter                  (stays powered)
```

## Guided settings on the hub or primary remote

In **All hub settings → Device → Fan cooling → Move fan to a GPIO switch**, follow the wiring reminders, choose **BCM12 · inline USB switch**, acknowledge the wiring and choose **Use this fan connection**. No pin number, polarity, path or shell command can be entered. The protected broker only supports fixed BCM12 on a verified Pi 4 GPIO controller and refuses a busy line. Changing connection clears the old physical test and starts in **Keep fan on** mode.

Open **Verify physical fan switching**, acknowledge, and run the five-second fan-only interruption. The independent broker restores the fan even if the browser closes. Actually observe the fan stop and restart, then acknowledge that observation and confirm. Only then enable **Automatic cooling**. Confirm the Wi-Fi link, mouse and any drive remain powered through both the test and later thermal cycling. Reported GPIO/USB bits are not an RPM/voltage sensor.

In GPIO mode, all onboard USB power stays on. The fan alone turns on at **70°C**, stays on for at least **60 seconds**, and turns off at **60°C or below**. It stays off until 70°C without discovery windows. This continues in privacy standby, since mouse power is now separate. While the protected broker is running, software updates, an invalid temperature reading or expiry of the API heartbeat request fan-on. The service restart/reboot portion of an update can interrupt that output, as explained below. A detected fault disarms automatic qualification and requires a fresh observed test.

The board defaults OFF during boot before the controller claims BCM12, including service restarts/reboots during an update. If the entire broker is killed, GPIO is released, the kernel crashes, wiring fails or the Pi is rebooting, software cannot guarantee fan-on. [Linux documents line state as uncontrolled after its request descriptor closes](https://docs.kernel.org/userspace-api/gpio/gpio-v2-get-line-ioctl.html). This inexpensive switch is **not a hardware fail-on thermostat**. If fan-on is not restored or status is unavailable, plug the fan directly into powered Pi USB and use Keep USB on until repaired. Do not claim software watchdog tests prove protection against total OS/power failure.

## Returning to the old connection

Choose Keep fan on, shut down and remove Pi power, move the fan's USB plug directly to a Pi USB port, and disconnect/insulate the GPIO switch wiring. Boot, select **Existing USB hub switching**, acknowledge and apply. This clears qualification again. The old whole-hub physical test is required before its Automatic mode; USB networking/storage and standby still keep that whole hub powered. Never run the old whole-hub interruption test while depending on a USB network adapter.

## Acceptance still needed on the actual hardware

No live GPIO, USB switching, HAT wiring or fan is exercised by source tests. Check correct pin/ground/5 V wiring, fan starting current, five-second restoration, Wi-Fi/mouse continuity, microphone/speaker function, 70/60 hysteresis, standby, reboot startup and fallback to direct USB. Keep the existing SD card, settings and bonds; the feature is designed as an application update without extra GPIO packages or a reflash.
