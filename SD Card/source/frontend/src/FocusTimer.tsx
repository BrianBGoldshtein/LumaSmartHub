import {useEffect,useMemo,useRef,useState} from 'react';
import {Timer,Pause,Play,X} from 'lucide-react';
import {TouchField,TouchInputProvider} from './TouchField';
import {idleTimer,previewTimerCommand,timerRemaining,timerText,type TimerState} from './timerState';
import type {Snapshot} from './types';
import './features.css';

function useRemaining(timer:TimerState){
  const anchor=useMemo(()=>performance.now(),[timer]);
  const [clock,setClock]=useState(performance.now());
  useEffect(()=>{setClock(performance.now());if(timer.status!=='running')return;const handle=setInterval(()=>setClock(performance.now()),250);return()=>clearInterval(handle);},[timer]);
  return timerRemaining(timer,(clock-anchor)/1000);
}
export function TimerBadge({timer,onOpen}:{timer:TimerState;onOpen:()=>void}){
  const left=useRemaining(timer);
  return <button className="timer-badge" aria-label="Open timer" onClick={event=>{event.stopPropagation();onOpen();}}><Timer/><strong>{timer.status==='complete'?'Done':timer.status==='awaiting_time'?'Check clock':timerText(left)}</strong>{timer.status==='paused' && <Pause aria-label="Paused"/>}</button>;
}
export function TimerPanel({snapshot,demo,onUpdate,onClose}:{snapshot:Snapshot;demo:boolean;onUpdate:(snapshot:Snapshot)=>void;onClose:()=>void}){
  const timer=snapshot.timer || idleTimer,remaining=useRemaining(timer);
  const [minutes,setMinutes]=useState('25'),[label,setLabel]=useState('');
  const [pending,setPending]=useState<{minutes:number;label:string;replace_id:string}|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const panel=useRef<HTMLElement>(null);
  useEffect(()=>{const previous=document.activeElement as HTMLElement|null;panel.current?.querySelector<HTMLButtonElement>('button')?.focus();return()=>previous?.focus();},[]);
  useEffect(()=>{setLabel('');},[snapshot.privacy_redacted]);
  const active=['running','paused','awaiting_time'].includes(timer.status);
  useEffect(()=>{setPending(null);},[timer.id]);
  async function run(name:string,value?:unknown){
    setError('');setBusy(true);
    try{
      if(demo){onUpdate({...snapshot,timer:previewTimerCommand(timer,name,value,remaining,crypto.randomUUID())});}
      else{
        const response=await fetch('/api/v1/commands',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name,value,source:'touchscreen'})});
        const data=await response.json();
        if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Timer unavailable. Try again.');
        onUpdate(data.snapshot);
        if(!data.result.accepted)throw Error(data.result.message);
      }
      setPending(null);
      setLabel('');
    }catch(e){setError(e instanceof Error?e.message:'Timer unavailable.');}finally{setBusy(false);}
  }
  function start(amount:number,title:string){
    if(!Number.isInteger(amount) || amount<1 || amount>240){setError('Choose 1–240 whole minutes.');return;}
    const value={minutes:amount,label:title.trim() || 'Timer'};
    if(active && timer.id)setPending({...value,replace_id:timer.id});else void run('start_timer',value);
  }
  return <TouchInputProvider><div className="feature-shade" onClick={event=>event.stopPropagation()}><section ref={panel} className="feature-panel device-setup" role="dialog" aria-modal="true" aria-label="Timer controls" onKeyDown={event=>{
    if(event.key==='Escape' && !busy){event.preventDefault();onClose();}
    if(event.key==='Tab'){
      const fields=[...event.currentTarget.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),summary,[tabindex="0"]')].filter(item=>item.getClientRects().length);
      const first=fields[0],last=fields[fields.length-1];
      if(event.shiftKey && document.activeElement===first){event.preventDefault();last?.focus();}
      else if(!event.shiftKey && document.activeElement===last){event.preventDefault();first?.focus();}
    }
  }}>
    <header><h2><Timer/>Timer</h2><button className="feature-close" onClick={onClose} disabled={busy} aria-label="Close timer"><X/></button></header>
    <div className="timer-reading"><strong>{timer.status==='idle'?'Ready':timer.status==='complete'?'Time’s up':timerText(remaining)}</strong>{timer.status!=='idle' && <span>{snapshot.privacy_redacted?'Timer':timer.label}{timer.status==='paused'?' · Paused':timer.status==='awaiting_time'?' · Waiting for clock':''}</span>}</div>
    {timer.note && <p className="feature-note" role="status">{timer.note}</p>}
    {error && <p role="alert" className="feature-error">{error}</p>}
    {active && <div className="feature-actions">{timer.status==='paused'?<button disabled={busy} onClick={()=>void run('resume_timer')}><Play/>Resume</button>:<button disabled={busy} onClick={()=>void run('pause_timer')}><Pause/>Pause</button>}<button disabled={busy} onClick={()=>void run('cancel_timer')}>Cancel timer</button></div>}
    {timer.status==='complete' && <button disabled={busy} onClick={()=>void run('dismiss_timer')}>Dismiss</button>}
    <div className="timer-presets"><button disabled={busy} onClick={()=>start(snapshot.settings.timer_focus_minutes ?? 25,'Focus')}>Focus <strong>{snapshot.settings.timer_focus_minutes ?? 25}<small> min</small></strong></button><button disabled={busy} onClick={()=>start(snapshot.settings.timer_break_minutes ?? 5,'Break')}>Break <strong>{snapshot.settings.timer_break_minutes ?? 5}<small> min</small></strong></button></div>
    <details><summary>Custom timer</summary><form onSubmit={event=>{event.preventDefault();start(Number(minutes),label);}}><TouchField label="Minutes · 1 to 240" value={minutes} onChange={setMinutes} mode="digits" maxLength={3} required disabled={busy}/><TouchField label="Label · optional, hidden in private standby" value={label} onChange={setLabel} maxLength={40} disabled={busy}/><button disabled={busy}>Start timer</button></form></details>
    {pending && <div className="feature-confirm" role="alert"><strong>Replace the current timer?</strong><p>Start {pending.minutes} minutes instead. The current countdown will be lost.</p><button disabled={busy} onClick={()=>void run('start_timer',pending)}>Replace timer</button><button disabled={busy} onClick={()=>setPending(null)}>Keep current timer</button></div>}
    {demo && <p className="feature-note">Preview timer only · no device changes or chime.</p>}
  </section></div></TouchInputProvider>;
}
export function TimerComplete({timer,privateMode,onOpen}:{timer:TimerState;privateMode:boolean;onOpen:()=>void}){
  return <aside className="feature-notice" role="status" onClick={event=>event.stopPropagation()}><Timer/><div><strong>Time’s up</strong><span>{privateMode?'Timer':timer.label}</span></div><button onClick={onOpen}>Open timer</button></aside>;
}
