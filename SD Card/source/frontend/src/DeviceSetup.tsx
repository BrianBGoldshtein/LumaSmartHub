import { useEffect, useState } from "react";
import {useSetupActivity} from "./setupActivity";
import { ArrowLeft, Check, CloudSun, Settings, ShieldCheck, Smartphone } from "lucide-react";
import {VoiceSetup} from "./VoiceSetup";
import {NetworkSetup} from "./NetworkSetup";
import {BluetoothSetup} from "./BluetoothSetup";
import {TailscaleSetup} from "./TailscaleSetup";
import {PiConnectSetup} from "./PiConnectSetup";
import {TouchField,TouchInputProvider} from "./TouchField";
import {UpdateSetup} from "./UpdateSetup";
import {coordinates} from "./touchInput";
import {setupTheme,setupLink} from "./setupTheme";

async function api(path:string, method="GET", body?:unknown) {
  const response=await fetch(`/api/v1/${path}`,{method,headers:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();
  if(!response.ok) throw new Error(typeof data.detail === "string" ? data.detail : "Check the entered settings.");
  return data;
}

export function DeviceSetup({demo,section,onSaved}:{demo:boolean;section?:"space"|"privacy";onSaved?:()=>void}) {
  const [theme,setTheme]=useState(()=>setupTheme(new URLSearchParams(location.search).get("theme")));
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
  const [ready,setReady]=useState(demo),[retry,setRetry]=useState(0);
  useSetupActivity(busy);
  useEffect(()=>{
    if(demo) return;
    Promise.all([api("settings"),api("security/status")]).then(([settings,security])=>{
      setForm({weather_location_label:settings.weather_location_label,latitude:settings.latitude?.toString() || "",longitude:settings.longitude?.toString() || "",timezone:settings.timezone,orientation:settings.orientation,audio_output:settings.audio_output || "auto"});
      setPinConfigured(security.pin_configured);
      setTheme(setupTheme(settings.theme));
      setPhoneAddress(settings.phone_address || "");
      setReady(true);
    }).catch(error=>setMessage(error.message));
  },[demo,retry]);
  async function run(action:()=>Promise<void>) {
    setBusy(true);setMessage("");
    try {await action();}catch(error){setMessage(error instanceof Error ? error.message : "Please try again.");}finally{setBusy(false);}
  }
  const field=(name:keyof typeof form,value:string)=>setForm(previous=>({...previous,[name]:value}));
  const Panel=section?"div":"main";
  if(!ready)return <div className="device-setup"><p role="status">{message || "Loading saved settings…"}</p>{message && <button onClick={()=>{setMessage("");setRetry(value=>value+1);}}>Retry settings</button>}</div>;
  return <TouchInputProvider><div className={section?"setup-embedded":`app theme-${theme} setup-page`}>{!section && <a className="setup-back" href={setupLink(demo,theme)}><ArrowLeft/> Dashboard</a>}<Panel className={section?"device-setup":"setup-content device-setup"}>
    {!section && <><Settings size={40}/><h1>Your space.</h1><p>Set up once. Saved on your Luma.</p><a href={setupLink(demo,theme,"onboarding")}>Open guided setup →</a>
    {demo && <p className="setup-note">Preview only — no device settings will change.</p>}
    <NetworkSetup demo={demo}/></>}
    {(!section || section==="space") && <form onSubmit={event=>{event.preventDefault();void run(async()=>{
      const locationCoordinates=coordinates(form.latitude,form.longitude);
      if(demo){setMessage("Preview settings checked. Nothing was saved to a device.");onSaved?.();return;}
      await api("settings","PATCH",{...form,...locationCoordinates});
      setMessage("Settings saved. Weather refreshes automatically when a location is set.");
      onSaved?.();
    });}}><section><h2><CloudSun/> Location & display</h2>
      <TouchField label="Location name" maxLength={80} value={form.weather_location_label} onChange={value=>field("weather_location_label",value)} placeholder="Home" disabled={busy}/>
      <div className="setup-grid"><TouchField label="Latitude" mode="decimal" maxLength={14} value={form.latitude} onChange={value=>field("latitude",value)} placeholder="e.g. 34.05" disabled={busy}/><TouchField label="Longitude" mode="decimal" maxLength={14} value={form.longitude} onChange={value=>field("longitude",value)} placeholder="e.g. -118.24" disabled={busy}/></div>
      <p className="setup-note">Use your city’s coordinates; a street address is unnecessary. West longitudes need a minus sign (Stanford is about 37.426, −122.164). Coordinates go to Open-Meteo only for weather. Leave both blank to disable it.</p>
      {form.timezone.startsWith("America/") && Number(form.longitude)>0 && form.longitude.trim()!=="" && <p className="setup-note" role="alert">Check longitude: locations in the western Americas normally need a minus sign. A positive longitude forecasts the Eastern Hemisphere.</p>}
      <TouchField label="Timezone" required maxLength={80} value={form.timezone} onChange={value=>field("timezone",value)} placeholder="America/Los_Angeles" disabled={busy}/>
      <label>Display orientation<select value={form.orientation} onChange={e=>field("orientation",e.target.value)}><option value="landscape">Landscape</option><option value="portrait-clockwise">Portrait clockwise</option><option value="portrait-counterclockwise">Portrait counterclockwise</option></select></label>
      <label>Speaker output<select value={form.audio_output} onChange={e=>field("audio_output",e.target.value)}><option value="auto">System default</option><option value="hdmi">HDMI screen speaker</option><option value="hat">ReSpeaker HAT</option></select></label>
      <button disabled={busy}><Check/> Save settings</button>
    </section></form>}
    {(!section || section==="privacy") && <section><h2><ShieldCheck/> Privacy PIN</h2><p>{pinConfigured?"A PIN is already saved. You can replace it here.":"Set a fallback PIN to show your calendar without your phone."}</p>
      <form onSubmit={event=>{event.preventDefault();void run(async()=>{const submitted=pin;setPin("");if(!demo)await api("security/pin","POST",{pin:submitted});setPinConfigured(true);setMessage(demo?"Preview PIN accepted; not stored.":"PIN saved.");onSaved?.();});}}><TouchField label="New PIN" secret mode="digits" pattern="[0-9]{4,8}" minLength={4} maxLength={8} required value={pin} autoComplete="new-password" onChange={setPin} disabled={busy}/><button disabled={busy}>Save PIN</button></form>
      {pinConfigured && <form onSubmit={event=>{event.preventDefault();void run(async()=>{const submitted=unlockPin;setUnlockPin("");if(!demo)await api("security/unlock","POST",{pin:submitted});setMessage(demo?"Preview unlock only.":"Private display unlocked for 15 minutes. Return to the dashboard.");});}}><TouchField label="Unlock with PIN" secret mode="digits" pattern="[0-9]{4,8}" minLength={4} maxLength={8} required value={unlockPin} onChange={setUnlockPin} disabled={busy}/><button disabled={busy}>Unlock for 15 minutes</button></form>}
    </section>}
    {!section && <><section><h2><Smartphone/> Connections</h2><a href={setupLink(demo,theme,"google")}>Connect Google Calendar →</a>
      <details><summary>Advanced phone selection</summary><form onSubmit={event=>{event.preventDefault();void run(async()=>{if(!demo)await api("settings","PATCH",{phone_address:phoneAddress.trim() || null});setMessage(demo?"Preview phone selection only.":"Phone selection saved. Private content stays hidden until an authorized notification connection is established.");});}}><TouchField label="Previously paired iPhone address" placeholder="AA:BB:CC:DD:EE:FF" pattern="([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}" maxLength={17} value={phoneAddress} onChange={setPhoneAddress} disabled={busy}/><p className="setup-note">For administrator-managed bonds only. Leave blank to disable presence detection. This field never pairs or trusts a device.</p><button disabled={busy}>Save phone</button></form></details>
      <p>Use this token only with the private HTTPS command address configured below. Never send it over campus HTTP or share it. Hide it when finished.</p><button disabled={busy} onClick={()=>run(async()=>{setToken(demo?"Preview — no real token":(await api("security/lan-token")).token);})}>Show Shortcut token</button>{token && <><code className="setup-token">{token}</code><button onClick={()=>setToken("")}>Hide token</button></>}</section>
    <section><h2>Replace Shortcut token</h2><p className="setup-note">Use this if a token or Shortcut was shared accidentally. Existing Shortcuts stop working until updated with the new token.</p>
      {!confirmTokenReset?<button disabled={busy} onClick={()=>setConfirmTokenReset(true)}>Replace token…</button>:<>
        <button disabled={busy} onClick={()=>run(async()=>{setConfirmTokenReset(false);setToken(demo?"Preview — no real token":(await api("security/lan-token/rotate","POST")).token);setMessage(demo?"Preview only; no token changed.":"Old token revoked. The replacement is shown in Connections above; update your Shortcuts.");})}>Revoke old token and replace</button>
        <button disabled={busy} onClick={()=>setConfirmTokenReset(false)}>Cancel</button>
      </>}
    </section>
    <PiConnectSetup demo={demo}/>
    <UpdateSetup demo={demo}/>
    <TailscaleSetup demo={demo}/>
    <BluetoothSetup demo={demo} pinConfigured={pinConfigured}/>
    <VoiceSetup demo={demo}/>
    <section><h2>Device check</h2><button disabled={busy} onClick={()=>run(async()=>setDiagnostics(demo?{mode:"Preview",hardware:"Not connected",calendar:"Sample data",weather:"Sample data"}:await api("diagnostics")))}>Run diagnostics</button>{diagnostics && <pre className="setup-diagnostics">{JSON.stringify(diagnostics,null,2)}</pre>}</section>
    <a href={setupLink(demo,theme,"onboarding")}>Review guided setup →</a></>}
    {!section && <p><a href={setupLink(demo,theme,"extras")}>New: daily rhythm & extras →</a></p>}
    {message && <p className="setup-message" role="status">{message}</p>}
  </Panel></div></TouchInputProvider>;
}
