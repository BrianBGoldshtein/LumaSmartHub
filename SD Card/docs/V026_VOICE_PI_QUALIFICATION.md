# Luma 0.2.6 voice qualification on the Raspberry Pi

This is the **owner's physical acceptance test**, not a claim that software tests prove audio quality. Run it only after a signed 0.2.6 beta is available and installed. Keep the Pi in its normal wall location, with its usual speaker, microphone, room distance and Wi-Fi. Do not send account credentials, private calendar details or a recording to report results. A transcript of one short, non-private test command is enough when diagnosing a mishearing.

## 1. Establish the output path first

In **Settings → Hey Luma**, confirm the selected local HDMI/HAT speaker and note the installed voice state. Tap **Test speaker tone**, then **Hear Kristin sample**, then **Hear original voice**. Say whether each was actually audible, not merely whether the button reported success. Record each displayed route/error and whether Kristin and the original voice sound distinct. If the tone fails, troubleshoot the speaker route before repairing or changing a voice model. If the tone and original voice work but Kristin fails with a runtime/model error, try **Repair installed voice** once and repeat these three checks. If Kristin works but you dislike its timbre, record that separately; reinstalling the same model will not change its sound.

Ask **“Hey Luma, what time is it?”** twice. Check the **timestamped** last-reply engine and route immediately after each answer. A fresh `original fallback` result suggests Piper failed for that reply; a fresh `Kristin` result contradicts that hypothesis even if the timbre is unpleasant. A successful route means only that the sound server accepted PCM. Your ears determine audibility. If the speaker is silent, check its mute/volume and the physical PipeWire link before adjusting microphone gain.

## 2. Measure microphone capture before changing recognition

With the room briefly quiet, tap **Check my voice** and let the four-second baseline finish. Speak each displayed phrase at your usual distance and pause after it. For each failed phrase, note which stage failed: the live level meter did not move; Luma saw audio but no complete phrase; the wake was missed; the unrestricted words were wrong; or the words were right but the selected intent was wrong. Do not mark a phrase correct merely because Luma chose the expected intent after a personal correction.

Note any **clipping**, **dropped microphone frames**, automatic HAT gain change, raw-versus-tuned comparison, and whether a mic profile was saved. If gain changes, wait through the new quiet-room baseline and repeat the phrase sequence; earlier measurements were deliberately discarded. Use **Use untouched mic audio** if processing makes words or wakes worse. Do not keep increasing gain when the stream is all zero, clipped, or barely above room sound; inspect the ReSpeaker/PipeWire source instead. No phrase-check audio is saved.

At normal distance, try at least five times each: **“Hey Luma, what time is it?”** and **“Hey Luma, good morning.”** Count correct replies, missed wakes, misheard words and wrong intents separately. Say the two no-wake controls from the guided check without “Hey Luma” and confirm that neither executes. Test once after reboot to confirm that a saved mic profile and owner-confirmed phrase corrections persist, without exporting any recording.

## 3. Challenge false wakes with call audio

Run **Check false wakes during a call** for its complete 90 seconds while a Zoom call, TV or other voice plays at the volume that previously triggered Luma. Do **not** say “Hey Luma.” Voice actions are suppressed during this test. Wait for the armed indication before counting the 90 seconds. Record partial orb hints, constrained suspected wakes and confirmed two-decoder wakes separately. One clean 90-second run does not establish a false-wake rate; repeat on several different calls if the first run is clean.

The stricter two-decoder wake check is **optional**. Offer it only after the guided positive/no-wake evidence or the wake-only plus full call-trial path unlocks it. If enabled, repeat the genuine-owner phrases at several distances **and** the call test. Keep it only if it reduces false activations without unacceptable missed owner wakes. It checks words, **not speaker identity**. A remote caller actually saying “Hey Luma” near the start of a sentence can still activate it; private data and device actions retain the phone/PIN owner gate.

The separate **owner-voice trial** is experimental. It needs explicit consent and another consenting speaker; it reports local vector separation and resource use but does not enable an owner-only lock. Do not use its single eight-sample result as proof that Zoom voices, replayed audio or a similar voice cannot pass. Report the observed separation and latency/RAM if you choose to run it; no raw trial recording is retained.

## Report back

Copy only these non-private results:

- Tone/Kristin/original sample: heard or silent; displayed route and fixed error, if any.
- Two time replies: actual audible voice; timestamped engine/route and any primary Piper error.
- Mic check: approximate speaking distance, whether the meter moved, number of guided phrases passed, clipping or dropped-frame count, gain/profile changes, and raw-versus-tuned winner.
- Five time and five good-morning trials: correct / missed wake / wrong words / wrong intent counts.
- Each complete 90-second call test: number of partial, suspected and independently confirmed wakes; whether any command actually acted outside the trial.
- After reboot: whether the voice model, mic profile and personal phrase corrections remained available.

Stop and report a repeatable **wrong action**, private-data exposure, capture stream failure, or an increase in false wakes after tuning. Do not repeatedly retrain around it. A source-test pass, a `pacat` success, and an installed model label are each weaker evidence than this physical sequence.
