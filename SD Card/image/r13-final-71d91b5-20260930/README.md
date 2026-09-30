# r13 image candidate — local artifact

The built `luma-pi4-UNVERIFIED.img.xz` is in the owner's local `SD Card/image/r13-final-71d91b5-20260930` folder; the 644,189,136-byte archive is deliberately excluded from GitHub. Select that archive with Raspberry Pi Imager **Use Custom**. SHA-256: `8c81312502fd29504c62f898ca7a9f398056c6eb036925a0db6743cf1aca68d3`.

It was built from r13 source commit `71d91b5` with source fingerprint `0b0016e13f66f32dda347b5d63a731e5d15527bec75c63db1c441bb4fdd33e4c`. XZ integrity, Windows copy hash, exact root-partition comparison, 162-file audit, and disposable ARM64 API/Pi Connect/USB-backup-broker checks passed. `boot_verified=false` and `hardware_qualified=false`: physical Pi testing remains essential.

The image includes Pi Connect Lite, USB mount authorization package `polkitd`, and ReSpeaker V1 capture diagnostics/gain. It does **not** include the later r14 Pong and Space Invaders polish. A full-card flash erases settings, account tokens and Bluetooth bonds on the target card; make a verified private whole-card backup first if those must be retained. Do not put credentials or backup images in this repository. Follow the [r13 focused test sequence](../../docs/R13_TEST_SEQUENCE.md) and [hardware validation](../../docs/HARDWARE_VALIDATION.md). `main` remains reserved for the owner's accepted v1.
