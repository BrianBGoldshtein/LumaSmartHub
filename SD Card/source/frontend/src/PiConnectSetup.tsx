import {useEffect,useState} from "react";
import {MonitorCog,RefreshCw,ShieldCheck,Terminal} from "lucide-react";
import {useSetupActivity} from "./setupActivity";

type PiConnectStatus={available:boolean;state:string;signed_in:boolean;remote_shell:boolean;verification_url?:string;qr?:string|null};
type ConnectDiagnostics={available:boolean;checks:{api:boolean|null;websocket:boolean|null;stun:boolean|null;turn:boolean|null}};
type Action="status"|"diagnose"|"signin"|"shell_on"|"shell_off";

async function request<T=PiConnectStatus>(action:Action):Promise<T>{
  const response=await fetch("/api/v1/pi-connect",{method:"POST",cache:"no-store",headers:{"Content-Type":"application/json"},body:JSON.stringify({action})});
  const data=await response.json().catch(()=>({}));
  if(!response.ok)throw new Error(typeof data.detail==="string"?data.detail:"Pi Connect setup is unavailable. Refresh and try again.");
  return data as T;
}

export function PiConnectSetup({demo=false}:{demo?:boolean}){
  const [status,setStatus]=useState<PiConnectStatus|null>(demo?{available:false,state:"preview",signed_in:false,remote_shell:false}:null);
  const [diagnostics,setDiagnostics]=useState<ConnectDiagnostics|null>(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState("");
  useSetupActivity(busy);
  async function refresh(){
    setError("");
    if(demo){setStatus({available:false,state:"preview",signed_in:false,remote_shell:false});return;}
    try{setStatus(await request("status"));}
    catch(problem){setStatus(null);setError(problem instanceof Error?problem.message:"Pi Connect setup is unavailable.");}
  }
  useEffect(()=>{void refresh();},[demo]);
  useEffect(()=>{
    if(demo||status?.state!=="awaiting_approval"||busy)return;
    let cancelled=false;
    const timer=window.setTimeout(()=>{request("status").then(value=>{if(!cancelled)setStatus(value);}).catch(()=>{if(!cancelled)setError("Approval check failed. Tap Refresh to check again.");});},4000);
    return()=>{cancelled=true;clearTimeout(timer);};
  },[demo,status?.state,busy,status?.verification_url]);
  async function run(action:Exclude<Action,"status">){
    setBusy(true);setError("");
    try{
      if(demo){setStatus({available:false,state:"preview",signed_in:false,remote_shell:false});return;}
      if(action==="diagnose")setDiagnostics(await request<ConnectDiagnostics>(action));
      else setStatus(await request(action));
    }catch(problem){setError(problem instanceof Error?problem.message:"Pi Connect setup is unavailable.");}
    finally{setBusy(false);}
  }
  const unavailable=error.includes("updated Luma image")||status?.state==="not_installed";
  const label=demo?"Preview only":unavailable?"Not available in this image":status?.state==="awaiting_approval"?"Waiting for your approval":status?.remote_shell?"Admin remote shell is on":status?.signed_in?"Pi linked · shell off":status?.state==="off"?"Pi Connect is off":status?"Not signed in":"Checking Pi Connect…";
  const checkLabel=(value:boolean|null)=>value===true?"reachable":value===false?"blocked or unavailable":"not determined";
  return <section className="pi-connect-setup" aria-labelledby="pi-connect-heading">
    <h2 id="pi-connect-heading"><MonitorCog aria-hidden="true"/> Raspberry Pi Connect</h2>
    <p>Secure recovery access when local-network SSH is blocked. Sign in with your Raspberry Pi account, then explicitly enable the remote shell.</p>
    <p className="pi-connect-status" role="status"><ShieldCheck aria-hidden="true"/><strong>{label}</strong></p>
    {demo?<p className="setup-note">Preview only — no sign-in or remote access is started.</p>:unavailable?<p className="setup-note">This installed image does not include the touch setup broker yet. The prepared Luma OS image will add it; no setting has changed.</p>:<>
      <p className="setup-note">The Pi stays unlinked until you tap Start sign-in. Remote shell access is a powerful administrator session; approve only your own Raspberry Pi account. Screen sharing stays off.</p>
      {!status?.signed_in&&<button disabled={busy||!status?.available} onClick={()=>void run("signin")}>{busy?"Starting sign-in…":status?.state==="awaiting_approval"?"Refresh sign-in link":"Start Pi Connect sign-in"}</button>}
      {status?.verification_url&&<div className="pi-connect-enrollment">
        {status.qr&&<img src={status.qr} alt="One-time Raspberry Pi Connect sign-in QR code" width="240" height="240"/>}
        <div><strong>Approve this Pi from your phone</strong><p>Scan the code, sign in to your Raspberry Pi account, and approve this device. The one-time link expires shortly.</p><a href={status.verification_url} target="_blank" rel="noreferrer">Open verification link on this Pi</a><code className="setup-token">{status.verification_url}</code></div>
      </div>}
      {status?.signed_in&&!status.remote_shell&&<button disabled={busy} onClick={()=>void run("shell_on")}><Terminal aria-hidden="true"/> Enable admin remote shell</button>}
      {status?.remote_shell&&<><p className="setup-note">Ready: on your phone or computer, open <strong>connect.raspberrypi.com → Devices → Luma → Connect via → Remote shell</strong>. The shell runs as the dedicated Luma administrator and can use sudo. This approval persists across reboots and app-only updates.</p><button disabled={busy} onClick={()=>void run("shell_off")}>Disable remote shell</button></>}
      <button disabled={busy} onClick={()=>void refresh()}><RefreshCw aria-hidden="true"/> Refresh status</button>
      <button disabled={busy||!status?.available} onClick={()=>void run("diagnose")}>Test Connect network</button>
      {diagnostics&&<p className="setup-note" role="status">Connect API: {checkLabel(diagnostics.checks.api)} · Live link: {checkLabel(diagnostics.checks.websocket)} · Relay: {checkLabel(diagnostics.checks.turn)}. A network test cannot sign in or enable the remote shell.</p>}
    </>}
    {error&&!unavailable&&<p className="setup-message" role="alert">{error}</p>}
  </section>;
}
