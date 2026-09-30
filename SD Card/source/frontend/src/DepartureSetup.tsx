import {useContext,useEffect,useState} from 'react';
import {Footprints} from 'lucide-react';
import {TouchField} from './TouchField';
import {SetupActivity} from './setupActivity';
import {departurePreferences,departurePatch,type DeparturePreferences} from './departureState';

type Calendar={id:string;summary:string;background_color?:string};
async function api(path:string,method='GET',body?:unknown,signal?:AbortSignal){
  const response=await fetch(`/api/v1/${path}`,{method,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body),signal});
  if(!response.ok)throw Error('Could not reach Luma or Google. Your saved choices are unchanged.');
  return response.json();
}
export function DepartureSetup({demo,onDirty,onBusy,onSaved}:{demo:boolean;onDirty:(dirty:boolean)=>void;onBusy:(busy:boolean)=>void;onSaved?:()=>void}){
  const [values,setValues]=useState(()=>departurePreferences()),[baseline,setBaseline]=useState(()=>departurePreferences());
  const [calendars,setCalendars]=useState<Calendar[]>([]),[ready,setReady]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[calendarNote,setCalendarNote]=useState(''),[retry,setRetry]=useState(0);
  const activity=useContext(SetupActivity);
  useEffect(()=>{onDirty(JSON.stringify(values)!==JSON.stringify(baseline));},[values,baseline,onDirty]);
  useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
  useEffect(()=>{
    const controller=new AbortController();
    async function load(){
      try{
        const saved=departurePreferences(demo?{}:await api('settings','GET',undefined,controller.signal));
        if(controller.signal.aborted)return;
        setValues(saved);setBaseline(saved);setReady(true);
        if(demo){setCalendars([{id:'work',summary:'Work',background_color:'#7986cb'},{id:'personal',summary:'Personal',background_color:'#33b679'}]);setCalendarNote('Sample calendars · no Google account connected.');return;}
        try{const items=await api('google/calendars','GET',undefined,controller.signal);if(!controller.signal.aborted){setCalendars(items);setCalendarNote('');}}
        catch{if(!controller.signal.aborted)setCalendarNote('Connect Google in Calendar setup to choose calendars. If already connected, check your network and reopen this extra. Saved selections are kept.');}
      }catch{if(!controller.signal.aborted)setMessage('Could not load saved preferences. Retry when Luma reconnects.');}
    }
    void load();return()=>controller.abort();
  },[demo,retry]);
  function edit<K extends keyof DeparturePreferences>(key:K,value:DeparturePreferences[K]){activity.edited();setValues(current=>({...current,[key]:value}));setMessage('');}
  async function save(){
    let patch;try{patch=departurePatch(values);}catch(e){setMessage((e as Error).message);return;}
    setBusy(true);setMessage('');
    try{
      if(!demo)await api('settings','PATCH',patch);
      setBaseline({...values});onSaved?.();
      if(demo)setMessage('Preview checked — no device changes.');
      else if(!values.departure_enabled)setMessage('Saved. Leave-soon reminders are off.');
      else{
        try{await api('google/sync','POST');setMessage('Saved and synced. Reminders appear near departure time while Luma is unlocked.');}
        catch{setMessage('Preferences saved. Calendar sync is unavailable; reminders wait for a fresh sync.');}
      }
    }catch{setMessage('Could not save preferences. Please try again.');}finally{setBusy(false);}
  }
  if(!ready)return <><p role="status">{message||'Loading leave-soon preferences…'}</p>{message && <button onClick={()=>{setMessage('');setRetry(value=>value+1);}}>Retry</button>}</>;
  const unavailable=values.departure_calendar_ids.filter(id=>!calendars.some(c=>c.id===id));
  return <><h2><Footprints/>Leave soon</h2><p>A quiet nudge before your next outing.</p><form onSubmit={e=>{e.preventDefault();void save();}}>
    <label className="extras-toggle"><input type="checkbox" checked={values.departure_enabled} disabled={busy} onChange={e=>edit('departure_enabled',e.target.checked)}/><span>Show leave-soon reminders</span></label>
    <p className="setup-note">Leaving countdowns automatically use eligible events from these calendars; no individual event selection needed. This is separate from your agenda and Important Dates. All-day, declined, cancelled, started and matching sleep events are excluded.</p>
    {calendarNote && <p className="setup-note">{calendarNote}</p>}
    <div className="calendar-choices">{calendars.map(calendar=><label key={calendar.id}><input type="checkbox" aria-label={`Departure calendar: ${calendar.summary}`} checked={values.departure_calendar_ids.includes(calendar.id)} disabled={busy} onChange={e=>edit('departure_calendar_ids',e.target.checked?[...values.departure_calendar_ids,calendar.id]:values.departure_calendar_ids.filter(id=>id!==calendar.id))}/><i style={{background:calendar.background_color||'var(--accent)'}}/><span>{calendar.summary}</span></label>)}</div>
    {unavailable.length>0 && <p className="setup-note">{unavailable.length} saved calendar selection(s) unavailable. Kept until you remove them. <button type="button" disabled={busy} onClick={()=>edit('departure_calendar_ids',values.departure_calendar_ids.filter(id=>!unavailable.includes(id)))}>Remove unavailable selections</button></p>}
    <div className="setup-grid"><TouchField label="Preparation · minutes" value={values.departure_prep_minutes} onChange={value=>edit('departure_prep_minutes',value)} mode="digits" maxLength={3} disabled={busy}/><TouchField label="Travel · minutes" value={values.departure_travel_minutes} onChange={value=>edit('departure_travel_minutes',value)} mode="digits" maxLength={3} disabled={busy}/></div>
    <p className="setup-note">Leave time = event start − preparation − travel. These are your estimates, not live traffic or GPS. Adjust individual events from their reminder.</p>
    <details><summary>Online events & privacy</summary><label className="extras-toggle"><input type="checkbox" checked={values.departure_include_virtual} disabled={busy} onChange={e=>edit('departure_include_virtual',e.target.checked)}/><span>Also remind me for online events</span></label><p className="setup-note">Recognized meeting links and online-only events are skipped by default. Hybrid events with a physical location stay included. Unknown link formats may still appear.</p><p className="setup-note">Private, silent reminders start 15 minutes before leave time. Snooze for five minutes or dismiss that occurrence. No Google edits or extra permissions. Stale calendars and private standby hide reminders.</p></details>
    <button disabled={busy}>{busy?'Saving…':'Save leave-soon preferences'}</button>
  </form>{message && <p className="setup-message" role="status">{message}</p>}</>;
}
