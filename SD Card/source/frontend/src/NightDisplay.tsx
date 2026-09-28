import {useEffect,useLayoutEffect,useMemo,useState} from 'react';
import type {Snapshot} from './types';
import {displayFilter} from './displayState';
import './nightDisplay.css';

export function useDisplayFilter(snapshot:Snapshot|null,demo:boolean){
  const display=snapshot?.display;
  const anchor=useMemo(()=>performance.now(),[display]);
  const [clock,setClock]=useState(performance.now());
  useEffect(()=>{setClock(performance.now());if(display?.mode!=='waking')return;
    const timer=setInterval(()=>setClock(performance.now()),40);return()=>clearInterval(timer);
  },[display]);
  const revision=display?.handoff.revision,needsFrame=display?.handoff.needs_frame;
  const filter=!snapshot && !demo?0:displayFilter(display,clock-anchor);
  // Until the first authoritative snapshot, stay black. Body dimming covers
  // in-app setup/keyboards without creating a fixed-position container;
  // native helper windows are separately closed by the desktop bridge.
  useLayoutEffect(()=>{document.body.style.opacity=String(filter);return()=>{document.body.style.removeProperty('opacity');};},[filter]);
  useEffect(()=>{
    if(demo || !revision || !needsFrame)return;
    let controller:AbortController|null=null,second=0,retry=0,timeout=0,stopped=false;
    // A matching rendered dimmer precedes any physical increase. No timeout
    // grants readiness; failures retry, while a suspended renderer stays safe.
    const acknowledge=()=>{second=requestAnimationFrame(()=>{second=requestAnimationFrame(async()=>{
      controller=new AbortController();timeout=window.setTimeout(()=>controller?.abort(),5000);
      try{const response=await fetch('/api/v1/display/frame',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({revision}),signal:controller.signal});if(!response.ok || !(await response.json()).accepted)throw Error();}
      catch{if(!stopped)retry=window.setTimeout(acknowledge,1000);}
      finally{clearTimeout(timeout);}
    });});};
    acknowledge();
    return()=>{stopped=true;cancelAnimationFrame(second);clearTimeout(retry);clearTimeout(timeout);controller?.abort();};
  },[demo,revision,needsFrame]);
  return filter;
}

export function NightDisplay({snapshot,onWake}:{snapshot:Snapshot;onWake:()=>void}){
  const anchor=useMemo(()=>performance.now(),[snapshot.server_time]);
  const [clock,setClock]=useState(performance.now());
  useEffect(()=>{const timer=setInterval(()=>setClock(performance.now()),1000);return()=>clearInterval(timer);},[]);
  const time=new Date(Date.parse(snapshot.server_time)+Math.max(0,clock-anchor));
  const reading=snapshot.display?.awaiting_clock?'—:—':new Intl.DateTimeFormat('en-GB',{hour:'2-digit',minute:'2-digit',hourCycle:'h23',timeZone:snapshot.settings.timezone}).format(time);
  return <button className="night-clock" aria-label={snapshot.display?.awaiting_clock?'Waiting for clock. Tap to wake Luma':'Tap to wake Luma for five minutes'} onClick={onWake}><span>{reading}</span></button>;
}
