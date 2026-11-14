import {useEffect, useState} from "react";
import {useSetupActivity} from "./setupActivity";
import {ShieldCheck} from "lucide-react";
import {CompanionSetup} from './CompanionSetup';
import {setupFetch as fetch} from './setupTransport';

type Connection = {state:string; command_url:string|null; auth_url?:string; qr?:string};
const labels:Record<string,string> = {
  off:"Not connected", Running:"Signed in to Tailscale", NeedsLogin:"Sign in on your iPhone",
  NeedsMachineAuth:"Approve Luma in Tailscale", Stopped:"Connection paused", Starting:"Connecting…", NoState:"Not signed in",
};
async function request(action:string):Promise<Connection> {
  const response=await fetch("/api/v1/tailscale",{method:"POST",cache:"no-store",headers:{"Content-Type":"application/json"},body:JSON.stringify({action})});
  const value=await response.json();
  if(!response.ok) throw new Error(typeof value.detail==="string"?value.detail:"Connection unavailable. Try again.");
  return value;
}

export function TailscaleSetup({demo,pinConfigured}:{demo:boolean;pinConfigured?:boolean}) {
  const [connection,setConnection]=useState<Connection>({state:"loading",command_url:null});
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  useSetupActivity(busy);
  useEffect(()=>{
    if(demo){setConnection({state:"off",command_url:null});return;}
    let cancelled=false;
    request("status").then(value=>{if(!cancelled)setConnection(value);}).catch(()=>{if(!cancelled)setConnection({state:"unavailable",command_url:null});});
    return ()=>{cancelled=true;};
  },[demo]);
  // Poll only while the user is looking at enrollment. Nothing runs in demo.
  useEffect(()=>{
    if(demo || busy || !["NeedsLogin","NeedsMachineAuth","Starting"].includes(connection.state))return;
    let cancelled=false;
    const timer=window.setTimeout(()=>{request("status").then(value=>{if(!cancelled)setConnection(value);}).catch(()=>{if(!cancelled)setMessage("Could not refresh. Check the connection, then tap Refresh.");});},5000);
    return ()=>{cancelled=true;clearTimeout(timer);};
  },[demo,busy,connection]);
  async function run(action:string) {
    setBusy(true);setMessage("");
    try {
      if(demo){setMessage("Preview only. Sign-in is available on the installed Pi.");return;}
      const value=await request(action);
      setConnection(value);
      if(action==="disconnect")setMessage("Disconnected. Your sign-in is saved for next time.");
    } catch(error) {setMessage(error instanceof Error?error.message:"Please try again.");}
    finally {setBusy(false);}
  }
  return <><section className="private-connection"><h2><ShieldCheck/> Set up your iPhone remote</h2>
    <p role="status"><strong>{connection.command_url?"Private HTTPS ready":labels[connection.state] || (connection.state==="loading"?"Checking…":"Connection unavailable")}</strong></p>
    {!connection.command_url&&<p className="setup-note">Install the Tailscale app on your iPhone and connect it to your account. Add Luma to that same account using the sign-in code below.</p>}
    <div className="private-connection-actions">
      {connection.state!=="Running"&&connection.state!=="NeedsMachineAuth"&&<button type="button" disabled={busy || connection.state==="loading"} onClick={()=>void run("connect")}>{busy?"Working…":connection.auth_url?"Get a new sign-in code":"Sign in to Tailscale"}</button>}
      <button type="button" disabled={busy} onClick={()=>void run("status")}>Refresh status</button>
    </div>
    {connection.auth_url && <div className="private-enrollment">
      {connection.qr && <img src={connection.qr} alt="Scan privately with your iPhone camera to sign in to Tailscale" width="256" height="256"/>}
      <p>Scan with your iPhone camera. If scanning is unavailable, open the sign-in link.</p><a className="setup-action" href={connection.auth_url} target="_blank" rel="noreferrer">Open Tailscale sign-in</a>
      <p className="setup-note">The code expires after five minutes. Return here after sign-in and check the status.</p>
    </div>}
    {connection.state==="NeedsMachineAuth"&&<p>Approve Luma under <a className="setup-action" href="https://login.tailscale.com/admin/machines" target="_blank" rel="noreferrer">Tailscale Devices</a>, then refresh here.</p>}
    {connection.state==="Running" && !connection.command_url && <>
      <p className="setup-note">Open <a className="setup-action" href="https://login.tailscale.com/admin/dns" target="_blank" rel="noreferrer">Tailscale DNS settings</a> and enable MagicDNS and HTTPS certificates. The certificate publishes Luma’s Tailscale hostname. Access stays on your private Tailscale network.</p>
      <button type="button" disabled={busy} onClick={()=>void run("enable")}>Enable private HTTPS</button>
    </>}
    {message && <p className="setup-message" role="alert">{message}</p>}
    {connection.command_url && <details><summary>Siri Shortcuts address</summary><code className="setup-token">{connection.command_url}</code></details>}
    {connection.state!=="off" && connection.state!=="loading" && <details><summary>Manage Tailscale connection</summary><button type="button" disabled={busy} onClick={()=>void run("disconnect")}>Disconnect Tailscale</button></details>}
  </section>{pinConfigured!==undefined&&connection.command_url&&<CompanionSetup demo={demo} pinConfigured={pinConfigured}/>}</>;
}
