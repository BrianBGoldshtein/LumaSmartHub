#!/usr/bin/env python3
"""Offline custom-keyword research, NOT the production wake path.

Use a separate venv with sherpa-onnx 1.13.8, numpy and sentencepiece. The
official English 3.3M model folder is argv[1]. Synthetic smoke is useful for
rejecting a broken candidate, not for proving room/accent false-wake rates.
Optional --wav-dir adds local/public WAV negatives without uploading audio.
No user enrollment, command execution, recorded microphone input or network.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
from pathlib import Path
import resource
import re
import subprocess
import tempfile
import time
import tarfile
import wave
import zipfile

import numpy as np
import sentencepiece as spm
import sherpa_onnx


POSITIVES = ('Hey Luma', 'Hey Luma what time is it', 'Hey Luma good morning',
             'Hey Luma start a timer for five minutes', 'Okay hey Luma what is the weather tomorrow')
NEGATIVES = ('What time is it', 'Good morning everyone', 'Hey Laura what time is it',
             'Hey Lou good morning', 'The room is brighter today', 'Hey Luna what time is it',
             'Okay let us move on to the next slide', 'Could you repeat the question please',
             'The meeting starts at two and ends at three', 'I would like to start a timer',
             'Hey look at the screen', 'That is a great question thank you',
             'The volume is quite low can you turn it up', 'They bloom in spring',
             'Can everyone hear me okay', 'Here is the summary of our conversation')

# Separate synthetic phrase set, generated only after freezing a configuration.
# Still one synthetic voice, NOT an estimate of the owner's/room's accuracy.
HELDOUT_POSITIVES = ('Hey Luma what is on my calendar', 'Hey Luma turn the brightness down',
    'Hey Luma what is the temperature', 'Hey Luma cancel my timer',
    'Hey Luma how many tasks do I have', 'Hey Luma switch to the arcade theme',
    'Please hey Luma show the weather', 'Um hey Luma set a timer for ten seconds',
    'Hey Luma good night', 'Hey Luma pause the screen',
    'Hey Luma what is my next event', 'Hey Luma make the volume quieter')
HELDOUT_NEGATIVES = ('Hello everybody can we begin', 'Hey Lucas could you check the time',
    'Hey Lucy the timer has finished', 'Hey Linda what is on the agenda',
    'The lumen output looks good', 'A human can understand this question',
    'Okay Laura please move to the next slide', 'They bloom when the weather is warmer',
    'I was saying the room has been quiet', 'Let us assume that is the correct answer',
    'He knew my name from the calendar', 'Hey Luna please turn the brightness down')
VALIDATION_POSITIVES = ('Hey Luma show my timers', 'Hey Luma tell me the date',
    'Hey Luma is it going to rain', 'Hey Luma show my tasks',
    'Hey Luma what happens tomorrow', 'Hey Luma brighten the display',
    'Oh hey Luma tell me the time', 'Uh hey Luma turn down the volume',
    'Hey Luma switch to the wooden theme', 'Hey Luma when should I leave',
    'Hey Luma show the settings', 'Hey Luma start a timer for two hours',
    'Hey Luma show me my upcoming events', 'Hey Luma stop the alarm',
    'Hey Luma what is the forecast tonight', 'Okay hey Luma good morning')
VALIDATION_NEGATIVES = ('Hey Emma can you take a look', 'Hey Lila could you read the next part',
    'Hey Luis what time does it start', 'Hey Luke we should turn down the volume',
    'The human body can adapt to this', 'There is a little room for improvement',
    'They knew my schedule before the meeting', 'A luminous screen is easier to see',
    'Here you are let us begin', 'I assume we will finish in two hours',
    'Hey everyone show me the settings', 'We should stop the alarm now',
    'The room temperature is higher tonight', 'I heard the music during the call',
    'Please tell me when the next lecture starts', 'How do we make the display brighter')

# Freeze the live configuration before first evaluation of this fourth set.
# It includes deliberate quoted wake phrases; only the final command/prefix
# pipeline, not raw KWS alone, can judge whether those are valid requests.
RELEASE_CHECK_POSITIVES = ('Hey Luma what is the time right now',
    "Hey Luma what's the time", 'Hey Luma show the weather',
    'Hey Luma start a timer for three minutes',
    'Hey Luma change theme to arcade', 'Hey Luma pause timer',
    'Hey Luma what tasks are due today', 'Hey Luma good night')
RELEASE_CHECK_NEGATIVES = ('I said hey Luma yesterday',
    'Do not say hey Luma during the meeting', 'Never say hey Luma on this call',
    'We call this screen Luma', 'Hey Lily can you close the door',
    'Hey Hugo will you join us tomorrow', 'Hey Lucy please read the next line',
    'Hey Luna what is the time right now', 'They bloom around this time of year',
    'Please pause the meeting for three minutes',
    'The computer should show the weather', 'What tasks are due today')


def samples(path: Path):
    with wave.open(str(path)) as audio:
        if audio.getnchannels() != 1 or audio.getsampwidth() != 2:
            raise ValueError('Provide mono 16-bit PCM WAV files.')
        rate = audio.getframerate()
        data = np.frombuffer(audio.readframes(audio.getnframes()), dtype='<i2').astype(np.float32) / 32768
    return data, rate


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('model', type=Path)
    parser.add_argument('--threshold', type=float, default=.4)
    parser.add_argument('--score', type=float, default=1)
    parser.add_argument('--max-active-paths', type=int, default=4, choices=(4,8,16), help='Bounded decoder beam for rare-name recall research')
    parser.add_argument('--wav-dir', type=Path)
    parser.add_argument('--negative-archive', type=Path, help='Public LibriSpeech dev-clean archive; read FLAC in memory, never extract files')
    parser.add_argument('--corpus-only', action='store_true', help='Skip synthetic speech; requires --negative-archive')
    parser.add_argument('--corpus-limit', type=int, default=0, help='Optional bounded corpus smoke; zero means the whole corpus')
    parser.add_argument('--fp32', action='store_true')
    parser.add_argument('--phone', action='store_true', help='Use official zh-en 3M phoneme model with explicit Hey Luma pronunciation')
    parser.add_argument('--piper-asset', type=Path, help='Optional existing Kristin asset for neural synthetic holdouts')
    parser.add_argument('--synthetic-cache', type=Path, help='Reuse disposable synthetic WAVs across settings; never microphone recordings')
    parser.add_argument('--vosk-model', type=Path, help='Compare the combined constrained-ASR + keyword gate (set backend PYTHONPATH)')
    parser.add_argument('--isolate-wake', action='store_true', help='Also verify only the ASR-aligned wake audio; requires --vosk-model')
    parser.add_argument('--candidate-adapter', action='store_true', help='Compare the bounded backend verifier; requires FP32 phonetic model, score 3 / threshold .1 / beam 8 and both contrast sets')
    parser.add_argument('--contrast-luna', action='store_true', help='Add a competing Hey Luna phonetic hypothesis; requires --phone, research only')
    parser.add_argument('--stress-variants', action='store_true', help='Compare stressed/unstressed Hey and name vowels; requires --phone, research only')
    parser.add_argument('--contrast-common', action='store_true', help='Compare Hey Laura and They bloom as non-wake acoustic competitors; requires --phone, research only')
    parser.add_argument('--contrast-near-names', action='store_true', help='Compare Hey Luis and Hey Lucy as explicit non-wake hypotheses; requires --phone')
    parser.add_argument('--neural-only', action='store_true', help='Skip eSpeak smoke; requires --piper-asset')
    parser.add_argument('--heldout-phrases', action='store_true', help='Separate synthetic phrase set; use a fresh synthetic cache')
    parser.add_argument('--validation-phrases', action='store_true', help='Fresh third phrase set after freezing position/contiguity guards; use a fresh cache')
    parser.add_argument('--release-check-phrases', action='store_true', help='Fourth frozen-config set including quoted wakes; judge with the timed command probe too')
    parser.add_argument('--near-speech-start', action='store_true', help='Evaluate candidate position guard; set backend PYTHONPATH, no ASR spelling requirement')
    args = parser.parse_args()
    if sum((args.heldout_phrases, args.validation_phrases, args.release_check_phrases)) > 1:
        parser.error('Choose one phrase set.')
    positives = (RELEASE_CHECK_POSITIVES if args.release_check_phrases else
                 VALIDATION_POSITIVES if args.validation_phrases else
                 HELDOUT_POSITIVES if args.heldout_phrases else POSITIVES)
    negatives = (RELEASE_CHECK_NEGATIVES if args.release_check_phrases else
                 VALIDATION_NEGATIVES if args.validation_phrases else
                 HELDOUT_NEGATIVES if args.heldout_phrases else NEGATIVES)
    if not 0 < args.threshold < 1 or not 0 < args.score <= 3:
        parser.error('Threshold must be (0,1) and score (0,3].')
    if args.neural_only and not args.piper_asset:
        parser.error('--neural-only requires --piper-asset')
    if args.synthetic_cache and not args.piper_asset:
        parser.error('--synthetic-cache requires --piper-asset')
    if args.isolate_wake and not args.vosk_model:
        parser.error('--isolate-wake requires --vosk-model')
    if args.corpus_only and not args.negative_archive:
        parser.error('--corpus-only requires --negative-archive')
    if args.corpus_only and args.neural_only:
        parser.error('Choose either --corpus-only or --neural-only')
    if args.corpus_limit<0 or args.corpus_limit>3000:
        parser.error('--corpus-limit must be between zero and 3000')
    if args.corpus_limit and not args.negative_archive:
        parser.error('--corpus-limit requires --negative-archive')
    if args.candidate_adapter and not (args.phone and args.fp32 and args.score==3
            and args.threshold==.1 and args.max_active_paths==8
            and args.contrast_luna and args.contrast_common and args.contrast_near_names):
        parser.error('--candidate-adapter requires --phone --fp32 --score 3 --threshold .1 --max-active-paths 8 --contrast-luna --contrast-common --contrast-near-names')
    if args.contrast_luna and not args.phone:
        parser.error('--contrast-luna requires --phone')
    if args.stress_variants and (not args.phone or args.candidate_adapter):
        parser.error('--stress-variants requires --phone and cannot compare the unmodified adapter')
    if args.contrast_common and not args.phone:
        parser.error('--contrast-common requires --phone')
    if args.contrast_near_names and not args.phone:
        parser.error('--contrast-near-names requires --phone')
    model = args.model.resolve(strict=True)
    if args.phone:
        keyword_tokens = ['HH','EY1','L','UW1','M','AH0']
    else:
        processor = spm.SentencePieceProcessor(model_file=str(model/'bpe.model'))
        keyword_tokens = processor.encode('HEY LUMA', out_type=str)
    allowed = {line.rsplit(' ',1)[0] for line in (model/'tokens.txt').read_text().splitlines()}
    if not keyword_tokens or any(token not in allowed for token in keyword_tokens):
        raise ValueError('Wake phrase tokenization is invalid for this model.')
    results = []
    vosk_model=None
    adapter=None
    if args.candidate_adapter:
        from luma.keyword_wake import load_pinned_candidate
        adapter=load_pinned_candidate(model)
    if args.vosk_model:
        from vosk import KaldiRecognizer, Model, SetLogLevel
        from luma.voice import command_grammar
        from luma.voice_wake import wake_near_start
        SetLogLevel(-1)
        vosk_model=Model(str(args.vosk_model))
    with tempfile.TemporaryDirectory(prefix='luma-keyword-smoke-') as folder:
        root = Path(folder)
        keywords = root/'keywords.txt'
        keyword_lines=[' '.join(keyword_tokens)+' @HEY_LUMA']
        if args.contrast_luna:
            keyword_lines.append('HH EY1 L UW1 N AH0 @HEY_LUNA')
        if args.contrast_common:
            keyword_lines.extend(('HH EY1 L AO1 R AH0 @NO_WAKE_LAURA',
                                  'DH EY1 B L UW1 M @NO_WAKE_THEY_BLOOM'))
        if args.contrast_near_names:
            keyword_lines.extend(('HH EY1 L UW0 IY1 S @NO_WAKE_LUIS',
                                  'HH EY1 L UW1 S IY0 @NO_WAKE_LUCY'))
        if args.stress_variants:
            for hey_stress,name_stress in ((0,1),(1,0),(0,0)):
                keyword_lines.append(f'HH EY{hey_stress} L UW{name_stress} M AH0 @HEY_LUMA')
                if args.contrast_luna:
                    keyword_lines.append(f'HH EY{hey_stress} L UW{name_stress} N AH0 @HEY_LUNA')
        keywords.write_text('\n'.join(keyword_lines)+'\n', encoding='utf-8')
        suffix = '.onnx' if args.fp32 else '.int8.onnx'
        model_prefix = 'epoch-13-avg-2-chunk-16-left-64' if args.phone else 'epoch-12-avg-2-chunk-16-left-64'
        started = time.monotonic()
        spotter = sherpa_onnx.KeywordSpotter(
            tokens=str(model/'tokens.txt'),
            encoder=str(model/f'encoder-{model_prefix}{suffix}'),
            decoder=str(model/f'decoder-{model_prefix}{".onnx" if args.phone else suffix}'),
            joiner=str(model/f'joiner-{model_prefix}{suffix}'),
            keywords_file=str(keywords), keywords_score=args.score,
            keywords_threshold=args.threshold, max_active_paths=args.max_active_paths,
            num_threads=1, provider='cpu')
        load_ms = round((time.monotonic()-started)*1000,1)

        def keyword_hits(pcm, rate):
            stream = spotter.create_stream()
            hits = []
            # Quarter-second chunks match Luma's capture framing; no whole
            # file shortcut that conceals streaming/endpoint behavior.
            chunk = rate//4
            for offset in range(0,len(pcm)+rate,chunk):
                frame = pcm[offset:offset+chunk] if offset<len(pcm) else np.zeros(chunk,dtype=np.float32)
                stream.accept_waveform(rate,frame)
                while spotter.is_ready(stream):
                    spotter.decode_stream(stream)
                    result = spotter.keyword_spotter.get_result(stream)
                    if result.keyword.strip():
                        hits.append({'keyword':result.keyword.strip(),'timestamps':result.timestamps})
                        spotter.reset_stream(stream)
            return hits

        def evaluate(path, label, expected, *, decoded_audio=None):
            pcm,rate = samples(path) if decoded_audio is None else decoded_audio
            # Match the Pi's mono 16kHz s16le capture for every compared path.
            # Letting the native detector resample a TTS WAV internally while
            # the adapter received externally resampled PCM is not a like-
            # for-like comparison, even if both started from the same WAV.
            if rate!=16000:
                pcm=np.interp(np.arange(int(len(pcm)*16000/rate))*rate/16000,
                              np.arange(len(pcm)),pcm)
            raw=np.clip(np.rint(pcm*32768),-32768,32767).astype('<i2').tobytes()
            pcm=np.frombuffer(raw,dtype='<i2').astype(np.float32)/32768
            rate=16000
            started = time.monotonic()
            hits = keyword_hits(pcm,rate)
            row={'sample':label,'expected':expected,'detected':any(hit['keyword']=='HEY_LUMA' for hit in hits),
                            'hits':hits,'seconds':round(len(pcm)/rate,2),
                            'pcm_sha256':hashlib.sha256(pcm.tobytes()).hexdigest(),
                            'decode_ms':round((time.monotonic()-started)*1000,1)}
            if args.near_speech_start:
                from luma.keyword_gate import keyword_near_sound_start
                from luma.keyword_wake import (KeywordEvidence, KeywordWakeError,
                                              MAX_NAME_PHONE_GAP_SECONDS)
                targets = [hit['timestamps'] for hit in hits if hit['keyword']=='HEY_LUMA'
                           and len(hit['timestamps'])==6
                           and all(b-a<=MAX_NAME_PHONE_GAP_SECONDS
                                   for a,b in zip(hit['timestamps'][2:],hit['timestamps'][3:]))]
                first = min(times[0] for times in targets) if targets else None
                try:
                    row['start_gate_detected'] = keyword_near_sound_start(
                        KeywordEvidence(first is not None, first),
                        [raw[offset:offset+8000] for offset in range(0,len(raw),8000)])
                except KeywordWakeError as error:
                    row['start_gate_error'] = str(error)
            if adapter:
                from luma.keyword_wake import KeywordWakeError
                try:
                    evidence=adapter.verify([raw[offset:offset+8000] for offset in range(0,len(raw),8000)])
                    row['adapter_detected']=evidence.detected
                    row['adapter_start_seconds']=evidence.first_token_seconds
                except KeywordWakeError as error:
                    # A rejected/incomplete clip is NOT a measured negative.
                    row['adapter_error']=str(error)
            if vosk_model:
                # Independent runtime research: no command gets dispatched.
                asr=KaldiRecognizer(vosk_model,16000,json.dumps(command_grammar('hey luma')))
                asr.SetWords(True)
                asr_audio=raw+bytes(32000)
                parts=[]
                aligned=[]
                for offset in range(0,len(asr_audio),8000):
                    if asr.AcceptWaveform(asr_audio[offset:offset+8000]):
                        decoded=json.loads(asr.Result())
                        parts.append(decoded.get('text',''))
                        aligned.extend(decoded.get('result',[]))
                decoded=json.loads(asr.FinalResult())
                parts.append(decoded.get('text',''))
                aligned.extend(decoded.get('result',[]))
                row['asr_proposal']=wake_near_start(' '.join(parts))
                row['combined_detected']=row['asr_proposal'] and row['detected']
                if args.isolate_wake:
                    # No ground-truth label controls the slice. Only the ASR
                    # proposal and its actual alignment select a candidate;
                    # a forced false proposal must still pass the acoustic KWS.
                    isolated=[]
                    if row['asr_proposal']:
                        for index,word in enumerate(aligned[:-1]):
                            following=aligned[index+1]
                            if word.get('word')=='hey' and following.get('word')=='luma':
                                start=max(0,float(word['start'])-.15)
                                end=min(len(pcm)/rate,float(following['end'])+.15)
                                if 0<end-start<=2.5:
                                    isolated=keyword_hits(pcm[int(start*rate):int(end*rate)],rate)
                                break
                    row['isolated_hits']=isolated
                    row['isolated_detected']=row['asr_proposal'] and any(hit['keyword']=='HEY_LUMA' for hit in isolated)
            results.append(row)

        for voice in (() if args.neural_only or args.corpus_only else ('en-us','en-gb','en-us+f3','en-us+m3')):
            for speed in (145,180):
                for expected,phrases in ((True,positives),(False,negatives)):
                    for index,phrase in enumerate(phrases):
                        path = root/'sample.wav'
                        subprocess.run(['espeak-ng','-v',voice,'-s',str(speed),'-w',str(path),phrase],check=True)
                        evaluate(path,f'{voice}/{speed}/{"positive" if expected else "negative"}/{index}',expected)
        if args.wav_dir:
            for path in sorted(args.wav_dir.rglob('*.wav')):
                evaluate(path,'wav-negative/'+str(path.relative_to(args.wav_dir)),False)
        corpus_summary=None
        if args.negative_archive:
            import soundfile as sf
            # Public read-speech negatives are not Zoom/room/owner acceptance.
            # Use annotations only to EXCLUDE a literal wake, not to tune KWS.
            annotations={}
            with tarfile.open(args.negative_archive,'r|gz') as corpus:
                for member in corpus:
                    if member.isfile() and member.name.endswith('.trans.txt'):
                        if member.size>1024*1024:
                            raise ValueError('Unexpected transcript size.')
                        for line in corpus.extractfile(member).read().decode('utf-8').splitlines():
                            key,_,words=line.partition(' ')
                            annotations[key]=not bool(re.search(r'\bHEY LUMA\b',words))
            count=excluded=0
            with tarfile.open(args.negative_archive,'r|gz') as corpus:
                for member in corpus:
                    if not member.isfile() or not member.name.endswith('.flac'):
                        continue
                    if not re.fullmatch(r'LibriSpeech/dev-clean/\d+/\d+/\d+-\d+-\d+\.flac',member.name):
                        raise ValueError('Unexpected corpus member name.')
                    key=Path(member.name).stem
                    if key not in annotations:
                        raise ValueError('Corpus audio has no annotation.')
                    if not annotations[key]:
                        excluded+=1
                        continue
                    if not 0<member.size<2*1024*1024:
                        raise ValueError('Unexpected corpus audio size.')
                    with sf.SoundFile(io.BytesIO(corpus.extractfile(member).read())) as audio:
                        if audio.channels!=1 or audio.samplerate!=16000 or len(audio)>45*16000:
                            raise ValueError('Unexpected corpus audio format.')
                        pcm=audio.read(dtype='float32')
                    evaluate(None,'librispeech-dev-clean/'+key,False,decoded_audio=(pcm,16000))
                    count+=1
                    if args.corpus_limit and count>=args.corpus_limit:
                        break
            with args.negative_archive.open('rb') as source:
                corpus_hash=hashlib.file_digest(source,'sha256').hexdigest()
            corpus_summary={'sha256':corpus_hash,
                            'evaluated':count,'literal_wake_excluded':excluded,
                            'license':'CC BY 4.0','source':'https://www.openslr.org/12',
                            'limited':bool(args.corpus_limit)}
        if args.piper_asset and not args.corpus_only:
            # Read only the two exact, source-hash-pinned model members. No
            # archive paths or wheel code are extracted/executed from this file.
            from piper import PiperVoice, SynthesisConfig
            lock = json.loads(Path(__file__).with_name('voice-assets.lock.json').read_text())
            with zipfile.ZipFile(args.piper_asset) as archive:
                for name in ('model/en_US-kristin-medium.onnx','model/en_US-kristin-medium.onnx.json'):
                    info=archive.getinfo(name)
                    if not 0<info.file_size<80*1024*1024:
                        raise ValueError('Unexpected voice model size.')
                    data=archive.read(name)
                    if hashlib.sha256(data).hexdigest()!=lock['files'][name]:
                        raise ValueError('Neural voice model does not match source pin.')
                    (root/Path(name).name).write_bytes(data)
            voice=PiperVoice.load(str(root/'en_US-kristin-medium.onnx'))
            cache=args.synthetic_cache
            cache_manifest=None
            if cache:
                cache.mkdir(parents=True,exist_ok=True)
                manifest=cache/'synthetic.json'
                specification={'voice':'en_US-kristin-medium','positives':list(positives),
                               'negatives':list(negatives),'length_scales':[.8,1,1.2]}
                if manifest.exists():
                    cache_manifest=json.loads(manifest.read_text())
                    if cache_manifest.get('specification')!=specification:
                        raise ValueError('Synthetic cache specification changed; use a new research folder.')
                else:
                    if any(cache.iterdir()):
                        raise ValueError('New synthetic cache must be an empty research folder.')
                    cache_manifest={'specification':specification,'files':{}}
            for length in (.8,1,1.2):
                for expected,phrases in ((True,positives),(False,negatives)):
                    for index,phrase in enumerate(phrases):
                        name=f'kristin-{length}-{"positive" if expected else "negative"}-{index}.wav'
                        path=cache/name if cache else root/'neural-sample.wav'
                        if cache and path.exists():
                            if hashlib.sha256(path.read_bytes()).hexdigest()!=cache_manifest['files'].get(name):
                                raise ValueError('Synthetic cache file does not match its digest.')
                        else:
                            with wave.open(str(path),'wb') as audio:
                                voice.synthesize_wav(phrase,audio,SynthesisConfig(length_scale=length))
                            if cache:
                                cache_manifest['files'][name]=hashlib.sha256(path.read_bytes()).hexdigest()
                                manifest.write_text(json.dumps(cache_manifest,sort_keys=True),encoding='utf-8')
                        evaluate(path,f'kristin/{length}/{"positive" if expected else "negative"}/{index}',expected)
        report = {'kind':'synthetic-wake-research-not-hardware-qualification',
                  'runtime':'sherpa-onnx '+sherpa_onnx.__version__, 'keyword_tokens':keyword_tokens,
                  'threshold':args.threshold,'score':args.score,'int8':not args.fp32,
                  'max_active_paths':args.max_active_paths,
                  'isolate_wake':args.isolate_wake,
                  'candidate_adapter':args.candidate_adapter,
                  'contrast_luna':args.contrast_luna,
                  'stress_variants':args.stress_variants,
                  'contrast_common':args.contrast_common,
                  'contrast_near_names':args.contrast_near_names,
                  'heldout_phrases':args.heldout_phrases,
                  'validation_phrases':args.validation_phrases,
                  'release_check_phrases':args.release_check_phrases,
                  'near_speech_start':args.near_speech_start,
                  'corpus':corpus_summary,
                  'model_files':{path.name:hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sorted(model.glob('*.onnx'))},
                  'load_ms':load_ms,'peak_rss_kib':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss,
                  'peak_rss_scope':'whole probe including any ASR/TTS/FLAC reader, not KWS alone',
                  'positive_hits':sum(row['expected'] and row['detected'] for row in results),
                  'positive_total':sum(row['expected'] for row in results),
                  'negative_hits':sum(not row['expected'] and row['detected'] for row in results),
                  'negative_total':sum(not row['expected'] for row in results),'samples':results}
        print(json.dumps(report,sort_keys=True))


if __name__=='__main__':
    main()
