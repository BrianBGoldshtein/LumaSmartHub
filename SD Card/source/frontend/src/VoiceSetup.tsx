import {useEffect,useState} from "react";
import {useSetupActivity} from "./setupActivity";
import "./features.css";
type Calibration={active:boolean;passed:boolean;phrase:string|null;completed:number;total:number;message:string;attempts:number;agent_available:boolean;agent_phase:string;agent_error:string|null;signal_available:boolean;signal_rms:number;signal_peak:number;last_heard:string;last_wake_detected:boolean|null;last_intent:string;applied_gain:number|null;gain_adjustments:number;dropped_frames:number};
type MicHardware={available:boolean;gain:number;max_gain:number;capture_on:boolean;route_ready:boolean};
type VoiceGroup={title:string;examples:string[]};
type PhrasePreview={understood:boolean;command:string|null;intent:string|null;model_suggestion:string|null;model_confidence:number|null;executed:false};
type VoiceAsset={phase:"checking"|"downloading"|"verifying"|"installing"|"ready"|"failed";message:string;downloaded_bytes?:number;total_bytes?:number;last_reply_engine?:"piper"|"fallback"|"silent"|null;last_reply_error?:string|null;last_preview_error?:string|null;last_tone_error?:string|null};
const outputErrorCopy:Record<string,string>={audio_session_unavailable:"The desktop audio session was unavailable.",speaker_route_unavailable:"The selected speaker route failed.",synthesis_unavailable:"The local voice could not generate audio.",voice_asset_unavailable:"Kristin is not installed yet.",piper_retry_wait:"Kristin is cooling down after an error; Luma will retry."};
const diagnosticCopy:Record<string,string>={
  recognizer_unavailable:"The offline speech engine could not start. Reinstall or update Luma, then retry.",
  model_unavailable:"Luma’s local speech model is missing or could not be loaded. Reinstall or update Luma, then retry.",
  audio_capture_tool_missing:"The local audio-capture component is missing. The current Luma system image is required.",
  capture_source_invalid:"The configured microphone source is invalid. Reset the local voice audio configuration.",
  capture_source_unavailable:"Luma could not open the ReSpeaker microphone source. Check that the HAT is connected and the audio session is running.",
  capture_stream_stopped:"The microphone stream stopped unexpectedly. Check the ReSpeaker connection, then run the check again.",
};
const previewLibrary:VoiceGroup[]=[{title:'Weather',examples:['What’s the weather today?','Will it rain today?','What is the temperature?']},{title:'Calendar',examples:['When is my next event?','What’s on my calendar today?','What’s on my calendar tomorrow?','What is happening now?']},{title:'Tasks & time',examples:['What are my tasks today?','What tasks are due today?','What time is it?',"What's the time?",'What day is it?','How much time is left on my timer?']},{title:'Everyday controls',examples:['Start focus timer','Pause timer','Good morning','Good night','Screen off','Wake screen','Change brightness','Change theme to arcade','Hide my calendar','What can I say?']}];
async function request(path:string,body?:unknown){
  const response=await fetch(`/api/v1/${path}`,{method:body===undefined?"GET":path==="settings"?"PATCH":"POST",headers:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw Error(typeof data.detail==="string"?data.detail:"Voice check unavailable.");return data;
}
export function VoiceSetup({demo}:{demo:boolean}){
  const [enabled,setEnabled]=useState<boolean|null>(demo?true:null),[status,setStatus]=useState<Calibration>(),[message,setMessage]=useState(""),[busy,setBusy]=useState(false);
  const [hardware,setHardware]=useState<MicHardware|undefined>(demo?{available:true,gain:39,max_gain:63,capture_on:true,route_ready:true}:undefined),[gain,setGain]=useState(39);
  const [library,setLibrary]=useState<VoiceGroup[]>(demo?previewLibrary:[]);
  const [phrase,setPhrase]=useState("What's the time?"),[phrasePreview,setPhrasePreview]=useState<PhrasePreview>(),[phraseError,setPhraseError]=useState("");
  const [voiceAsset,setVoiceAsset]=useState<VoiceAsset|undefined>(demo?{phase:"ready",message:"Preview only — offline voice is not installed here."}:undefined);
  const [sampleMessage,setSampleMessage]=useState("");
  const [toneMessage,setToneMessage]=useState("");
  useEffect(()=>{if(!demo)request('voice/library').then(data=>setLibrary(data.groups)).catch(()=>setLibrary([]));},[demo]);
  useSetupActivity(busy || !!status?.active);
  useEffect(()=>{if(!demo)request("settings").then(data=>setEnabled(data.voice_enabled)).catch(()=>setMessage("Device connection unavailable."));},[demo]);
  useEffect(()=>{if(!demo)request("voice/hardware").then((data:MicHardware)=>{setHardware(data);setGain(data.gain);}).catch(()=>setHardware(undefined));},[demo]);
  useEffect(()=>{
    if(demo)return;
    let stopped=false;
    const refresh=()=>{void request("voice/asset").then((next:VoiceAsset)=>{if(!stopped)setVoiceAsset(next);}).catch(()=>{if(!stopped)setVoiceAsset(undefined);});};
    refresh();const timer=window.setInterval(refresh,5000);
    return ()=>{stopped=true;window.clearInterval(timer);};
  },[demo]);
  useEffect(()=>{
    if(demo || !status?.active)return;
    const timer=window.setInterval(()=>request("voice/calibration").then((next:Calibration)=>{setStatus(next);if(next.applied_gain!==null)setGain(next.applied_gain);}).catch(()=>setMessage("Voice check connection interrupted.")),1000);
    return ()=>clearInterval(timer);
  },[demo,status?.active]);
  async function act(fn:()=>Promise<void>){setBusy(true);setMessage("");try{await fn();}catch(error){setMessage(error instanceof Error?error.message:"Voice check unavailable.");}finally{setBusy(false);}}
  const signalPercent=status?.signal_available?Math.max(2,Math.min(100,Math.round(status.signal_rms*1000))):0;
  const voiceDiagnostic=!status?.active?null:status.agent_error?diagnosticCopy[status.agent_error]??"The local voice service reported a startup problem.":!status.agent_available?"Voice service has not checked in yet. It may still be starting; if this stays here, retry the microphone check.":!status.signal_available?"Voice service is running, but no microphone audio frames have arrived yet.":status.signal_peak>=.995?"Mic is live but clipping. Lower its capture gain before continuing.":status.signal_rms<.002?"Mic is live but very quiet. Speak closer or raise the ReSpeaker capture gain.":"Mic is live. Say the phrase below at your normal room distance.";
  return <section><h2>Hey Luma</h2><p>Your local voice controls are on by default. Say “Hey Luma” followed by a command. Audio stays in memory on this Pi; it is not saved or uploaded. You can turn the microphone off below; that choice survives restarts.</p>
    <button disabled={busy || enabled===null} onClick={()=>act(async()=>{if(!demo)await request("settings",{voice_enabled:!enabled});setEnabled(!enabled);setStatus(undefined);})}>{enabled===null?"Loading microphone setting…":enabled?"Turn microphone off":"Enable local voice"}</button>
    <div className="voice-asset-status"><strong>Spoken replies</strong>
      <p>{voiceAsset?.phase==="ready"?(demo?voiceAsset.message:"Kristin installed · speaker playback not yet confirmed"):(voiceAsset?.message||"Checking the local speech voice…")}</p>
      {!demo&&voiceAsset?.last_reply_engine&&<p role="status">Last spoken reply: {voiceAsset.last_reply_engine==="piper"?"Kristin":voiceAsset.last_reply_engine==="fallback"?"original fallback voice":"silent"}{voiceAsset.last_reply_error?` · ${outputErrorCopy[voiceAsset.last_reply_error]??"Playback needs checking."}`:""}</p>}
      {!demo&&voiceAsset?.last_preview_error&&<p role="status">Sample check: {outputErrorCopy[voiceAsset.last_preview_error]??"Playback needs checking."}</p>}
      {!demo&&voiceAsset?.last_tone_error&&<p role="status">Speaker test: {outputErrorCopy[voiceAsset.last_tone_error]??"Speaker route needs checking."}</p>}
      {voiceAsset?.phase==="downloading"&&!!voiceAsset.total_bytes&&<div className="voice-meter" role="progressbar" aria-label="Offline voice download" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(100*(voiceAsset.downloaded_bytes||0)/voiceAsset.total_bytes)}><span style={{width:`${Math.round(100*(voiceAsset.downloaded_bytes||0)/voiceAsset.total_bytes)}%`}}/></div>}
      {voiceAsset?.phase==="ready"&&!demo&&<button disabled={busy} onClick={()=>{setBusy(true);setSampleMessage("");void request("voice/asset/preview",{}).then(()=>setSampleMessage("Sample sent to Luma’s speaker. Did you hear it?")).catch(error=>setSampleMessage(error instanceof Error?error.message:"Sample playback failed.")).finally(()=>setBusy(false));}}>Hear a sample</button>}
      {sampleMessage&&<p role="status">{sampleMessage}</p>}
      {!demo&&<button disabled={busy} onClick={()=>{setBusy(true);setToneMessage("");void request("voice/asset/tone",{}).then(()=>setToneMessage("Tone sent to Luma’s speaker. Did you hear it?")).catch(error=>setToneMessage(error instanceof Error?error.message:"Speaker test failed.")).finally(()=>setBusy(false));}}>Test speaker tone</button>}
      {toneMessage&&<p role="status">{toneMessage}</p>}
      {!demo&&<small>If the tone works but speech is silent, check the local voice model. If replies sound robotic, check whether “Last spoken reply” says original fallback voice. A sent tone still needs your listening confirmation.</small>}
      {voiceAsset?.phase==="failed"&&!demo&&<button disabled={busy} onClick={()=>act(async()=>{setVoiceAsset(await request("voice/asset/retry",{}));setMessage("Luma will retry the signed offline voice download.");})}>Retry voice download</button>}
      {voiceAsset?.phase!=="ready"&&<small>Voice commands remain available with the original local voice while this optional model is prepared. No speech is uploaded.</small>}
    </div>
    <div className="voice-hardware"><strong>ReSpeaker capture</strong><p>{hardware===undefined?"Checking the V1 sound card…":hardware.available?hardware.capture_on&&hardware.route_ready?"V1 sound card and mic input path detected.":"V1 sound card detected; capture path needs initialization.":"V1 sound card not detected. Check the HAT model and seating with power off; gain cannot fix a missing card."}</p>
      {hardware?.available&&<><label htmlFor="mic-capture-gain">Capture gain · {gain} / {hardware.max_gain}</label><input id="mic-capture-gain" type="range" min="0" max={hardware.max_gain} step="1" value={gain} disabled={busy} onChange={event=>setGain(Number(event.target.value))}/><button disabled={busy} onClick={()=>act(async()=>{if(demo){setMessage("Preview only. Gain was not changed.");return;}const next:MicHardware=await request("voice/hardware/gain",{gain});setHardware(next);setGain(next.gain);setMessage("Capture gain saved. Try the voice check again.");})}>Save capture gain</button></>}
      <button disabled={busy||demo} onClick={()=>act(async()=>{const next:MicHardware=await request("voice/hardware");setHardware(next);setGain(next.gain);})}>Recheck microphone hardware</button></div>
    <p className="setup-note">Check six phrases from your normal room distance. Luma can make up to three small capture-gain adjustments for clearly quiet or clipped speech, then saves that gain. It does not train a personal voice model. A meter stuck at zero means the microphone route needs diagnosis, not more gain.</p>
    <button disabled={busy || !enabled || status?.active} onClick={()=>act(async()=>{if(demo){setMessage("Preview only. The microphone check runs on your Pi.");return;}setStatus(await request("voice/calibration/start",{}));})}>Check my voice</button>
    {status && <div className="voice-calibration" role="region" aria-label="Microphone check status"><p>{status.completed} / {status.total} phrases checked</p>{status.phrase && <h2>“{status.phrase}”</h2>}{voiceDiagnostic&&<div className={`voice-diagnostic ${status.agent_available?"is-live":"is-waiting"}`} role="status"><strong>{voiceDiagnostic}</strong><div className="voice-meter" role="progressbar" aria-label="Live microphone level" aria-valuemin={0} aria-valuemax={100} aria-valuenow={signalPercent}><span style={{width:`${signalPercent}%`}}/></div><small>{status.agent_available?`Voice service: ${status.agent_phase}`:status.agent_error?"Voice startup diagnostic":"Waiting for local voice service"} · level meter is temporary and only active during this check</small></div>}{status.dropped_frames>0&&<p role="status">Microphone frames lost while listening: {status.dropped_frames}. If this count rises during the check, Luma will discard incomplete phrases rather than guess.</p>}{status.last_heard&&<p role="status">Luma heard: “{status.last_heard}” · {status.last_wake_detected?"Hey Luma recognized":"Wake phrase missed"} · {status.last_intent?`Matched ${status.last_intent.replaceAll('_',' ')}`:"No command matched"}</p>}<p>{status.message}</p>{status.active && <button disabled={busy} onClick={()=>act(async()=>setStatus(await request("voice/calibration/cancel",{})))}>Cancel check</button>}</div>}
    {message && <p role="status">{message}</p>}
    <form className="voice-phrase-preview" onSubmit={event=>{event.preventDefault();setPhraseError("");setPhrasePreview(undefined);if(demo){setPhraseError("Preview only. Try this on the Pi.");return;}void request('voice/phrase-preview',{text:phrase.trim()}).then(setPhrasePreview).catch(error=>setPhraseError(String(error instanceof Error?error.message:error)));}}>
      <strong>Try a phrase—without running it</strong>
      <p>The small neural phrase matcher runs entirely on this Pi. This checks typed text after recognition; it does not test microphone accuracy or change a setting.</p>
      <label htmlFor="luma-phrase-preview">What would you say after “Hey Luma”?</label>
      <div><input id="luma-phrase-preview" value={phrase} maxLength={160} onChange={event=>{setPhrase(event.target.value);setPhrasePreview(undefined);}}/><button type="submit" disabled={!phrase.trim()}>Check phrase</button></div>
      {phrasePreview&&<p role="status">{phrasePreview.understood?`Luma understands: ${phrasePreview.intent?.replaceAll('_',' ')??phrasePreview.command?.replaceAll('_',' ')}.`:"Luma would ask you to try a different phrase."} {phrasePreview.model_suggestion&&`Offline model suggests “${phrasePreview.model_suggestion.replaceAll('_',' ')}” (${Math.round((phrasePreview.model_confidence??0)*100)}%); the safe command parser makes the final decision.`} Nothing was executed.</p>}
      {phraseError&&<p role="status">{phraseError}</p>}
    </form>
    <details className="voice-library"><summary>Things you can ask</summary>
      <p className="setup-note">Start with “Hey Luma”. Recognition, answers and speech run locally—no AI tokens, subscription or cloud AI. Weather and Google Calendar still need internet to refresh; saved data works offline and is identified when out of date. Private answers require your nearby phone or PIN. This is a phrase library, not an open-ended chatbot.</p>
      {!library.length && <p className="setup-note">The command list will be available when the local service reconnects.</p>}
      {library.map(group=><section key={group.title}><h3>{group.title}</h3><ul>{group.examples.map(phrase=><li key={phrase}>“{phrase}”</li>)}</ul></section>)}
      <p className="setup-note">“Show weather” or “show calendar” changes the screen. Asking a question speaks an answer without waking or unlocking the display. Calendar summaries read up to three titles, then tell you how many more there are. Speech uses the Pi’s local voice, not Siri.</p>
    </details>
  </section>;
}
