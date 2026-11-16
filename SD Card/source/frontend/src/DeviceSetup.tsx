import {useEffect,useState} from "react";
import {Check, CloudSun, ShieldCheck} from "lucide-react";
import {BluetoothSetup} from "./BluetoothSetup";
import {TailscaleSetup} from "./TailscaleSetup";
import {CompanionSetup} from "./CompanionSetup";
import {TouchField,TouchInputProvider} from "./TouchField";
import {coordinates} from "./touchInput";
import {isRemoteSetup,setupFetch as fetch} from "./setupTransport";
import {announceAdminNeeded} from "./adminState";
import {useSetupActivity} from "./setupActivity";

async function api(path:string, method="GET", body?:unknown) {
  const response=await fetch(`/api/v1/${path}`,{method,headers:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok){announceAdminNeeded(data);throw new Error(typeof data.detail === "string" ? data.detail : "Check the entered settings.");}
  return data;
}
type DeviceSection = "space" | "location" | "speaker" | "privacy" | "bluetooth" | "iphone-remote" | "shortcuts" | "diagnostics";

export function DeviceSetup({demo,section,onSaved}:{demo:boolean;section:DeviceSection;onSaved?:()=>void}) {
  const [form,setForm]=useState({weather_location_label:"",latitude:"",longitude:"",timezone:Intl.DateTimeFormat().resolvedOptions().timeZone || "America/Los_Angeles",orientation:"landscape",audio_output:"auto"});
  const [pin,setPin]=useState("");
  const [pinConfigured,setPinConfigured]=useState(false);
  const [unlockPin,setUnlockPin]=useState("");
  const [token,setToken]=useState("");
  const [confirmTokenReset,setConfirmTokenReset]=useState(false);
  const [phoneAddress,setPhoneAddress]=useState("");
  const [message,setMessage]=useState("");
  const [busy,setBusy]=useState(false);
  const [diagnostics,setDiagnostics]=useState<Record<string,unknown>>();
  const isLocation=section==="space"||section==="location";
  const needsSettings=isLocation||section==="speaker"||section==="bluetooth";
  const needsSecurity=section==="privacy"||section==="bluetooth"||section==="iphone-remote";
  const [ready,setReady]=useState(demo||(!needsSettings&&!needsSecurity)),[retry,setRetry]=useState(0);
  useSetupActivity(busy);
  useEffect(()=>{
    if(demo||(!needsSettings&&!needsSecurity)) return;
    let active=true;
    Promise.all([needsSettings?api("settings"):null,needsSecurity?api("security/status"):null]).then(([settings,security])=>{
      if(!active)return;
      if(settings){
        setForm({weather_location_label:settings.weather_location_label,latitude:settings.latitude?.toString() || "",longitude:settings.longitude?.toString() || "",timezone:settings.timezone,orientation:settings.orientation,audio_output:settings.audio_output || "auto"});
        setPhoneAddress(settings.phone_address || "");
      }
      if(security)setPinConfigured(security.pin_configured);
      setReady(true);
    }).catch(error=>{if(active)setMessage(error.message);});
    return()=>{active=false;};
  },[demo,needsSettings,needsSecurity,retry]);
  async function run(action:()=>Promise<void>) {
    setBusy(true);setMessage("");
    try {await action();}catch(error){setMessage(error instanceof Error ? error.message : "Please try again.");}finally{setBusy(false);}
  }
  const field=(name:keyof typeof form,value:string)=>setForm(previous=>({...previous,[name]:value}));
  const speakerField=<label>Speaker output<select value={form.audio_output} onChange={e=>field("audio_output",e.target.value)}><option value="auto">System default</option><option value="hdmi">HDMI screen speaker</option><option value="hat">ReSpeaker HAT</option></select></label>;
  if(!ready)return <div className="device-setup"><p role="status">{message || "Loading saved settings…"}</p>{message && <button onClick={()=>{setMessage("");setRetry(value=>value+1);}}>Retry settings</button>}</div>;
  return <TouchInputProvider><div className="device-setup">
    {isLocation && <form onSubmit={event=>{event.preventDefault();void run(async()=>{
      const locationCoordinates=coordinates(form.latitude,form.longitude);
      if(demo){setMessage("Preview settings checked. Nothing was saved to a device.");onSaved?.();return;}
      await api("settings","PATCH",{
        weather_location_label:form.weather_location_label,timezone:form.timezone,
        orientation:form.orientation,...locationCoordinates,
        ...(section==="space"?{audio_output:form.audio_output}:{}),
      });
      setMessage("Settings saved. Weather refreshes automatically when a location is set.");
      onSaved?.();
    });}}><section><h2><CloudSun/> {section==="space"?"Location & display":"Location & orientation"}</h2>
      <TouchField label="Location name" maxLength={80} value={form.weather_location_label} onChange={value=>field("weather_location_label",value)} placeholder="Home" disabled={busy}/>
      <div className="setup-grid"><TouchField label="Latitude" mode="decimal" maxLength={14} value={form.latitude} onChange={value=>field("latitude",value)} placeholder="e.g. 34.05" disabled={busy}/><TouchField label="Longitude" mode="decimal" maxLength={14} value={form.longitude} onChange={value=>field("longitude",value)} placeholder="e.g. -118.24" disabled={busy}/></div>
      <p className="setup-note">Use your city’s coordinates; a street address is unnecessary. West longitudes need a minus sign (Stanford is about 37.426, −122.164). Coordinates go to Open-Meteo only for weather. Leave both blank to disable it.</p>
      {form.timezone.startsWith("America/") && Number(form.longitude)>0 && form.longitude.trim()!=="" && <p className="setup-note" role="alert">Check longitude: locations in the western Americas normally need a minus sign. A positive longitude forecasts the Eastern Hemisphere.</p>}
      <TouchField label="Timezone" required maxLength={80} value={form.timezone} onChange={value=>field("timezone",value)} placeholder="America/Los_Angeles" disabled={busy}/>
      <label>Display orientation<select value={form.orientation} onChange={e=>field("orientation",e.target.value)}><option value="landscape">Landscape</option><option value="portrait-clockwise">Portrait clockwise</option><option value="portrait-counterclockwise">Portrait counterclockwise</option></select></label>
      {section==="space" && speakerField}
      <button disabled={busy}><Check/> Save settings</button>
    </section></form>}
    {section==="privacy" && <section><h2><ShieldCheck/> Privacy PIN</h2><p>{pinConfigured?"A PIN is already saved. You can replace it here.":"Set a fallback PIN to show your calendar without your phone."}</p>
      <form onSubmit={event=>{event.preventDefault();void run(async()=>{const submitted=pin;setPin("");if(!demo)await api("security/pin","POST",{pin:submitted});setPinConfigured(true);setMessage(demo?"Preview PIN accepted; not stored.":"PIN saved.");onSaved?.();});}}><TouchField label="New PIN" secret mode="digits" pattern="[0-9]{4,8}" minLength={4} maxLength={8} required value={pin} autoComplete="new-password" onChange={setPin} disabled={busy}/><button disabled={busy}>Save PIN</button></form>
      {pinConfigured && <form onSubmit={event=>{event.preventDefault();void run(async()=>{const submitted=unlockPin;setUnlockPin("");if(!demo)await api("security/unlock","POST",{pin:submitted});setMessage(demo?"Preview unlock only.":"Private display unlocked for 15 minutes. Return to the dashboard.");});}}><TouchField label="Unlock with PIN" secret mode="digits" pattern="[0-9]{4,8}" minLength={4} maxLength={8} required value={unlockPin} onChange={setUnlockPin} disabled={busy}/><button disabled={busy}>Unlock for 15 minutes</button></form>}
    </section>}
    {section==="speaker" && <section><form onSubmit={event=>{event.preventDefault();void run(async()=>{
      if(!demo)await api("settings","PATCH",{audio_output:form.audio_output});
      setMessage(demo?"Preview only. Speaker output was not changed.":"Speaker output saved.");
    });}}>{speakerField}<button disabled={busy}>Save speaker output</button></form></section>}
    {section==="bluetooth" && <><BluetoothSetup demo={demo} pinConfigured={pinConfigured}/><section><details><summary>Advanced phone selection</summary><form onSubmit={event=>{event.preventDefault();void run(async()=>{if(!demo)await api("settings","PATCH",{phone_address:phoneAddress.trim() || null});setMessage(demo?"Preview phone selection only.":"Phone selection saved. Private content stays hidden until an authorized notification connection is established.");});}}><TouchField label="Previously paired iPhone address" placeholder="AA:BB:CC:DD:EE:FF" pattern="([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}" maxLength={17} value={phoneAddress} onChange={setPhoneAddress} disabled={busy}/><p className="setup-note">For administrator-managed bonds only. Leave blank to disable presence detection. This field never pairs or trusts a device.</p><button disabled={busy}>Save phone</button></form></details></section></>}
    {section==="iphone-remote" && <><TailscaleSetup demo={demo} pinConfigured={isRemoteSetup()?undefined:pinConfigured}/>{isRemoteSetup()&&<CompanionSetup demo={demo} pinConfigured={pinConfigured}/>}</>}
    {section==="shortcuts" && <><section><p>Use this token only with the private HTTPS command address listed under iPhone remote & Tailscale. Never send it over campus HTTP or share it. Hide it when finished.</p><button disabled={busy} onClick={()=>run(async()=>{setToken(demo?"Preview — no real token":(await api("security/lan-token")).token);})}>Show Shortcut token</button>{token && <><code className="setup-token">{token}</code><button onClick={()=>setToken("")}>Hide token</button></>}</section>
    <section><h2>Replace Shortcut token</h2><p className="setup-note">Use this if a token or Shortcut was shared accidentally. Existing Shortcuts stop working until updated with the new token.</p>
      {!confirmTokenReset?<button disabled={busy} onClick={()=>setConfirmTokenReset(true)}>Replace token…</button>:<>
        <button disabled={busy} onClick={()=>run(async()=>{setConfirmTokenReset(false);setToken(demo?"Preview — no real token":(await api("security/lan-token/rotate","POST")).token);setMessage(demo?"Preview only; no token changed.":"Old token revoked. The replacement is shown above; update your Shortcuts.");})}>Revoke old token and replace</button>
        <button disabled={busy} onClick={()=>setConfirmTokenReset(false)}>Cancel</button>
      </>}
    </section></>}
    {section==="diagnostics" && <section><h2>Device check</h2><button disabled={busy} onClick={()=>run(async()=>setDiagnostics(demo?{mode:"Preview",hardware:"Not connected",calendar:"Sample data",weather:"Sample data"}:await api("diagnostics")))}>Run diagnostics</button>{diagnostics && <pre className="setup-diagnostics">{JSON.stringify(diagnostics,null,2)}</pre>}</section>}
    {message && <p className="setup-message" role="status">{message}</p>}
  </div></TouchInputProvider>;
}
