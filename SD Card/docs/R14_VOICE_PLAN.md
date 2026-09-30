# Pleasant offline Luma voice (r14 follow-on)

Status: researched and queued **after Pi Connect recovery**. The signed
`0.2.2` card-recovery candidate does **not** yet change the audible voice.
The currently shipped `luma-voice` process answers with `espeak-ng` at 155
words/minute; this is the source of the mechanical sound the owner reported.

Use local Piper neural text-to-speech, with a single warm-loaded US English
female model, no cloud speech API, account, token, or audio upload. The leading
candidate is Piper `en_US-kristin-medium`: its model card explicitly describes
a female single-speaker voice trained from public-domain LibriVox recordings.
Compare its sample and `en_US-ljspeech-medium` on the physical speaker before
making a final aesthetic choice. LJSpeech is also a US English female model
from public-domain audio. Avoid assuming the general model-repository license
overrides each voice's `MODEL_CARD` or source-dataset restrictions.

Engineering boundary: each medium voice model is about 63 MB, exceeding the
existing app-only `.lup` 24 MiB payload cap; Piper also needs its ARM64
runtime and dependencies. Do not slip an unverified download or dependency
change into the Connect recovery bundle. Once `0.2.2` enables a remote admin
shell, build a separately signed, checksum-pinned **voice asset** install path
and qualify it in the same ARM64 VM before deploying to the Pi. It should
store the model outside `/var/lib/luma` user settings and outside the
version-switching `/opt/luma` symlink, so application rollback cannot corrupt
or erase credentials; use root-owned files and a single atomic directory
rename. Retain `espeak-ng` as a fail-safe if Piper cannot load or misses a
bounded speech deadline. Limit speech output to the existing Luma response
path; timer alarms and phone media routing stay unchanged.

Acceptance checks: model/dataset license recorded; pinned model/config/wheel
hashes; real ARM64 runtime launch; speech generation faster than playback on
the Pi 4; audibly pleasant through the actual screen speaker; no regression
in microphone wake detection or voice calibration; bounded reply length;
working fallback when the model is absent; preservation across application
update, rollback, reboot and power loss. Give the owner a screen-side voice
preview and restrained speed/volume adjustment only after the default voice
has passed the speaker test.

Primary references: [Piper project](https://github.com/OHF-Voice/piper1-gpl),
[Piper model guidance](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md),
[Kristin model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/kristin/medium/MODEL_CARD),
[LJSpeech model card](https://huggingface.co/rhasspy/piper-voices/blob/main/en/en_US/ljspeech/medium/MODEL_CARD).
