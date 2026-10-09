import {useEffect,useRef,useState} from 'react';
import {Timer,X} from 'lucide-react';
import {TimerPanel} from './FocusTimer';
import {idleTimer,type TimerState} from './timerState';
import type {Snapshot} from './types';

const prefix='/api/v1/user-self/wall/';
export async function wallRequest<T>(path:string,method='GET',body?:unknown,signal?:AbortSignal):Promise<T>{
  const timeout=AbortSignal.timeout(45000);
  const response=await fetch(prefix+path,{method,cache:'no-store',signal:signal?AbortSignal.any([signal,timeout]):timeout,
    headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const packet=await response.json();
  if(!response.ok)throw Error(response.status===403?'Personal access ended. Reconnect your iPhone or ask the primary user to reopen your setup.':
    response.status===409?'This changed. Refresh before trying again.':'Your request could not finish. Refresh before retrying.');
  return packet as T;
}

export function useWallAccess(snapshot:Snapshot|null,demo:boolean){
  const [approved,setApproved]=useState<string[]>([]);
  const present=(snapshot?.users??[]).map(user=>user.profile_id);
  const key=JSON.stringify(present),day=!snapshot?.display||snapshot.display.mode==='day';
  useEffect(()=>{
    let stopped=false,handle:ReturnType<typeof setTimeout>;
    const controller=new AbortController();
    setApproved(previous=>day&&!demo?previous.filter(uid=>(JSON.parse(key) as string[]).includes(uid)):[]);
    async function poll(){
      try{
        const value=await wallRequest<{users:{profile_id:string}[]}>('access','GET',undefined,controller.signal);
        if(!stopped)setApproved(value.users.map(user=>user.profile_id));
      }catch{if(!stopped)setApproved([]);}
      if(!stopped)handle=setTimeout(()=>void poll(),2000);
    }
    if(!demo&&day&&present.length)void poll();
    return()=>{stopped=true;controller.abort();clearTimeout(handle);};
  },[key,day,demo]);
  return day?approved.filter(uid=>present.includes(uid)):[];
}

export function PersonalWallTimer({snapshot,profileId,allowed,onClose}:{snapshot:Snapshot;profileId:string;allowed:boolean;onClose:()=>void}){
  const user=snapshot.users?.find(row=>row.profile_id===profileId);
  const [timer,setTimer]=useState<TimerState|null>(null),[error,setError]=useState('');
  const working=useRef(false),active=useRef(true),revision=useRef(0),requests=useRef(new AbortController());
  useEffect(()=>{
    let handle:ReturnType<typeof setTimeout>;active.current=true;revision.current++;
    const controller=new AbortController();requests.current=controller;
    async function poll(){
      const serial=revision.current;
      if(!working.current){
        try{
          const value=await wallRequest<{timer:TimerState}>('preview?profile_id='+encodeURIComponent(profileId),'GET',undefined,controller.signal);
          if(active.current&&serial===revision.current){setTimer(value.timer);setError('');}
        }catch{if(active.current&&serial===revision.current){setTimer(null);setError('Personal timer unavailable. Reconnect your authorized iPhone.');}}
      }
      if(active.current)handle=setTimeout(()=>void poll(),2000);
    }
    setTimer(null);setError('');if(allowed)void poll();
    return()=>{active.current=false;controller.abort();clearTimeout(handle);};
  },[profileId,allowed]);
  if(!user)return null;
  if(!allowed||!timer)return <div className="feature-shade" onClick={event=>event.stopPropagation()}><section className="feature-panel device-setup" role="dialog" aria-modal="true" aria-label={`${user.nickname}’s timer`}>
    <header><h2>{user.nickname}’s timer</h2><button onClick={onClose} className="feature-close" aria-label="Close personal timer"><X/></button></header>
    <p role="status">{!allowed?'Ask the primary user to open your personal setup once in Settings → Users. Your phone must be authorized. Room timers always work without a PIN.':error||'Opening your timer…'}</p>
  </section></div>;
  const privateSnapshot={...snapshot,privacy_redacted:false,timer:timer??idleTimer};
  return <TimerPanel snapshot={privateSnapshot} demo={false} onClose={onClose}
    onUpdate={next=>{if(active.current)setTimer(next.timer??idleTimer);}}
    controller={{title:`${user.nickname}’s timer`,send:async(name,value)=>{
      working.current=true;revision.current++;
      try{
        const packet=await wallRequest<{result:{accepted:boolean;message:string};preview:{timer:TimerState}}>('timer','POST',
          {profile_id:profileId,name,...(value===undefined?{}:{value})},requests.current.signal);
        if(!active.current)throw Error('Personal controls closed.');
        return {...packet.result,timer:packet.preview.timer};
      }finally{working.current=false;}
    }}}/>;
}

export function PersonalTimerComplete({snapshot,onOpen}:{snapshot:Snapshot;onOpen:(uid:string)=>void}){
  const complete=snapshot.personal_timers?.filter(timer=>timer.status==='complete')??[];
  if(!complete.length)return null;
  const available=complete.find(timer=>snapshot.users?.some(user=>user.profile_id===timer.profile_id));
  const label=complete.length>1?`${complete.length} personal timers finished`:
    !snapshot.privacy_redacted&&complete[0].owner_present?`${complete[0].owner} · ${complete[0].label}`:'Personal timer finished';
  return <aside className="feature-notice" role="status" onClick={event=>event.stopPropagation()}><Timer/>
    <div><strong>Time’s up</strong><span>{label}</span></div>
    {available&&<button onClick={()=>onOpen(available.profile_id)}>Open {available.owner}’s timer</button>}
  </aside>;
}
