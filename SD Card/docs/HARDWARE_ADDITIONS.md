# Additional hardware considerations

Luma targets the Raspberry Pi 4, the owner-selected touchscreen, ReSpeaker 2-Mics Pi HAT V1, and a high-endurance microSD card. Check the exact display connector, independent display power, USB touch cable, HAT clearance, enclosure ventilation, and Pi power budget before first boot. No appliance hardware purchase is required for the dashboard itself.

The Levoit Core 300S/300S-P uses its vendor app and VeSync cloud connection. Its network enrollment remains subject to campus policy and real-device testing. Luma's optional 2.4 GHz hotspot requires a compatible second Wi-Fi radio, permission to share the upstream network, and on-device qualification; see [CAMPUS_NETWORK.md](CAMPUS_NETWORK.md).

For local audio, first verify whether the display's built-in HDMI speaker meets the room's needs. Otherwise use an appropriately powered, compatible speaker. Do not connect an unamplified speaker directly to an unsupported output. The Pi and display power requirements are separate. A spare removable USB drive is useful for encrypted settings backups; it is not required to run the dashboard.

No additional appliance controller, hub, sensor, GPU, or second Pi is required by the current feature set. Verify actual parts and wiring before buying or connecting anything else.
