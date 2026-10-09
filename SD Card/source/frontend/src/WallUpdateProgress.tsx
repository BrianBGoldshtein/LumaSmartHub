import {useEffect,useRef,useState} from 'react';
import {ShieldCheck} from 'lucide-react';
import {dashboardRefreshUrl} from './dashboardRefresh';
type Status={current_version:string;state:string;phase?:string;target_version?:string;elapsed_seconds?:number;message?:string};
const phases=['verifying','copying','installing','syncing','switching','restarting','checking'];
const labels:Record<string,string>={verifying:'Verifying signature',copying:'Copying release',installing:'Installing application',syncing:'Saving to SD card',switching:'Switching versions',restarting:'Restarting services',checking:'Checking health',restoring:'Restoring previous version'};

/** Always mounted, including setup and sleeping screens. The initiating
 * browser is irrelevant: the protected broker is the source of truth. */
export function WallUpdateProgress({demo=false}:{demo?:boolean}){
  const [status,setStatus]=useState<Status|null>(null),[gap,setGap]=useState(false);
  const target=useRef<string|null>(null),reloading=useRef(false);
  useEffect(()=>{
    if(demo)return;
    let live=true,inFlight=false;let refreshTimer:ReturnType<typeof setTimeout>|undefined;
    async function poll(){
      if(inFlight)return;inFlight=true;
      const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),4000);
      try{
        const response=await fetch('/api/v1/updates/status',{cache:'no-store',signal:controller.signal});
        if(!response.ok)throw Error('Status unavailable');
        const next:Status=await response.json();if(!live)return;
        if(!next||typeof next.current_version!=='string'||!['idle','installing','installed','failed'].includes(next.state))throw Error('Invalid update status');
        setGap(false);setStatus(next);
        if(next.state==='installing'&&next.target_version)target.current=next.target_version;
        if(next.state==='installed'&&target.current===next.current_version&&!reloading.current){
          reloading.current=true;
          refreshTimer=setTimeout(()=>{if(live)location.replace(dashboardRefreshUrl(location.href,next.current_version));},12000);
        }
        if(next.state==='failed')target.current=null;
      }catch{if(live)setGap(true);}finally{clearTimeout(timeout);inFlight=false;}
    }
    void poll();const interval=setInterval(()=>void poll(),1500);
    return()=>{live=false;clearInterval(interval);if(refreshTimer)clearTimeout(refreshTimer);};
  },[demo]);
  const finishing=status?.state==='installed'&&target.current===status.current_version;
  if(status?.state!=='installing'&&!finishing)return null;
  if(!status)return null;
  const theme=document.querySelector('.app')?.className.match(/theme-([\w-]+)/)?.[1]||'luma-glass';
  const elapsed=status.elapsed_seconds||0;
  return <div className={`app theme-${theme} wall-update-progress`} style={{position:'fixed',inset:0,zIndex:2000}}>
    <div className="luma-update-overlay" role="status" aria-live="polite" aria-label="Software update in progress">
      <span className="luma-update-mark"><ShieldCheck/> Luma software</span>
      <strong>Updating to {status.target_version}</strong>
      <p className="luma-update-phase">{finishing?'Update verified · restarting Luma':labels[status.phase||'']||'Working safely'}</p>
      <div className="luma-update-rail" aria-hidden="true">{phases.map((step,index)=><i key={step} className={finishing||index<=phases.indexOf(status.phase||'')?'done':''}/>)}</div>
      <p className="luma-update-wait">Keep power connected. Luma will reboot after the health check.</p>
      <span className="luma-update-elapsed">{Math.floor(elapsed/60)}:{String(elapsed%60).padStart(2,'0')} elapsed · {gap?'Services restarting; progress remains visible.':'Progress is saved on this Pi.'}</span>
    </div>
  </div>;
}
