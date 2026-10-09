import {useEffect,useRef,useState} from 'react';
import {Smartphone} from 'lucide-react';
import {TouchField} from './TouchField';
import {useSetupActivity} from './setupActivity';
type Pending={device_id:string;comparison_code:string};
type Device={device_id:string;label:string};
type Issued={url:string;qr:string|null;expires_in_seconds:number};
async function local(action:string,pin:string,extra:Record<string,string>={}){
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),20000);
  try{
    const response=await fetch('/api/v1/companion/local',{method:'POST',cache:'no-store',signal:controller.signal,
      headers:{'Content-Type':'application/json'},body:JSON.stringify({action,pin,...extra})});
    const value=await response.json();if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'Remote setup unavailable.');return value;
  }finally{clearTimeout(timer);}
}
export function CompanionSetup({demo,pinConfigured}:{demo:boolean;pinConfigured:boolean}){
  const [pin,setPin]=useState(''),[issued,setIssued]=useState<Issued|null>(null),[pending,setPending]=useState<Pending|null>(null);
  const [devices,setDevices]=useState<Device[]>([]),[busy,setBusy]=useState(false),[notice,setNotice]=useState(''),[matched,setMatched]=useState(false);
  const [policy,setPolicy]=useState<'all_profiles'|'primary_only'|null>(null);
  const heldPin=useRef(''),expiry=useRef(0),revision=useRef(0);
  useSetupActivity(busy||!!issued);
  const hide=()=>{revision.current++;heldPin.current='';expiry.current=0;setPin('');setIssued(null);setPending(null);setMatched(false);setDevices([]);setPolicy(null);};
  useEffect(()=>{
    const visibility=()=>{if(document.visibilityState!=='visible')hide();};
    document.addEventListener('visibilitychange',visibility);window.addEventListener('pagehide',hide);
    return()=>{heldPin.current='';revision.current++;document.removeEventListener('visibilitychange',visibility);window.removeEventListener('pagehide',hide);};
  },[]);
  useEffect(()=>{
    if(!issued||demo)return;let live=true;let handle:number;const current=revision.current;
    const poll=async()=>{
      if(!live||!heldPin.current)return;
      if(Date.now()>=expiry.current){hide();setNotice('Enrollment expired. Enter your PIN to request another.');return;}
      try{const result=await local('pending',heldPin.current);if(live&&current===revision.current)setPending(result.pending);}
      catch{if(live&&current===revision.current){hide();setNotice('Enrollment paused. Reconnect your iPhone and request a new QR.');}}
      if(live&&current===revision.current)handle=window.setTimeout(poll,5000);
    };handle=window.setTimeout(poll,5000);return()=>{live=false;clearTimeout(handle);};
  },[issued,demo]);
  async function run(action:()=>Promise<void>){setBusy(true);setNotice('');try{await action();}
    catch(error){hide();setNotice(error instanceof Error?error.message:'Remote setup unavailable.');}finally{setBusy(false);}}
  function start(action:'issue'|'devices'|'remote_policy_status'){
    const submitted=pin;hide();const current=revision.current;
    void run(async()=>{
      if(demo){setNotice('Preview only. Enrollment runs on the installed hub.');return;}
      const result=await local(action,submitted);if(current!==revision.current)return;
      heldPin.current=submitted;expiry.current=Date.now()+300000;
      if(action==='issue')setIssued(result);else if(action==='devices')setDevices(result.devices);else setPolicy(result.policy);
    });
  }
  return <section className="companion-setup"><h2><Smartphone/> iPhone remote</h2>
    <p>Control Luma privately in Safari or from your Home Screen. No games on the phone. Private sync requires your selected iPhone’s authorized Bluetooth connection.</p>
    <p className="setup-note">First enable the private Tailscale HTTPS connection above. Install Tailscale on your iPhone and connect it to the same private account. If you want a Home Screen app, install it before enrolling that window.</p>
    <p className="setup-note">Secondary remotes use their own Tailscale identity and node sharing—not your primary login. If that is impractical, choose primary-only remote below. Secondary phones, wall calendars and timers still work.</p>
    {!pinConfigured?<p>Set your hub privacy PIN first.</p>:<>
      <TouchField label="Hub PIN for remote enrollment" secret mode="digits" required minLength={4} maxLength={8} pattern="[0-9]{4,8}" value={pin} onChange={setPin} disabled={busy}/>
      <button disabled={busy||pin.length<4} onClick={()=>start('issue')}>Create enrollment QR</button>
      <button disabled={busy||pin.length<4} onClick={()=>start('devices')}>Manage enrolled browsers</button>
      <button disabled={busy||pin.length<4} onClick={()=>start('remote_policy_status')}>Review remote access</button>
    </>}
    {policy&&<div><h3>Who can use an iPhone remote?</h3><p>{policy==='primary_only'?'Primary only':'All enrolled users · own information only'}</p>
      <button disabled={busy} onClick={()=>{
        const next=policy==='primary_only'?'all_profiles':'primary_only';
        if(next==='primary_only'&&!confirm('Revoke all secondary browsers and cancel pending consent? Their wall profiles and timers stay. Reenabling remotes requires fresh enrollment.'))return;
        void run(async()=>{if(!heldPin.current||Date.now()>=expiry.current)throw Error('Enter your primary PIN to review remote access again.');
          const current=revision.current;const result=await local('remote_policy',heldPin.current,{policy:next});
          if(current!==revision.current)return;hide();setNotice(result.policy==='primary_only'?'Primary-only remote saved. Secondary wall profiles and timers are unchanged.':'All-user remote enabled. Secondary browsers must enroll again.');});
      }}>{policy==='primary_only'?'Allow secondary remotes':'Use primary-only remote'}</button><button disabled={busy} onClick={hide}>Close review</button>
    </div>}
    {issued&&<div className="private-enrollment">
      {issued.qr&&<img src={issued.qr} width="280" height="280" alt="Scan privately to enroll this iPhone browser"/>}
      <p>Open this link in your chosen Safari or Home Screen window, then tap Enroll. The link expires in five minutes.</p>
      <code className="setup-token">{issued.url}</code>
      {pending&&<><h3>Approval code: {pending.comparison_code}</h3><label className="setup-note"><input type="checkbox" checked={matched} onChange={event=>setMatched(event.target.checked)}/> These six digits match the phone screen</label>
        <button disabled={busy||!matched} onClick={()=>void run(async()=>{
          if(!heldPin.current||Date.now()>=expiry.current)throw Error('Enter your PIN and request a fresh QR.');
          const current=revision.current;await local('approve',heldPin.current,pending);
          if(current!==revision.current)return;hide();setNotice('Browser approved. Your phone can now sync while its Bluetooth session is authorized.');
        })}>Approve matching browser</button></>}
      <button disabled={busy} onClick={hide}>Hide enrollment</button>
    </div>}
    {devices.length>0&&<div><p>Each Safari/Home Screen window has a separate browser key.</p>{devices.map((device,index)=><div key={device.device_id}><b>{device.label} {index+1}</b><button disabled={busy} onClick={()=>{
      if(!confirm('Revoke this browser? It must enroll again to regain access.'))return;
      void run(async()=>{if(!heldPin.current||Date.now()>=expiry.current)throw Error('Enter your PIN again to manage browsers.');
        const current=revision.current;await local('revoke',heldPin.current,{device_id:device.device_id});if(current!==revision.current)return;
        setDevices(values=>values.filter(value=>value.device_id!==device.device_id));setNotice('Browser revoked.');});
    }}>Revoke browser {index+1}</button></div>)}<button onClick={hide}>Hide browsers</button></div>}
    <p className="setup-note">The browser stores a nonexportable signing key, not your calendar or PIN. Clearing browser storage requires re-enrollment. This is browser authorization, not hardware attestation.</p>
    {notice&&<p role="status" className="setup-message">{notice}</p>}
  </section>;
}
import {setupFetch as fetch} from './setupTransport';
