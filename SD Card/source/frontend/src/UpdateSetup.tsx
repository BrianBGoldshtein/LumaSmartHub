import {useEffect,useRef,useState} from 'react';
import {Check,CloudDownload,RefreshCw,ShieldCheck} from 'lucide-react';

type Status={current_version:string;state:'idle'|'installing'|'installed'|'failed';phase?:string;target_version?:string|null;message?:string;elapsed_seconds?:number};
type Candidate={state:'available'|'current';current_version:string;version?:string;release_notes?:string;published_at?:string;candidate_id?:string};

async function call<T>(path:string,method='GET',body?:unknown,timeoutMs=0):Promise<T>{
  const controller=new AbortController(),timeout=timeoutMs?setTimeout(()=>controller.abort(),timeoutMs):null;
  try{
    const response=await fetch(`/api/v1/updates/${path}`,{method,cache:'no-store',signal:controller.signal,headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await response.json().catch(()=>({}));
    if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Luma could not check for updates. Check Wi-Fi sign-in and retry.');
    return data as T;
  }finally{if(timeout)clearTimeout(timeout);}
}

export function UpdateSetup({demo=false}:{demo?:boolean}){
  const [status,setStatus]=useState<Status|null>(null),[candidate,setCandidate]=useState<Candidate|null>(null);
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[sending,setSending]=useState(false);
  const [networkGap,setNetworkGap]=useState(false),[clock,setClock]=useState(Date.now()),[lastStatusAt,setLastStatusAt]=useState(Date.now());
  const initiated=useRef<string|null>(null),reloading=useRef(false);
  useEffect(()=>{if(demo){setStatus(new URLSearchParams(location.search).get('fixture')==='updating'
      ?{current_version:'0.2.2',state:'installing',phase:'copying',target_version:'0.2.3',elapsed_seconds:84}
      :{current_version:'Preview',state:'idle'});return;}let live=true;
    let inFlight=false;
    async function poll(){if(inFlight)return;inFlight=true;
      try{const value=await call<Status>('status','GET',undefined,5000);if(live){setStatus(value);setLastStatusAt(Date.now());setNetworkGap(false);}}
      catch(error){if(live){setNetworkGap(true);setMessage(current=>current||(error as Error).message);}}
      finally{inFlight=false;}}
    void poll();const interval=setInterval(()=>void poll(),2000),ticker=setInterval(()=>setClock(Date.now()),1000);
    return()=>{live=false;clearInterval(interval);clearInterval(ticker);};
  },[demo]);
  useEffect(()=>{
    if(!status||!initiated.current)return;
    if(status.state==='failed'){setMessage(status.message||'The update failed. Check the active version before retrying.');initiated.current=null;}
    else if(status.state==='installed'&&status.current_version===initiated.current&&!reloading.current){
      reloading.current=true;setMessage(`Luma ${status.current_version} passed its health check. Reloading the dashboard…`);
      setCandidate(null);setTimeout(()=>location.reload(),2500);
    }
  },[status]);
  async function check(){setBusy(true);setMessage('');setCandidate(null);
    try{if(demo){setMessage('Preview only — no network request or installation.');return;}
      const result=await call<Candidate>('check','POST');setCandidate(result);
      setMessage(result.state==='current'?'Luma is up to date.':'A signed update is ready for review.');
    }catch(error){setMessage((error as Error).message);}finally{setBusy(false);}
  }
  async function install(){if(!candidate?.candidate_id||!candidate.version)return;setBusy(true);setSending(true);setMessage('Sending the reviewed update to Luma’s protected installer…');
    try{
      await call('install','POST',{candidate_id:candidate.candidate_id});initiated.current=candidate.version;
      setStatus(previous=>({current_version:previous?.current_version||candidate.current_version,state:'installing',phase:'verifying',target_version:candidate.version,elapsed_seconds:0}));
      setLastStatusAt(Date.now());setMessage('Installing the signed release. Keep power connected.');
    }catch(error){setMessage((error as Error).message);}finally{setBusy(false);setSending(false);}
  }
  const installing=status?.state==='installing';
  const phases=['verifying','copying','installing','syncing','switching','restarting','checking'];
  const labels:Record<string,string>={verifying:'Verifying signature',copying:'Copying release',installing:'Installing application',syncing:'Saving to SD card',switching:'Switching versions',restarting:'Restarting services',checking:'Checking health',restoring:'Restoring previous version'};
  const phase=status?.phase||'verifying',elapsed=Math.max(0,(status?.elapsed_seconds||0)+Math.floor((clock-lastStatusAt)/1000));
  return <section className="luma-update" aria-labelledby="luma-update-title">
    <h2 id="luma-update-title"><CloudDownload aria-hidden="true"/> Luma software</h2>
    <p className="setup-note">Current version: <strong>{status?.current_version??'Checking…'}</strong> · Signed releases from the Luma GitHub project</p>
    <p className="setup-note">Updates are checked, signature-verified and staged before installation. Settings, Google links and saved games stay on this Pi; failed health checks restore the previous release.</p>
    {!candidate||candidate.state==='current'?<button disabled={busy||installing||demo} onClick={()=>void check()}><RefreshCw aria-hidden="true"/>{installing?'Installing…':busy?'Checking…':'Check for updates'}</button>:<div className="luma-update-review">
      <h3>Luma {candidate.version}</h3>
      <p className="setup-note">Verified signed application release{candidate.published_at?` · Published ${new Date(candidate.published_at).toLocaleDateString()}`:''}</p>
      {candidate.release_notes&&<pre className="luma-update-notes">{candidate.release_notes}</pre>}
      <div className="luma-update-actions"><button disabled={busy||installing} onClick={()=>void install()}><Check aria-hidden="true"/>{busy?'Installing…':'Review complete · Install update'}</button><button disabled={busy||installing} onClick={()=>{setCandidate(null);setMessage('Update not installed.');}}>Cancel</button></div>
    </div>}
    {installing&&<p className="setup-note"><ShieldCheck aria-hidden="true"/> Installing verified release {status.target_version}…</p>}
    {status?.state==='failed'&&<p className="setup-message" role="alert">{status.message||'The update failed. The previous release remains active.'}</p>}
    {message&&<p className="setup-message" role="status" aria-live="polite">{message}</p>}
    {(installing||sending)&&<div className="luma-update-overlay" role="status" aria-live="polite" aria-label="Software update in progress">
      <span className="luma-update-mark"><ShieldCheck aria-hidden="true"/> Luma software</span>
      <strong>Updating to {status?.target_version||candidate?.version||'the new release'}</strong>
      <p className="luma-update-phase">{sending?'Sending verified update':labels[phase]||'Working safely'}</p>
      <div className="luma-update-rail" aria-hidden="true">{phases.map((step,index)=><i key={step} className={index<=phases.indexOf(phase)?'done':''}/>)}</div>
      <p className="luma-update-wait">Keep power connected.</p>
      <span className="luma-update-elapsed">{Math.floor(elapsed/60)}:{String(elapsed%60).padStart(2,'0')} elapsed · {networkGap?'Services restarting; this screen will remain visible.':'Progress is saved on the Pi.'}</span>
    </div>}
  </section>;
}
