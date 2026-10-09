import {useEffect, useState} from "react";
import {useSetupActivity} from "./setupActivity";
import {ShieldCheck} from "lucide-react";

type Connection = {state:string; command_url:string|null; auth_url?:string; qr?:string};
const labels:Record<string,string> = {
  off:"Not connected", Running:"Private connection ready", NeedsLogin:"Sign in on your iPhone",
  NeedsMachineAuth:"Approve Luma in Tailscale", Stopped:"Connection paused", Starting:"Connecting…", NoState:"Not signed in",
};
async function request(action:string):Promise<Connection> {
  const response=await fetch("/api/v1/tailscale",{method:"POST",cache:"no-store",headers:{"Content-Type":"application/json"},body:JSON.stringify({action})});
  const value=await response.json();
  if(!response.ok) throw new Error(typeof value.detail==="string"?value.detail:"Connection unavailable. Try again.");
  return value;
}

export function TailscaleSetup({demo}:{demo:boolean}) {
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
  return <section className="private-connection"><h2><ShieldCheck/> Private iPhone connection</h2>
    <p>Siri Shortcuts, securely from your iPhone. Optional Tailscale Personal account — free for personal use. Hey Luma and touch work without it.</p>
    <p role="status"><strong>{labels[connection.state] || (connection.state==="loading"?"Checking…":"Connection unavailable")}</strong>{connection.command_url?" · Commands enabled":" · Commands not enabled"}</p>
    <p className="setup-note">Install Tailscale on your iPhone and use a personal account on its free plan. Tap Connect, then scan the code here using your phone’s camera. Do not share the sign-in code.</p>
    <div className="private-connection-actions">
      <button disabled={busy || connection.state==="loading"} onClick={()=>void run("connect")}>{busy?"Working…":connection.state==="Running"?"Reconnect":"Connect / sign in"}</button>
      <button disabled={busy} onClick={()=>void run("status")}>Refresh</button>
      {connection.state!=="off" && connection.state!=="loading" && <button disabled={busy} onClick={()=>void run("disconnect")}>Disconnect</button>}
    </div>
    {connection.auth_url && <div className="private-enrollment">
      {connection.qr && <img src={connection.qr} alt="Scan privately with your iPhone camera to sign in to Tailscale" width="256" height="256"/>}
      <p>On your iPhone, open this address if the camera cannot scan:</p><code className="setup-token">{connection.auth_url}</code>
      <p className="setup-note">Sign-in stays on your phone. Luma never asks for your account password. This code hides after five minutes; reconnect to request another.</p>
    </div>}
    {connection.state==="Running" && <>
      <p className="setup-note">In Tailscale’s admin console → DNS, enable MagicDNS and HTTPS certificates. The certificate’s Luma hostname is public in certificate-transparency logs; the service itself stays private. Limit access to your own phone/account (see the included Tailscale guide), then enable commands.</p>
      <button disabled={busy} onClick={()=>void run("enable")}>{connection.command_url?"Reconfigure private commands":"Enable private commands"}</button>
    </>}
    {connection.command_url && <><p>Use this HTTPS address in your Apple Shortcut, with the Shortcut token in All settings → Connections:</p><code className="setup-token">{connection.command_url}</code></>}
    <p className="setup-note">No public sharing or remote SSH. The optional iPhone remote below requires separate PIN-approved browser enrollment and live authorized Bluetooth; Tailscale alone never reveals private details. Campus Wi-Fi must be online first.</p>
    {message && <p className="setup-message" role="status">{message}</p>}
  </section>;
}
import {setupFetch as fetch} from './setupTransport';
