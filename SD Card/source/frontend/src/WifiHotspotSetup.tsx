import {useCallback,useEffect,useState} from "react";
import {Router,ShieldAlert,Wifi} from "lucide-react";
import {TouchField} from "./TouchField";
import {useSetupActivity} from "./setupActivity";

type HotspotStatus={ssid:string;configured:boolean;active:boolean;same_as_pin:boolean|null;upstream_connected:boolean;can_enable:boolean;reason:string};
const preview:HotspotStatus={ssid:"Luma-Devices",configured:false,active:false,same_as_pin:null,upstream_connected:false,can_enable:false,reason:"Preview only — radio capability is not checked."};

export function WifiHotspotSetup({demo}:{demo:boolean}){
  const [status,setStatus]=useState<HotspotStatus>(demo?preview:{...preview,reason:"Checking Wi-Fi adapters…"});
  const [pin,setPin]=useState("");
  const [sameAsPin,setSameAsPin]=useState(true);
  const [wifiPassword,setWifiPassword]=useState("");
  const [revealWifiPassword,setRevealWifiPassword]=useState(false);
  const [acknowledged,setAcknowledged]=useState(false);
  const [busy,setBusy]=useState(false);
  const [message,setMessage]=useState("");
  useSetupActivity(busy);
  const refresh=useCallback(async()=>{
    if(demo){setStatus(preview);return;}
    try{
      const response=await fetch("/api/v1/network/hotspot",{cache:"no-store"});
      const result=await response.json();
      if(!response.ok)throw Error(typeof result.detail==="string"?result.detail:"Hotspot status is unavailable.");
      setStatus(result);
      if(typeof result.same_as_pin==="boolean")setSameAsPin(result.same_as_pin);
    }catch(error){setStatus({...preview,reason:error instanceof Error?error.message:"Hotspot status is unavailable."});}
  },[demo]);
  useEffect(()=>{void refresh();const timer=setInterval(()=>void refresh(),30000);return()=>clearInterval(timer);},[refresh]);
  async function change(action:"enable"|"disable"){
    const submitted=pin;
    setPin("");setBusy(true);setMessage("");
    try{
      if(demo){setMessage("Preview only — no hotspot or password was saved.");return;}
      const payload={action,pin:submitted,...(action==="enable"?{same_as_pin:sameAsPin,stanford_permission_confirmed:acknowledged,...(sameAsPin?{}:{wifi_password:wifiPassword})}:{})};
      const response=await fetch("/api/v1/network/hotspot",{method:"POST",headers:{"Content-Type":"application/json"},cache:"no-store",body:JSON.stringify(payload)});
      const result=await response.json();
      if(!response.ok)throw Error(typeof result.detail==="string"?result.detail:"Hotspot setup failed.");
      setStatus(result);
      setAcknowledged(false);
      if(action==="enable"&&!sameAsPin)setRevealWifiPassword(true);
      if(action==="disable"){setWifiPassword("");setRevealWifiPassword(false);setSameAsPin(true);}
      if(typeof result.same_as_pin==="boolean")setSameAsPin(result.same_as_pin);
      setMessage(action==="enable"?sameAsPin?"Luma-Devices is saved. Use your eight-digit Luma PIN as its Wi-Fi password.":"Luma-Devices is saved. Keep the passphrase below to enroll the Levoit.":"Hotspot stopped and its saved Wi-Fi key was removed.");
    }catch(error){setMessage(error instanceof Error?error.message:"Hotspot setup failed.");}
    finally{setBusy(false);}
  }
  return <section className="wifi-hotspot" id="network-hotspot">
    <h3><Router aria-hidden="true"/> Levoit Wi-Fi sharing</h3>
    <p>Create a private 2.4 GHz network for the Core 300S. Luma routes its internet through the Pi’s current Wi-Fi connection; this does not bridge Levoit onto Stanford’s LAN.</p>
    <p className="setup-note" role="status">{status.active?`On · ${status.ssid} · 2.4 GHz WPA2`:status.configured?`Saved · ${status.ssid} is currently off`:status.reason}</p>
    <p className="setup-note"><strong>Hardware:</strong> a second, Linux-supported USB Wi-Fi adapter is required. The Pi 4’s built-in radio must stay connected to eduroam; one radio cannot reliably serve the Levoit’s 2.4 GHz network while it is on campus Wi-Fi.</p>
    <p className="setup-note"><strong>Wi-Fi key:</strong> for the requested same-as-PIN setup, Luma’s PIN must be exactly eight digits (WPA2 requires at least eight characters). If your PIN is shorter, choose the separate passphrase; you do not need to change your Luma PIN. A numeric PIN is weaker than a random Wi-Fi password, and anyone you give the shared PIN-key to will also learn your Luma PIN. The NetworkManager Wi-Fi profile is persisted root-only on the Pi; it is not added to Luma backups.</p>
    {!status.active&&<>
      <fieldset className="hotspot-key-mode"><legend>Network password</legend>
        <label><input type="radio" name="hotspot-key" checked={sameAsPin} disabled={busy} onChange={()=>{setSameAsPin(true);setWifiPassword("");setRevealWifiPassword(false);}}/><span>Use my Luma PIN · exactly 8 digits</span></label>
        <label><input type="radio" name="hotspot-key" checked={!sameAsPin} disabled={busy} onChange={()=>setSameAsPin(false)}/><span>Use a separate, stronger Wi-Fi passphrase</span></label>
      </fieldset>
      <TouchField label="Confirm current Luma PIN" secret mode="digits" pattern="[0-9]{4,8}" minLength={4} maxLength={8} required value={pin} onChange={setPin} autoComplete="current-password" disabled={busy}/>
      {!sameAsPin&&<><TouchField label="Wi-Fi passphrase · 16–63 ASCII characters" secret={!revealWifiPassword} minLength={16} maxLength={63} required value={wifiPassword} onChange={setWifiPassword} autoComplete="new-password" disabled={busy}/><button type="button" disabled={busy||!wifiPassword} onClick={()=>setRevealWifiPassword(value=>!value)}>{revealWifiPassword?"Hide":"Show"} Wi-Fi passphrase</button></>}
      <label className="hotspot-ack"><input type="checkbox" checked={acknowledged} disabled={busy} onChange={event=>setAcknowledged(event.target.checked)}/><span>I have explicit approval from Stanford or the network owner for this Pi to run a private access point with DHCP and NAT on this connection. I will accept any Stanford Visitor sign-in on Luma itself.</span></label>
      <button disabled={busy||!acknowledged||!status.can_enable||(sameAsPin?pin.length!==8:wifiPassword.length<16)} onClick={()=>void change("enable")}>{busy?"Starting…":status.configured?"Refresh hotspot":"Turn on Luma-Devices"}</button>
    </>}
    {status.active&&<>
      <p className="setup-note">To enroll the purifier, put your iPhone on <strong>Luma-Devices</strong>, enter {status.same_as_pin?"your eight-digit Luma PIN":"the Wi-Fi passphrase you selected"} in VeSync, and keep VPN off during setup. Once the purifier is online, your phone can rejoin eduroam.</p>
      {!sameAsPin&&wifiPassword&&<div className="hotspot-passphrase"><strong>Separate Wi-Fi passphrase</strong><code>{revealWifiPassword?wifiPassword:"••••••••••••••••"}</code><button type="button" onClick={()=>setRevealWifiPassword(value=>!value)}>{revealWifiPassword?"Hide":"Show"} passphrase</button><small>This is held in this page only. If you lose it, turn off the hotspot and set it again.</small></div>}
      {status.same_as_pin===false&&!wifiPassword&&<p className="setup-note">This hotspot uses a separate key that is not retained in the dashboard. If you no longer have it, turn the hotspot off and create it again with a key you know.</p>}
      <TouchField label="Confirm current Luma PIN" secret mode="digits" pattern="[0-9]{4,8}" minLength={4} maxLength={8} required value={pin} onChange={setPin} autoComplete="current-password" disabled={busy}/>
      <button disabled={busy||pin.length<4} onClick={()=>void change("disable")}>{busy?"Stopping…":"Turn off and remove hotspot"}</button>
    </>}
    <button type="button" disabled={busy} onClick={()=>void refresh()}><Wifi aria-hidden="true"/> Check hotspot</button>
    <p className="setup-note"><ShieldAlert aria-hidden="true"/> Stanford residential-computing guidance says routers, DHCP and NAT servers are generally not allowed; Stanford Medicine explicitly prohibits internet-connection sharing and personal wireless access points. Rules depend on your location and network, so do not enable sharing until the responsible Stanford/venue administrator explicitly approves this setup. <a href="https://thehub.stanford.edu/find-software-and-computers/computer-usage-policies" target="_blank" rel="noreferrer">Residential network policy</a> · <a href="https://med.stanford.edu/irt/personal-computing/network-access/policies" target="_blank" rel="noreferrer">Stanford Medicine policy</a>. Visitor sessions last 12 hours and restrict network services, so purifier cloud setup may not work there. If approved, accept Visitor terms on Luma itself before enabling this; the purifier cannot complete a captive-portal sign-in.</p>
    {message&&<p className="setup-message" role="status">{message}</p>}
  </section>;
}
import {setupFetch as fetch} from './setupTransport';
