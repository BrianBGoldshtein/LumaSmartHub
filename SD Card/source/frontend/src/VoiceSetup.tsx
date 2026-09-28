import {useEffect,useState} from "react";
import {useSetupActivity} from "./setupActivity";
type Calibration={active:boolean;passed:boolean;phrase:string|null;completed:number;total:number;message:string;attempts:number};
type VoiceGroup={title:string;examples:string[]};
const previewLibrary:VoiceGroup[]=[{title:'Weather',examples:['What’s the weather today?','Will it rain today?','What is the temperature?']},{title:'Calendar',examples:['When is my next event?','What’s on my calendar today?','What’s on my calendar tomorrow?','What is happening now?']},{title:'Tasks & time',examples:['What are my tasks today?','What tasks are due today?','What time is it?','What day is it?','How much time is left on my timer?']},{title:'Everyday controls',examples:['Start focus timer','Pause timer','Good morning','Good night','Screen off','Wake screen','Change brightness','Change theme to arcade','Hide my calendar','What can I say?']}];
async function request(path:string,body?:unknown){
  const response=await fetch(`/api/v1/${path}`,{method:body===undefined?"GET":path==="settings"?"PATCH":"POST",headers:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw Error(typeof data.detail==="string"?data.detail:"Voice check unavailable.");return data;
}
export function VoiceSetup({demo}:{demo:boolean}){
  const [enabled,setEnabled]=useState<boolean|null>(demo?true:null),[status,setStatus]=useState<Calibration>(),[message,setMessage]=useState(""),[busy,setBusy]=useState(false);
  const [library,setLibrary]=useState<VoiceGroup[]>(demo?previewLibrary:[]);
  useEffect(()=>{if(!demo)request('voice/library').then(data=>setLibrary(data.groups)).catch(()=>setLibrary([]));},[demo]);
  useSetupActivity(busy || !!status?.active);
  useEffect(()=>{if(!demo)request("settings").then(data=>setEnabled(data.voice_enabled)).catch(()=>setMessage("Device connection unavailable."));},[demo]);
  useEffect(()=>{
    if(demo || !status?.active)return;
    const timer=window.setInterval(()=>request("voice/calibration").then(setStatus).catch(()=>setMessage("Voice check connection interrupted.")),1000);
    return ()=>clearInterval(timer);
  },[demo,status?.active]);
  async function act(fn:()=>Promise<void>){setBusy(true);setMessage("");try{await fn();}catch(error){setMessage(error instanceof Error?error.message:"Voice check unavailable.");}finally{setBusy(false);}}
  return <section><h2>Hey Luma</h2><p>Your local voice controls are on by default. Say “Hey Luma” followed by a command. Audio stays in memory on this Pi; it is not saved or uploaded. You can turn the microphone off below; that choice survives restarts.</p>
    <button disabled={busy || enabled===null} onClick={()=>act(async()=>{if(!demo)await request("settings",{voice_enabled:!enabled});setEnabled(!enabled);setStatus(undefined);})}>{enabled===null?"Loading microphone setting…":enabled?"Turn microphone off":"Enable local voice"}</button>
    <p className="setup-note">Check three phrases from your normal room distance. This tests recognition and signal level—it does not train a personal voice model. Test commands do not change your settings. If the signal is too quiet or clips, adjust microphone capture gain using the audio setup guide.</p>
    <button disabled={busy || !enabled || status?.active} onClick={()=>act(async()=>{if(demo){setMessage("Preview only. The microphone check runs on your Pi.");return;}setStatus(await request("voice/calibration/start",{}));})}>Check my voice</button>
    {status && <div role="status"><p>{status.completed} / {status.total} phrases checked</p>{status.phrase && <h2>“{status.phrase}”</h2>}<p>{status.message}</p>{status.active && <button disabled={busy} onClick={()=>act(async()=>setStatus(await request("voice/calibration/cancel",{})))}>Cancel check</button>}</div>}
    {message && <p role="status">{message}</p>}
    <details className="voice-library"><summary>Things you can ask</summary>
      <p className="setup-note">Start with “Hey Luma”. Recognition, answers and speech run locally—no AI tokens, subscription or cloud AI. Weather and Google Calendar still need internet to refresh; saved data works offline and is identified when out of date. Private answers require your nearby phone or PIN. This is a phrase library, not an open-ended chatbot.</p>
      {!library.length && <p className="setup-note">The command list will be available when the local service reconnects.</p>}
      {library.map(group=><section key={group.title}><h3>{group.title}</h3><ul>{group.examples.map(phrase=><li key={phrase}>“{phrase}”</li>)}</ul></section>)}
      <p className="setup-note">“Show weather” or “show calendar” changes the screen. Asking a question speaks an answer without waking or unlocking the display. Calendar summaries read up to three titles, then tell you how many more there are. Speech uses the Pi’s local voice, not Siri.</p>
    </details>
  </section>;
}
