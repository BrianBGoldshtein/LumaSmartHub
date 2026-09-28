import {useEffect,useMemo,useRef,useState,type CSSProperties} from 'react';
import {Footprints,X} from 'lucide-react';
import type {Snapshot} from './types';
import {departureMinutes,departureText,type Departure} from './departureState';
import {TouchField,TouchInputProvider} from './TouchField';

function useDepartureText(reminder:Departure,serverTime:string){
  const anchor=useMemo(()=>performance.now(),[serverTime]);
  const [clock,setClock]=useState(performance.now());
  useEffect(()=>{setClock(performance.now());const id=setInterval(()=>setClock(performance.now()),1000);return()=>clearInterval(id);},[serverTime]);
  return departureText(reminder,serverTime,clock-anchor);
}
export function DepartureNotice({reminder,serverTime,onOpen}:{reminder:Departure;serverTime:string;onOpen:()=>void}){
  const text=useDepartureText(reminder,serverTime);
  if(!text)return null;
  return <aside className="feature-notice departure-notice" role="status" style={{'--event-color':reminder.color||'var(--accent)'} as CSSProperties} onClick={e=>e.stopPropagation()}><Footprints/><div><strong>{text}</strong><span>{reminder.title}</span></div><button onClick={onOpen}>Details</button></aside>;
}
export function DeparturePanel({snapshot,demo,onUpdate,onClose}:{snapshot:Snapshot;demo:boolean;onUpdate:(value:Snapshot)=>void;onClose:()=>void}){
  const reminder=snapshot.departure!;
  const text=useDepartureText(reminder,snapshot.server_time);
  const [prep,setPrep]=useState(String(reminder.prep_minutes)),[travel,setTravel]=useState(String(reminder.travel_minutes));
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const panel=useRef<HTMLElement>(null),pending=useRef<AbortController|null>(null);
  useEffect(()=>{const previous=document.activeElement as HTMLElement|null;panel.current?.querySelector<HTMLButtonElement>('button')?.focus();return()=>{pending.current?.abort();previous?.focus();};},[]);
  useEffect(()=>{if(!text)onClose();},[text,onClose]);
  async function act(action:'snooze'|'dismiss'|'override'){
    let minutes={};
    try{if(action==='override')minutes={prep:departureMinutes(prep),travel:departureMinutes(travel)};}catch(e){setError((e as Error).message);return;}
    setBusy(true);setError('');const controller=new AbortController();pending.current=controller;
    try{
      if(demo){
        const next=action==='override'?{...reminder,prep_minutes:Number(prep),travel_minutes:Number(travel),depart_at:new Date(Date.parse(reminder.start)-(Number(prep)+Number(travel))*60000).toISOString()}:null;
        onUpdate({...snapshot,departure:next});
      }else{
        const response=await fetch('/api/v1/departures/action',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key:reminder.key,action,...minutes}),signal:controller.signal});
        const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Could not update the reminder. Refresh your calendar.');
        if(!controller.signal.aborted)onUpdate(data);
      }
      if(!controller.signal.aborted)onClose();
    }catch(e){if(!controller.signal.aborted)setError((e as Error).message);}finally{if(!controller.signal.aborted)setBusy(false);}
  }
  return <TouchInputProvider><div className="feature-shade" onClick={e=>e.stopPropagation()}><section ref={panel} className="feature-panel device-setup" role="dialog" aria-modal="true" aria-label="Departure reminder" onKeyDown={event=>{
    if(event.key==='Escape' && !busy)onClose();
    if(event.key==='Tab'){
      const items=[...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),summary,[tabindex="0"]')].filter(item=>item.getClientRects().length);
      if(event.shiftKey && document.activeElement===items[0]){event.preventDefault();items.at(-1)?.focus();}
      else if(!event.shiftKey && document.activeElement===items.at(-1)){event.preventDefault();items[0]?.focus();}
    }
  }}><header><h2><Footprints/>Leave soon</h2><button className="feature-close" onClick={onClose} disabled={busy} aria-label="Close reminder"><X/></button></header>
    <div className="departure-reading"><strong>{text}</strong><span>{reminder.title}</span></div>
    <p className="feature-note">Starts {new Intl.DateTimeFormat('en-US',{hour:'numeric',minute:'2-digit',timeZone:snapshot.settings.timezone}).format(new Date(reminder.start))} · {reminder.prep_minutes} min preparation + {reminder.travel_minutes} min travel</p>
    <div className="feature-actions"><button disabled={busy} onClick={()=>void act('snooze')}>Snooze 5 min</button><button disabled={busy} onClick={()=>void act('dismiss')}>Dismiss this event</button></div>
    <details><summary>Adjust this event</summary><form onSubmit={e=>{e.preventDefault();void act('override');}}><div className="setup-grid"><TouchField label="Preparation · minutes" mode="digits" maxLength={3} value={prep} onChange={setPrep} disabled={busy}/><TouchField label="Travel · minutes" mode="digits" maxLength={3} value={travel} onChange={setTravel} disabled={busy}/></div><button disabled={busy}>Save for this event</button></form></details>
    <p className="feature-note">Your time estimates, not live directions. Changes stay on Luma; your Google event is unchanged.</p>
    {demo && <p className="feature-note">Preview only. Snooze hides this sample; reload to try again.</p>}
    {error && <p className="feature-error" role="alert">{error}</p>}
  </section></div></TouchInputProvider>;
}
