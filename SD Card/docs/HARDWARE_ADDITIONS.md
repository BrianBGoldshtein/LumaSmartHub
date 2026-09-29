# Additional hardware research — 2026-09-26

Research only: no purchases, account enrollment, device commands or physical testing. Exact Woozoo model labels and remotes are still needed. This is not a finalized wiring/BOM or a claim of supported plug-and-play Luma hardware.

## Recommendation

Prefer USB-connected infrared control for the fans, avoiding another campus Wi-Fi client and the ReSpeaker's occupied GPIO. A single room-wide blaster is sufficient only if both fans may act together or their codes are demonstrably distinct. Separate remotes do not prove distinct codes. Independent same-code fans need separately driven, optically isolated emitters placed at the respective receivers; test cross-activation both ways before automations. No appliance disassembly or mains modifications.

### Ready-made candidate

[Irdroid USB Infrared Transceiver v3](https://irdroid.eu/product/usb-infrared-transceiver-v3/) lists EUR32 with TX/RX and Linux support. [Manufacturer firmware/hardware](https://github.com/Irdroid/USB-Infrared-Transmitter-v3) describes three onboard IR LEDs; independently selectable external emitter channels are NOT established. Do not promise this unit controls identical fans independently. [US shipping notice](https://irdroid.com/) says DHL only; landed price is not verified. Exact Pi kernel interface/carrier-learning capability needs qualification; manufacturer mentions both legacy IrToy and mainline support. Do not confuse it with the similarly named IrDA data adapters.

### Lowest component-cost candidate — custom USB Pico controller

[Pico](https://www.raspberrypi.com/products/raspberry-pi-pico/) with USB firmware, two separately transistor-driven/current-limited IR LEDs, a receiver, cable, wiring and enclosure could support independent outputs. Rough planning allowance USD20–30 for a simple discrete-component build before tax/shipping/tools; not a verified complete cart. Requires assembly, custom firmware, power/circuit review, optical isolation and actual fan tests. It is NOT an already implemented Luma transport and not a Linux LIRC device by default.

Component references: [38kHz TSOP38238 receiver](https://www.adafruit.com/product/157) USD1.95, [940nm LED](https://www.adafruit.com/product/387) USD0.75, [Adafruit circuit/parts guide](https://learn.adafruit.com/building-an-infrared-transmitter-and-receiver-board/parts-list). Use a 38kHz receiver only after establishing the remote carrier. [TSMP96000 learning breakout](https://www.adafruit.com/product/5970) USD7.95 preserves carrier but needs specialized capture firmware; follow the actual Vishay datasheet's rated range rather than broader shop copy. Pico H is listed USD5 but out of stock at Adafruit; Pico2W-with-header product page is also out of stock despite a category page claiming stock. Verify live retailer stock before suggesting an order.

[Prebuilt emitter boards](https://www.adafruit.com/product/5639) USD3.95 each plus USD1.25 cables reduce component wiring, but are high-power, wide-coverage and not automatically suitable for isolating identical fans. They can pulse up to400mA each at5V; never power emitters from a GPIO or assume the Pico regulator/Pi USB budget is adequate. A tidier breakout-based build with a carrier-learning receiver, cables and enclosure may cost USD35–45 rather than the bare-component estimate. No final circuit selected.

### Cheap Wi-Fi alternative — not first choice here

[BroadLink deals](https://ebroadlink.com/pages/deals) advertises RM4mini USD23.39 and RMmini3 USD18.99; promotional landing-page figures, not verified checkout/stock. RM4mini is an IR/Wi-Fi blaster; a broad blaster still has the same-code/two-fan limitation. [Stanford Visitor](https://uit.stanford.edu/service/wirelessnet/access) requires acknowledgment and limits sessions/ports. Successful Pi connectivity does not establish that an IoT blaster can enroll or communicate locally. Do not promise Visitor/eduroam compatibility or recommend an unauthorized router workaround. A permitted compatible IoT network must be confirmed first.

## Other additions

### Core build completeness check (research refresh, 2026-09-26)

These are conditional gaps, not instructions to rebuy already purchased parts. The original pasted BOM includes Pi4, Thinlerain display, ReSpeaker, interconnects and power, but does not clearly identify a purchased speaker or cooling kit.

- **Sound:** first check whether the exact Thinlerain has adequate built-in HDMI audio. If so, buy no speaker initially. Otherwise reuse a small powered 3.5mm speaker or budget roughly USD10–20 (planning allowance, not a verified product quote). [Seeed's WM8960 HAT documentation](https://wiki.seeedstudio.com/ReSpeaker_2_Mics_Pi_HAT/) confirms 3.5mm and JST speaker outputs; a bare speaker's impedance, connector and power arrangement require revision-specific verification. Do not connect extra supplies blindly.
- **Cooling:** retain the planned ventilated enclosure, low-profile heatsink and quiet fan; allow roughly USD5–15 if missing, not a verified cart. Check HAT clearance and wiring before purchase. [Raspberry Pi's case-fan discussion](https://www.raspberrypi.com/news/raspberry-pi-4-case-fan/) explains enclosed-board thermal throttling; its official case fan is not automatically a mechanical fit for this custom HAT enclosure.
- **Power:** do not replace the existing supply merely to increase its printed current rating. [Raspberry Pi specifies 5V/3A for Pi4](https://www.raspberrypi.com/documentation/computers/getting-started.html); monitor and peripheral requirements are additional system-design considerations. Retain independent monitor power and verify the total USB load.
- **Backup/installation:** reuse a spare USB drive and an existing laptop microSD reader if available. They are not reasons to buy a large SSD or another computer. Backup software is a separate completion gate.
- **Network alternative to ask about, not assume:** [Stanford's residential networking page](https://uit.stanford.edu/service/network/student_residences) lists wired Ethernet as well as Wi-Fi. If this particular room has an active, permitted port, an ordinary Ethernet cable could avoid the Pi's visitor portal; the Pi has built-in Ethernet. It would NOT itself connect a Wi-Fi-only purifier or BroadLink. Confirm with residential IT before changing the network plan.

Rechecked manufacturer pages still list Irdroid v3 EUR32 (US DHL-only shipping), BroadLink RM4mini USD23.39 promotional price, Adafruit learning receiver USD7.95 and emitter boards USD3.95 each. No checkout/shipping totals or end-to-end hardware compatibility established. For lowest effort, avoid a DIY controller unless the owner wants low-voltage assembly; its low component cost does not make it plug-and-play.

- Core300S/300S-P: no additional IR hub expected; [manufacturer](https://levoit.com/products/core-300s-p-smart-air-purifier) provides VeSync smart control. Luma integration is unofficial/cloud-based, not vendor-endorsed. Needs supported actual API model and approved working Wi-Fi. Plain Core300 is different; confirm label if uncertain.
- Settings-backup feature: reuse a spare USB flash drive; large/high-speed storage is unnecessary for settings-only backups. Feature is not yet implemented. Laptop needs a microSD reader if it lacks one, not an additional permanent hub component.
- Do not add smart plugs on the assumption that fans/purifier resume after power restoration; exact-model behavior and motor/load rating must be checked. Power-only control is not speed/oscillation control.
- No new Zigbee hub, second full Pi or GPU is required by the currently planned feature set. Additional sensors/UPS are optional separate decisions, not required shopping items.
- [Iguanaworks](https://iguanaworks.net/products/usb-ir-transceiver.html) explicitly says it has closed and no longer sells products, despite stale indexed store prices. Do not recommend new purchase there.

## Decision needed before purchase

Obtain both Woozoo model-label/remote photos and whether independent control is required if codes overlap. Ask about willingness to assemble a small low-voltage circuit before selecting DIY. Later, when owner authorizes hardware testing, verify carrier/codes, power semantics, isolated reception and timing. IR has no reliable appliance-state acknowledgment; blind power toggles must not become automatic off actions.
