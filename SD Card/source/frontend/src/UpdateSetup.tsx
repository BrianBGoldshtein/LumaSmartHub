import {useEffect,useState} from 'react';
import {Check,CloudDownload,RefreshCw,ShieldCheck} from 'lucide-react';

type Status={current_version:string;state:'idle'|'installing'|'installed'|'failed';target_version?:string|null;message?:string};
type Candidate={state:'available'|'current';current_version:string;version?:string;release_notes?:string;published_at?:string;candidate_id?:string};

async function call<T>(path:string,method='GET',body?:unknown):Promise<T>{
  const response=await fetch(`/api/v1/updates/${path}`,{method,cache:'no-store',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Luma could not check for updates. Check Wi-Fi sign-in and retry.');
  return data as T;
}

export function UpdateSetup({demo=false}:{demo?:boolean}){
  const [status,setStatus]=useState<Status|null>(null),[candidate,setCandidate]=useState<Candidate|null>(null);
  const [busy,setBusy]=useState(false),[message,setMessage]=useState('');
  useEffect(()=>{if(demo){setStatus({current_version:'Preview',state:'idle'});return;}let live=true;
    call<Status>('status').then(value=>{if(live)setStatus(value);}).catch(error=>{if(live)setMessage((error as Error).message);});
    return()=>{live=false;};
  },[demo]);
  async function check(){setBusy(true);setMessage('');setCandidate(null);
    try{if(demo){setMessage('Preview only — no network request or installation.');return;}
      const result=await call<Candidate>('check','POST');setCandidate(result);
      setMessage(result.state==='current'?'Luma is up to date.':'A signed update is ready for review.');
    }catch(error){setMessage((error as Error).message);}finally{setBusy(false);}
  }
  async function install(){if(!candidate?.candidate_id||!candidate.version)return;setBusy(true);setMessage('Sending the reviewed update to Luma’s protected installer…');
    try{
      await call('install','POST',{candidate_id:candidate.candidate_id});setMessage(`Installing Luma ${candidate.version}. The dashboard will briefly restart; your saved settings stay in place.`);
      const deadline=Date.now()+120_000;
      while(Date.now()<deadline){await new Promise(resolve=>setTimeout(resolve,2000));
        try{const next=await call<Status>('status');setStatus(next);
          if(next.current_version===candidate.version&&['installed','idle'].includes(next.state)){setMessage(`Luma ${candidate.version} installed and passed its health check.`);setCandidate(null);return;}
          if(next.state==='failed'){setMessage(next.message||'The update failed. Luma restored the previous release.');return;}
        }catch{/* The API restarts during a valid release switch; retry after it returns. */}
      }
      setMessage('Luma is still restarting. Give it another moment, then check the version here.');
    }catch(error){setMessage((error as Error).message);}finally{setBusy(false);}
  }
  return <section className="luma-update" aria-labelledby="luma-update-title">
    <h2 id="luma-update-title"><CloudDownload aria-hidden="true"/> Luma software</h2>
    <p className="setup-note">Current version: <strong>{status?.current_version??'Checking…'}</strong> · Signed releases from the Luma GitHub project</p>
    <p className="setup-note">Updates are checked, signature-verified and staged before installation. Settings, Google links and saved games stay on this Pi; failed health checks restore the previous release.</p>
    {!candidate||candidate.state==='current'?<button disabled={busy||demo} onClick={()=>void check()}><RefreshCw aria-hidden="true"/>{busy?'Checking…':'Check for updates'}</button>:<div className="luma-update-review">
      <h3>Luma {candidate.version}</h3>
      <p className="setup-note">Verified signed application release{candidate.published_at?` · Published ${new Date(candidate.published_at).toLocaleDateString()}`:''}</p>
      {candidate.release_notes&&<pre className="luma-update-notes">{candidate.release_notes}</pre>}
      <div className="luma-update-actions"><button disabled={busy} onClick={()=>void install()}><Check aria-hidden="true"/>{busy?'Installing…':'Review complete · Install update'}</button><button disabled={busy} onClick={()=>{setCandidate(null);setMessage('Update not installed.');}}>Cancel</button></div>
    </div>}
    {status?.state==='installing'&&<p className="setup-note"><ShieldCheck aria-hidden="true"/> Installing verified release {status.target_version}…</p>}
    {message&&<p className="setup-message" role="status" aria-live="polite">{message}</p>}
  </section>;
}
