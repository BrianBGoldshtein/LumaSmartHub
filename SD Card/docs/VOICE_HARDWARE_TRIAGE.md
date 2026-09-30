# ReSpeaker V1 physical microphone triage

Owner-reported first Pi test: **Hey Luma calibration says the microphone is live but very quiet, and the meter does not move even when shouting.** This is a failed hardware acceptance gate, not proof that Vosk or wake-phrase matching is at fault. Luma captures from PipeWire's virtual `luma_mic` echo-cancelled source; that node can exist while its physical ReSpeaker input is absent, muted, or disconnected. The image installed the ReSpeaker 2-Mics Pi HAT V1 overlay and the PipeWire AEC module, but the physical capture path and WM8960 mixer state have not been qualified.

From the **Pi Connect remote shell on the Pi**, run these read-only checks and return the output (no passwords or recordings):

```sh
arecord -l
amixer -c seeed2micvoicec cget name='Capture Switch'
amixer -c seeed2micvoicec cget name='Capture Volume'
```

If `arecord -l` does not show `seeed-2mic-voicecard`, stop: do not raise gain or switch the app to an unrelated microphone. Check that the board really is V1/WM8960 and that it is fully seated on the Pi's 40-pin header, with all power **off** before touching the HAT. The r13 source adds a touch-side hardware check and bounded capture-gain slider. Its startup initializer applies only Seeed's published V1 microphone input route, capture switch and saved volume (default 39 of 63), never speaker/playback volume. The physical test must still show a moving meter and pass recognition; an ALSA card report alone is insufficient. If the card appears but the meter remains at zero, compare the physical PipeWire source with `luma_mic` and check echo routing over the remote shell before changing more software. A passing fix needs speech-level, echo/playback and reboot-persistence retests.

Seeed's [V1 getting-started guide](https://wiki.seeedstudio.com/ReSpeaker_2_Mics_Pi_HAT_Raspberry/) uses `arecord -l` to confirm the `seeed-2mic-voicecard` capture device and selects that card in `alsamixer`; its example card number is not fixed across Pis. PipeWire's [echo-cancel module documentation](https://pipewire.pages.freedesktop.org/pipewire/page_module_echo_cancel.html) describes the separate physical capture and virtual source streams. These references explain the test order, not a claim that r12's HAT is working.
