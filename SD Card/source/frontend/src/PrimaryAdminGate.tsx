import {useEffect,useRef,useState,type ReactNode} from 'react';
import {LockKeyhole,ShieldCheck} from 'lucide-react';
import {TouchField,TouchInputProvider} from './TouchField';
import {ADMIN_NEEDED,adminAccess,type AdminStatus} from './adminState';
import {setupTheme,setupLink} from './setupTheme';
import type {Theme} from './types';
import './primaryAdmin.css';

export function PrimaryAdminGate({children,demo=false,inline=false,theme=setupTheme(new URLSearchParams(location.search).get('theme'))}:
  {children:ReactNode;demo?:boolean;inline?:boolean;theme?:Theme}){
  const [status,setStatus]=useState<AdminStatus|null>(null),[checking,setChecking]=useState(!demo);
  const [confirm,setConfirm]=useState(false),[pin,setPin]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const revision=useRef(0);
  useEffect(()=>{
    if(demo)return;let live=true,inFlight=false;
    const poll=async()=>{
      if(inFlight)return;inFlight=true;
      const current=revision.current,controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),5000);
      try{const response=await fetch('/api/v1/admin/status',{cache:'no-store',signal:controller.signal});
        if(!response.ok)throw Error();const value=await response.json();
        if(live&&current===revision.current){setStatus(value);setChecking(false);}}
      catch{if(live&&current===revision.current){setStatus(null);setChecking(false);setMessage('Could not check primary access. Keep the hub connected and retry.');}}
      finally{clearTimeout(timeout);inFlight=false;}
    };
    const needed=(event:Event)=>{const fresh=(event as CustomEvent<{fresh:boolean}>).detail?.fresh;
      revision.current++;
      if(fresh)setConfirm(true);else setStatus(previous=>previous?{...previous,unlocked:false}:null);
      setPin('');setMessage(fresh?'Confirm your PIN, then review and try the action again.':'Primary access expired. Enter your PIN again.');};
    void poll();const timer=setInterval(()=>void poll(),5000);
    window.addEventListener(ADMIN_NEEDED,needed);
    return()=>{live=false;clearInterval(timer);window.removeEventListener(ADMIN_NEEDED,needed);};
  },[demo]);
  if(demo)return <>{children}</>;
  const access=adminAccess(status),allowed=access!=='locked';
  async function unlock(){
    const entered=pin;revision.current++;setPin('');setBusy(true);setMessage('');
    try{const response=await fetch(status?.configured===false?'/api/v1/security/pin':'/api/v1/admin/unlock',{
      method:'POST',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({pin:entered})});
      const value=await response.json();
      if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'Could not unlock primary settings.');
      setStatus({configured:true,unlocked:true,bootstrap:false,expires_in_seconds:300});setConfirm(false);}
    catch(error){setMessage(error instanceof Error?error.message:'Try again.');}
    finally{setBusy(false);}
  }
  const prompt=<TouchInputProvider><section className="primary-admin-prompt">
    <LockKeyhole aria-hidden="true"/><h1>{confirm?'Confirm primary PIN':'Primary settings'}</h1>
    <p>{status?.configured===false?'Choose the primary PIN before managing this hub.':'Only the primary user manages hub-wide settings. Timers remain available to everyone.'}</p>
    <form onSubmit={event=>{event.preventDefault();void unlock();}}>
      <TouchField label={status?.configured===false?'New primary PIN':'Primary PIN'} mode="digits" secret required minLength={4} maxLength={8} pattern="[0-9]{4,8}" value={pin} onChange={setPin} disabled={busy||checking}/>
      <button disabled={busy||checking}>{checking?'Checking access…':busy?'Checking PIN…':status?.configured===false?'Set primary PIN':'Unlock settings'}</button>
      {confirm&&allowed&&<button type="button" onClick={()=>{setConfirm(false);setPin('');}}>Cancel</button>}
    </form>{message&&<p role="status">{message}</p>}
    {!inline&&<a href={setupLink(false,theme)}>Back to dashboard</a>}
  </section></TouchInputProvider>;
  if(!allowed)return inline?prompt:<div className={`app theme-${theme} setup-page`}><main className="setup-content device-setup">{prompt}</main></div>;
  const unlocked=<><div className={`primary-admin-bar ${inline?'inline':''}`}>
    <ShieldCheck aria-hidden="true"/><span>{access==='bootstrap'?'Initial setup':'Primary settings unlocked · 5 minutes'}</span>
    {access==='unlock'&&<><button onClick={()=>{setConfirm(true);setPin('');setMessage('');}}>Confirm PIN</button>
      <button onClick={()=>{revision.current++;setPin('');setConfirm(false);setStatus(previous=>previous?{...previous,unlocked:false}:null);
        void fetch('/api/v1/admin/lock',{method:'POST',cache:'no-store'}).catch(()=>setMessage('Access will expire automatically.'));}}>Lock</button></>}
  </div>{children}{confirm&&<div className="primary-admin-shade" role="dialog" aria-modal="true" aria-label="Confirm primary PIN">{prompt}</div>}</>;
  return inline?unlocked:<div className={`app theme-${theme} primary-admin-shell`}>{unlocked}</div>;
}
