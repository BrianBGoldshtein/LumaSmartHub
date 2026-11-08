# Luma 0.4.0 Beta

Optional **BCM12 inline fan switching** lets Luma control the existing USB fan while keeping USB Wi-Fi, mouse and drives powered. The default remains the existing USB-hub connection; installing this update alone never claims a GPIO pin or changes wiring.

The primary phone and wall share **All hub settings → Device → Fan cooling → Move fan to a GPIO switch**. Guided instructions, an explicit wiring acknowledgment and a new observed five-second fan test are required before Automatic cooling. Changing connections or a detected fault clears the saved test approval. Secondary users cannot alter global fan wiring.

Use the **8086 USB2 Power Switch**, listed at $3.45 before shipping by PiShop.us, plus a USB-A-to-micro-USB cable and suitable GPIO/ground leads. Keep the ReSpeaker V1 microphone: its digital Grove connector exposes BCM12. **BCM12 is header pin 32; physical pin 12 is audio and must not be used.** USB supplies motor current; GPIO supplies only a 3.3 V signal. Leave the board's 5V header pin unconnected. See [ordering, wiring and setup](https://github.com/BrianBGoldshtein/LumaSmartHub/blob/main/SD%20Card/docs/GPIO_FAN_SETUP.md) before buying or rewiring. No board or live Pi wiring has been tested by these software checks.

GPIO mode retains **70°C on / 60°C off**, at least 60 seconds on, and no discovery cycles. It continues during privacy standby because mouse power is separate. Updates, unavailable temperature and loss of the API heartbeat request fan-on through the independent broker. The fixed pin uses exclusive kernel GPIO access; busy/unknown controllers are refused. No arbitrary GPIO, polarity, PWM, shell commands or new runtime packages are exposed.

**Hardware limit:** this low-cost board defaults OFF before the controller starts. A total broker/kernel failure, released GPIO, reboot or wiring fault cannot be made hardware fail-on by software. If the fan does not run, connect it directly to powered USB. The watchdog is not a hardware thermostat and control readback is not an RPM sensor.

Install normally through Settings → Luma software, review **0.4.0 Beta**, retain power through reboot, confirm **0.4.0** and refresh the phone remote. No reflash/reset/re-pairing. The existing remote connected-user roster, private accounts, settings, bonds, timers and games are retained. Leave the current fan connection selected until new hardware is actually wired with the Pi powered off.
