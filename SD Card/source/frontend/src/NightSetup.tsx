import {useContext,useEffect,useState} from 'react';
import {Moon} from 'lucide-react';
import {SetupActivity} from './setupActivity';
import {TouchField} from './TouchField';

export function NightSetup({demo,onDirty,onBusy,onSaved}:{demo:boolean;onDirty:(value:boolean)=>void;onBusy:(value:boolean)=>void;onSaved?:()=>void}){
  const [enabled,setEnabled]=useState(true),[brightness,setBrightness]=useState('5'),[baseline,setBaseline]=useState(''),[ready,setReady]=useState(demo),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[retry,setRetry]=useState(0);
  const activity=useContext(SetupActivity),selection=JSON.stringify([enabled,brightness]);
  useEffect(()=>{onDirty(Boolean(baseline)&&baseline!==selection);},[baseline,selection,onDirty]);
  useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
  useEffect(()=>{
    if(demo){setBaseline(JSON.stringify([true,'5']));return;}
    const controller=new AbortController();
    fetch('/api/v1/settings',{signal:controller.signal}).then(async response=>{if(!response.ok)throw Error();return response.json();}).then(data=>{
      const clock=data.night_clock_enabled!==false,value=String(data.night_brightness??5);setEnabled(clock);setBrightness(value);setBaseline(JSON.stringify([clock,value]));setReady(true);
    }).catch(()=>{if(!controller.signal.aborted)setMessage('Could not load saved night preferences.');});
    return()=>controller.abort();
  },[demo,retry]);
  async function save(){
    if(!/^\d{1,3}$/.test(brightness) || Number(brightness)>100){setMessage('Choose whole percent from 0 to 100.');return;}
    setBusy(true);setMessage('');
    try{
      if(!demo){const response=await fetch('/api/v1/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({night_clock_enabled:enabled,night_brightness:Number(brightness)})});if(!response.ok)throw Error();}
      setBaseline(selection);setMessage(demo?'Preview checked — no device changes.':'Night preferences saved.');onSaved?.();
    }catch{setMessage('Could not save night preferences. Try again.');}finally{setBusy(false);}
  }
  if(!ready)return <><p role="status">{message||'Loading night preferences…'}</p>{message && <button onClick={()=>{setMessage('');setRetry(value=>value+1);}}>Retry</button>}</>;
  return <><h2><Moon/>Night & wake</h2><p>A quiet clock. A gradual morning.</p><form onSubmit={event=>{event.preventDefault();void save();}}>
    <label className="extras-toggle"><input type="checkbox" checked={enabled} disabled={busy} onChange={event=>{activity.edited();setEnabled(event.target.checked);}}/><span>Show a dim clock during sleep</span></label>
    <p className="setup-note">{enabled?'Only hours and minutes, on black. No private details or alerts.':'Turn the screen off during sleep instead.'} Choose your sleep calendar in Google Calendar setup; daily timed events named “Sleep” set the hours. “Good night” also starts night mode.</p>
    <TouchField label="Night brightness · %" value={brightness} onChange={value=>{activity.edited();setBrightness(value);}} mode="digits" maxLength={3} disabled={busy}/>
    <p className="setup-note">Night uses an extra-dark software curve on top of panel dimming: the saved 5% setting is now barely visible in a dark room. Daytime brightness stays separate. Zero hides the clock; tap the screen or say “Hey Luma, wake screen” to wake temporarily.</p>
    <div className="night-timing"><p><strong>Scheduled wake · 5 minutes</strong><br/>Starts when the Sleep event ends, never before.</p><p><strong>“Good morning” · 20 seconds</strong><br/>Overrides sleep from the current brightness.</p></div>
    <details><summary>Recovery & display control</summary><p className="setup-note">Touch wake lasts five minutes during a sleep interval. Screen off stays off until you wake it. Manual daytime brightness cancels a wake ramp. Scheduled mornings are silent.</p><p className="setup-note">Night preferences survive power loss. Before clock sync, a configured hub stays dark; explicit wake still works. Initial network setup remains available offline.</p><p className="setup-note">Panel brightness is verified where DDC is supported, with software dimming otherwise. Software dimming cannot remove an LCD’s backlight glow. Actual power-off/wake and brightness still need the assembled-panel check.</p></details>
    <button disabled={busy}>{busy?'Saving…':'Save night preferences'}</button>
  </form>{message && <p className="setup-message" role="status">{message}</p>}</>;
}
