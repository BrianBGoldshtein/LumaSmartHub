import {useEffect,useState} from "react";
import {useSetupActivity} from "./setupActivity";
import {Wifi,LockKeyhole,Check} from "lucide-react";
import {TouchField} from "./TouchField";
import {SystemKeyboardControl} from "./SystemKeyboardControl";
import {networkDescription,type NetworkStatus} from "./networkStatus";

type Network={device:string;access_point:string;ssid:string;security:string;strength:number;connected:boolean};
type Scan={wifi_enabled:boolean;hardware_enabled:boolean;connectivity:number;wifi_device_count:number;scan_complete:boolean;networks:Network[]};
const sample:Scan={wifi_enabled:true,hardware_enabled:true,connectivity:2,wifi_device_count:1,scan_complete:true,networks:[{device:"preview",access_point:"visitor",ssid:"Stanford Visitor",security:"open",strength:91,connected:false},{device:"preview",access_point:"eduroam",ssid:"eduroam",security:"stanford-eduroam",strength:88,connected:false}]};

export function NetworkSetup({demo}:{demo:boolean}){
  const [scan,setScan]=useState<Scan>(),[selected,setSelected]=useState<Network>(),[password,setPassword]=useState("");
  const [busy,setBusy]=useState(false),[message,setMessage]=useState("");
  useSetupActivity(busy);
  const [identity,setIdentity]=useState("");
  const [status,setStatus]=useState<NetworkStatus>();
  const [demoScan,setDemoScan]=useState(sample);
  useEffect(()=>{
    let stopped=false;
    const controller=new AbortController();
    async function poll(){
      try{
        const response=demo?null:await fetch("/api/v1/network/status",{signal:controller.signal});
        if(response && !response.ok)throw Error();
        const next=demo?{state:demoScan.connectivity===4?"online":"portal",stale:false,checking_enabled:true,checked_at:null}:await response!.json();
        if(!stopped)setStatus(next);
      }catch{if(!stopped)setStatus({state:"unavailable",stale:false,checking_enabled:false,checked_at:null});}
    }
    void poll();const timer=setInterval(()=>void poll(),30000);
    return ()=>{stopped=true;controller.abort();clearInterval(timer);};
  },[demo,demoScan.connectivity]);
  async function send(payload:unknown){
    const response=await fetch("/api/v1/network",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const result=await response.json();if(!response.ok)throw Error(typeof result.detail==="string"?result.detail:"Wi-Fi setup unavailable");return result;
  }
  async function refresh(action="scan"){
    setBusy(true);setMessage("");setPassword("");setIdentity("");setSelected(undefined);
    try{setScan(demo?demoScan:await send({action}));}catch(error){setMessage(error instanceof Error?error.message:"Could not scan");}finally{setBusy(false);}
  }
  async function connect(){
    if(!selected)return;setBusy(true);setMessage("Joining your network…");
    const secret=password,account=identity;setPassword("");setIdentity("");
    try{
      if(demo){const next={...sample,connectivity:selected.security==="stanford-eduroam"?4:2,networks:sample.networks.map(n=>({...n,connected:n.access_point===selected.access_point}))};setDemoScan(next);setScan(next);setMessage("Preview only — no network or password was saved.");}
      else{await send({action:"connect",device:selected.device,access_point:selected.access_point,password:secret,...(selected.security==="stanford-eduroam"?{identity:account}:{})});setMessage("Connected. Wi-Fi is saved on this Pi. Check internet access below; visitor networks may still require sign-in.");setScan(await send({action:"scan"}));}
      setSelected(undefined);
    }catch(error){setMessage(error instanceof Error?error.message:"Could not join");}finally{setBusy(false);}
  }
  async function portal(){
    setBusy(true);
    try{
      if(!demo){const response=await fetch("/api/v1/network/portal",{method:"POST"});const data=await response.json();if(!response.ok)throw Error(data.detail || "Could not open sign-in");}
      setMessage(demo?"Preview only — on the Pi this opens a separate browser. Review and accept Stanford’s terms yourself, then close that window to return to Luma.":"Opening a separate sign-in browser. Review the network terms yourself; close that window to return to Luma.");
    }catch(error){setMessage(error instanceof Error?error.message:"Could not open sign-in");}finally{setBusy(false);}
  }
  async function check(){
    setBusy(true);setMessage("");
    try{
      const result=demo?{state:demoScan.connectivity===4?"online":"portal",checking_enabled:true}:await send({action:"check"});
      setStatus({...result,stale:false,checked_at:new Date().toISOString()});
    }catch(error){setMessage(error instanceof Error?error.message:"Could not check internet access");}finally{setBusy(false);}
  }
  return <section className="network-setup" id="network"><h2><Wifi/> Wi-Fi</h2><p>Use eduroam with your Stanford SUNet account, or Stanford Visitor with browser sign-in.</p>
    <p className="setup-note" role="status">{networkDescription(status)}</p>
    <button disabled={busy} onClick={()=>void refresh()}>{busy?"Working…":"Find networks"}</button>
    {scan && !scan.wifi_enabled && <button disabled={busy || !scan.hardware_enabled} onClick={()=>void refresh("enable")}>Turn on Wi-Fi</button>}
    {scan && !scan.hardware_enabled && <p className="setup-note">Wi-Fi is blocked or unavailable. Check the Pi’s wireless region and radio configuration using the administrator guide.</p>}
    <div className="network-list">{scan?.networks.map(n=><button key={`${n.device}-${n.access_point}`} disabled={busy || n.security==="unsupported"} aria-pressed={selected?.access_point===n.access_point} onClick={()=>{setSelected(n);setPassword("");setIdentity("");setMessage("");}}>
      {n.connected?<Check/>:n.security==="open"?<Wifi/>:<LockKeyhole/>}<span>{n.ssid}<small>{n.connected?"Connected":n.security==="unsupported"?"Advanced setup required":n.security==="stanford-eduroam"?"Stanford SUNet · verified profile":n.security==="open"?"Open network":n.security==="sae"?"WPA3":"WPA2"}</small></span><small>{n.strength}%</small>
    </button>)}</div>
    {scan?.wifi_enabled && scan.networks.length===0 && scan.wifi_device_count===0 && <p>NetworkManager cannot see a Wi-Fi radio. Check the Pi Wi-Fi driver and supplicant installation.</p>}
    {scan?.wifi_enabled && scan.networks.length===0 && scan.wifi_device_count>0 && !scan.scan_complete && <p>The Wi-Fi scan did not finish. Try again; if it persists, the Wi-Fi scanning backend may be missing or unavailable.</p>}
    {scan?.wifi_enabled && scan.networks.length===0 && scan.wifi_device_count>0 && scan.scan_complete && <p>No networks were reported by the completed scan. Try scanning again or check the radio and regulatory region.</p>}
    {selected && !selected.connected && <form onSubmit={e=>{e.preventDefault();void connect();}}>
      <p>Join <strong>{selected.ssid}</strong></p>
      {selected.security==="stanford-eduroam" && <><p className="setup-note">Stanford accounts only. Uses Stanford’s official eduroam certificate profile; server verification cannot be skipped. Joining saves your Wi-Fi credentials locally on this Pi, outside dashboard backups.</p><TouchField label="SUNetID@stanford.edu" placeholder="yourid@stanford.edu" value={identity} onChange={setIdentity} maxLength={77} required disabled={busy}/></>}
      {selected.security==="open"?<p className="setup-note">This network is unencrypted. Verify the campus network name and use secure HTTPS pages for account sign-in. Luma’s control API stays local.</p>:<TouchField label={selected.security==="stanford-eduroam"?"SUNet password":"Wi-Fi password"} secret value={password} onChange={setPassword} maxLength={selected.security==="stanford-eduroam"?256:64} required disabled={busy}/>}
      <button disabled={busy}>Join network</button><button type="button" disabled={busy} onClick={()=>{setSelected(undefined);setPassword("");setIdentity("");}}>Cancel</button>
    </form>}
    {message && <p className="setup-message" role="status">{message}</p>}
    <SystemKeyboardControl demo={demo}/>
    <button disabled={busy} onClick={()=>void portal()}>Open network sign-in</button>
    <button disabled={busy} onClick={()=>void check()}>Check internet access</button>
    {scan?.connectivity===2 && <p className="setup-note">This network requires browser sign-in.</p>}
    <p className="setup-note">Stanford Visitor sessions last up to 12 hours; you may need to accept the terms again. Luma never accepts them automatically. The sign-in browser opens an HTTP page to trigger the network’s redirect; verify the destination before entering credentials.</p>
    <p className="setup-note">Eduroam setup supports Stanford SUNet accounts only. If authentication fails, check your account, the Pi’s date and time, and the installed certificate profile; never bypass a certificate warning. Real campus connectivity still requires testing.</p>
  </section>;
}
