import {useCallback,useEffect,useState} from "react";
import {Router,ShieldAlert,Wifi} from "lucide-react";
import {TouchField} from "./TouchField";
import {useSetupActivity} from "./setupActivity";
import {isRemoteSetup,setupFetch as fetch} from "./setupTransport";

type HotspotStatus={ssid:string;configured:boolean;active:boolean;same_as_pin:boolean|null;upstream_connected:boolean;can_enable:boolean;reason:string};
const unavailable:HotspotStatus={ssid:"Luma-Devices",configured:false,active:false,same_as_pin:null,upstream_connected:false,can_enable:false,reason:"Checking Wi-Fi adapters…"};
const preview:HotspotStatus={...unavailable,upstream_connected:true,can_enable:true,reason:"Preview · ready to set up"};

export function WifiHotspotSetup({demo}:{demo:boolean}){
  const [status,setStatus]=useState<HotspotStatus>(demo?preview:unavailable);
  const [editing,setEditing]=useState(false);
  const [statusError,setStatusError]=useState("");
  const [pin,setPin]=useState("");
  const [sameAsPin,setSameAsPin]=useState(false);
  const [wifiPassword,setWifiPassword]=useState("");
  const [revealWifiPassword,setRevealWifiPassword]=useState(false);
  const [acknowledged,setAcknowledged]=useState(false);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  useSetupActivity(busy);
  const refresh=useCallback(async()=>{
    if(demo)return;
    try{
      const response=await fetch("/api/v1/network/hotspot",{cache:"no-store"});
      const result=await response.json();
      if(!response.ok)throw Error(typeof result.detail==="string"?result.detail:"Hotspot status is unavailable.");
      setStatus(result);
      setStatusError("");
    }catch(error){setStatusError(error instanceof Error?error.message:"Hotspot status is unavailable.");}
  },[demo]);
  useEffect(()=>{if(!busy&&!editing)void refresh();},[refresh,busy,editing]);
  async function change(action:"enable"|"disable"){
    const submitted=pin;
    setPin("");setBusy(true);setMessage("");
    try{
      const payload={action,pin:submitted,...(action==="enable"?{same_as_pin:sameAsPin,stanford_permission_confirmed:acknowledged,...(sameAsPin?{}:{wifi_password:wifiPassword})}:{})};
      let result:HotspotStatus;
      if(demo){result={...preview,active:action==="enable",configured:action==="enable",same_as_pin:action==="enable"?sameAsPin:null};}
      else{
        const response=await fetch("/api/v1/network/hotspot",{method:"POST",headers:{"Content-Type":"application/json"},cache:"no-store",body:JSON.stringify(payload)});
        const data=await response.json();
        if(!response.ok)throw Error(typeof data.detail==="string"?data.detail:"Hotspot setup failed.");
        result=data;
      }
      setStatus(result);
      setStatusError("");
      setEditing(false);
      setAcknowledged(false);
      setRevealWifiPassword(false);
      if(action==="disable"){setWifiPassword("");setSameAsPin(false);}
      if(typeof result.same_as_pin==="boolean")setSameAsPin(result.same_as_pin);
      setMessage(demo?"Preview settings applied.":action==="enable"?"Hotspot started.": "Hotspot stopped and saved Wi-Fi key removed.");
    }catch(error){setMessage(error instanceof Error?error.message:"Hotspot setup failed.");}
    finally{setBusy(false);}
  }
  return <section className="wifi-hotspot" id="network-hotspot">
    <h3><Router aria-hidden="true"/> Room-device hotspot</h3>
    <div className="hotspot-summary"><strong>{status.ssid}</strong><span>2.4 GHz · WPA2</span>
      <p role="status">{statusError || (status.active?"Hotspot on":status.configured?"Saved · hotspot off":status.can_enable?"Ready to set up":status.reason)}</p>
    </div>
    {status.active&&!status.upstream_connected&&<p className="setup-note" role="alert">The hotspot is on. Reconnect Luma to its upstream Wi-Fi to restore internet for room devices.</p>}
    {!status.active&&!editing&&<button disabled={busy||!!statusError||!status.can_enable} onClick={()=>{setMessage("");setEditing(true);}}>Set up hotspot</button>}
    {!status.active&&editing&&<>
      <fieldset className="hotspot-key-mode"><legend>Network password</legend>
        <label><input type="radio" name="hotspot-key" checked={sameAsPin} disabled={busy} onChange={()=>{setSameAsPin(true);setWifiPassword("");setRevealWifiPassword(false);}}/><span>Use my Luma PIN · exactly 8 digits</span></label>
        <label><input type="radio" name="hotspot-key" checked={!sameAsPin} disabled={busy} onChange={()=>setSameAsPin(false)}/><span>Use a separate, stronger Wi-Fi passphrase</span></label>
      </fieldset>
      <TouchField label="Confirm current Luma PIN" secret mode="digits" pattern="[0-9]{4,8}" minLength={4} maxLength={8} required value={pin} onChange={setPin} autoComplete="current-password" disabled={busy}/>
      {!sameAsPin&&<><TouchField label="Wi-Fi passphrase · 16–63 ASCII characters" secret={!revealWifiPassword} minLength={16} maxLength={63} required value={wifiPassword} onChange={setWifiPassword} autoComplete="new-password" disabled={busy}/><button type="button" disabled={busy||!wifiPassword} onClick={()=>setRevealWifiPassword(value=>!value)}>{revealWifiPassword?"Hide":"Show"} Wi-Fi passphrase</button></>}
      <label className="hotspot-ack"><input type="checkbox" checked={acknowledged} disabled={busy} onChange={event=>setAcknowledged(event.target.checked)}/><span>The upstream network owner has approved this private hotspot.</span></label>
      <button disabled={busy||!!statusError||!acknowledged||!status.can_enable||!/^[0-9]{4,8}$/.test(pin)||(sameAsPin?pin.length!==8:!(/^[\x20-\x7e]{16,63}$/.test(wifiPassword)))} onClick={()=>void change("enable")}>{busy?"Starting…":"Start hotspot"}</button>
      <button disabled={busy} onClick={()=>{setEditing(false);setPin("");setWifiPassword("");setRevealWifiPassword(false);setAcknowledged(false);}}>Cancel</button>
    </>}
    {status.active&&<>
      <details><summary>Connect the Levoit</summary><ol><li>Join <strong>{status.ssid}</strong> on your iPhone.</li><li>Add the purifier in VeSync and enter {status.same_as_pin?"your eight-digit Luma PIN":"the Wi-Fi passphrase you selected"} when prompted.</li><li>After the purifier is online, rejoin your usual Wi-Fi.</li></ol>{isRemoteSetup()&&<p>Keep this passphrase handy before leaving the remote.</p>}</details>
      {!sameAsPin&&wifiPassword&&<div className="hotspot-passphrase"><strong>Separate Wi-Fi passphrase</strong><code>{revealWifiPassword?wifiPassword:"••••••••••••••••"}</code><button type="button" onClick={()=>setRevealWifiPassword(value=>!value)}>{revealWifiPassword?"Hide":"Show"} passphrase</button><small>This is held in this page only. If you lose it, turn off the hotspot and set it again.</small></div>}
      {status.same_as_pin===false&&!wifiPassword&&<p className="setup-note">This hotspot uses a separate key that is not retained in the dashboard. If you no longer have it, turn the hotspot off and create it again with a key you know.</p>}
      <TouchField label="Confirm current Luma PIN" secret mode="digits" pattern="[0-9]{4,8}" minLength={4} maxLength={8} required value={pin} onChange={setPin} autoComplete="current-password" disabled={busy}/>
      <button disabled={busy||pin.length<4} onClick={()=>void change("disable")}>{busy?"Stopping…":"Turn off and remove hotspot"}</button>
    </>}
    <button type="button" disabled={busy} onClick={()=>void refresh()}><Wifi aria-hidden="true"/> Check hotspot</button>
    <details className="setup-note"><summary><ShieldAlert aria-hidden="true"/> Adapter, password and campus Wi-Fi</summary>
      <p>Keep Luma connected to Wi-Fi. Use a second AP-capable adapter for the hotspot. Keep USB powered while the adapter is attached.</p>
      <p>A separate password keeps your Luma PIN private. If you use your eight-digit PIN, changing it in Luma only takes effect on the hotspot after you recreate the network.</p>
      <p>Use this on networks that permit personal access points. If authorized on Stanford Visitor, complete its sign-in on Luma before connecting room devices. <a href="https://thehub.stanford.edu/find-software-and-computers/computer-usage-policies" target="_blank" rel="noreferrer">Stanford residential policy</a></p>
    </details>
    {message&&<p className="setup-message" role="status">{message}</p>}
  </section>;
}
