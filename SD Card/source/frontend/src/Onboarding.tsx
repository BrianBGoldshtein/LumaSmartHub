import {useCallback,useEffect,useRef,useState} from "react";
import {ArrowLeft,ArrowRight,Check,MicOff,ShieldCheck} from "lucide-react";
import {DeviceSetup} from "./DeviceSetup";
import {GoogleSetup} from "./GoogleSetup";
import {NetworkSetup} from "./NetworkSetup";
import {BluetoothSetup} from "./BluetoothSetup";
import {VoiceSetup} from "./VoiceSetup";
import {TailscaleSetup} from "./TailscaleSetup";
import {ExtrasSetup} from './ExtrasSetup';
import {TouchInputProvider} from "./TouchField";
import {setupTheme,setupLink} from "./setupTheme";
import {restoreSetup,demoTransition,setupSteps,optionalSteps,setupCopy,type SetupProgress,type SetupStep} from "./onboardingState";
import type {Theme} from "./types";
import {SetupActivity} from "./setupActivity";
import "./onboarding.css";

const demoKey="luma.onboarding.preview.v1";
type Summary={weather:boolean;pin:boolean;google:boolean;phone_selected:boolean;voice_enabled:boolean;weather_nudges_enabled?:boolean;timer_focus_minutes?:number;timer_break_minutes?:number;departure_enabled?:boolean;departure_calendars?:number;night_clock_enabled?:boolean;night_brightness?:number;countdowns?:number;public_countdowns?:number;transit_stops?:number;public_transit_stops?:number;transit_token?:boolean;purifier_session?:boolean;purifier_selected?:boolean;room_recovery?:boolean;fan_outputs?:number;fan_checks?:boolean;fan_recovery?:boolean;scenes_enabled?:number;scenes_automatic?:number;scenes_recovery?:boolean};
async function request(path:string,method="GET",body?:unknown){
  const response=await fetch(`/api/v1/${path}`,{method,cache:"no-store",headers:{"Content-Type":"application/json"},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw Error(typeof data.detail==="string"?data.detail:"Could not save. Please try again.");return data;
}
export function Onboarding({demo,locked=false}:{demo:boolean;locked?:boolean}){
  const [progress,setProgress]=useState<SetupProgress>(restoreSetup(null));
  const [theme,setTheme]=useState<Theme>(()=>setupTheme(new URLSearchParams(location.search).get("theme")));
  const [summary,setSummary]=useState<Summary>();
  const [loaded,setLoaded]=useState(false),[saving,setBusy]=useState(false),[error,setError]=useState("");
  const [childBusy,setChildBusy]=useState(false);
  const busy=saving || childBusy;
  const [dirty,setDirty]=useState(false),[pending,setPending]=useState<{action:string;step?:SetupStep}>();
  const [notice,setNotice]=useState("");
  const heading=useRef<HTMLHeadingElement>(null);
  const edited=useCallback(()=>{if(["space","privacy","calendar","extras"].includes(progress.step))setDirty(true);},[progress.step]);
  async function load(){
    setError("");setLoaded(false);
    try{
      if(demo){
        let saved:unknown=null;try{saved=JSON.parse(localStorage.getItem(demoKey) || "null");}catch{/* Preview storage can be unavailable. */}
        const restored=restoreSetup(saved), requested=new URLSearchParams(location.search).get("step");
        if(setupSteps.includes(requested as SetupStep))restored.step=requested as SetupStep;
        setProgress(restored);setSummary({weather:false,pin:false,google:false,phone_selected:false,voice_enabled:true});
      }else{
        const [state,settings]=await Promise.all([request("onboarding"),request("settings")]);
        setProgress(restoreSetup(state));setSummary(state.summary);setTheme(setupTheme(settings.theme));
      }
      setLoaded(true);
    }catch(e){setError(e instanceof Error?e.message:"Setup unavailable.");}
  }
  useEffect(()=>{void load();},[demo]);
  useEffect(()=>{if(loaded){heading.current?.focus({preventScroll:true});document.querySelector(".onboarding-shell")?.scrollTo(0,0);}},[progress.step,loaded]);
  useEffect(()=>{
    const warn=(event:BeforeUnloadEvent)=>{if(dirty){event.preventDefault();event.returnValue="";}};
    window.addEventListener("beforeunload",warn);return()=>window.removeEventListener("beforeunload",warn);
  },[dirty]);
  async function move(action:string,step?:SetupStep,discard=false){
    if(busy)return;
    if(dirty && !discard){setPending({action,step});return;}
    setBusy(true);setError("");setNotice("");setPending(undefined);
    try{
      const next=demo?demoTransition(progress,action,step):await request("onboarding","POST",{action,...(step?{step}:{})});
      if(demo)try{localStorage.setItem(demoKey,JSON.stringify(next));}catch{setNotice("Preview storage is unavailable; progress lasts until this page closes.");}
      setProgress(restoreSetup(next));if(!demo)setSummary(next.summary);setDirty(false);
      if(action==="finish")location.assign(setupLink(demo,theme));
    }catch(e){setError(e instanceof Error?e.message:"Your previous step is still saved. Try again.");}finally{setBusy(false);}
  }
  async function chooseTheme(value:Theme){
    setBusy(true);setError("");try{if(!demo)await request("settings","PATCH",{theme:value});setTheme(value);}catch(e){setError(String((e as Error).message));}finally{setBusy(false);}
  }
  async function mute(){
    setBusy(true);setError("");try{if(!demo)await request("settings","PATCH",{voice_enabled:false});setSummary(current=>current?{...current,voice_enabled:false}:current);}catch(e){setError(String((e as Error).message));}finally{setBusy(false);}
  }
  const step=progress.step,copy=setupCopy[step],index=setupSteps.indexOf(step);
  const phase=step==="welcome"?0:["network","space","privacy"].includes(step)?1:step==="review"?3:2;
  const saved=()=>{setDirty(false);setPending(undefined);setNotice(demo?"Preview checked — no device changes.":"Saved on Luma.");};
  return <SetupActivity.Provider value={{busy:setChildBusy,edited}}><TouchInputProvider><div className={`app theme-${theme} setup-page onboarding-shell`}>
    <header className="onboarding-top"><span className="onboarding-brand">Luma <span> / setup</span></span><span>{demo?"Interactive preview":"Progress saved on this device"}</span></header>
    <div className="onboarding-layout">
      <aside className="onboarding-rail" aria-label="Setup stages"><ol>{["Welcome","Essentials","Make it yours","Ready"].map((label,i)=><li key={label} aria-current={phase===i?"step":undefined}><span>{i<phase?<Check aria-hidden="true"/>:String(i+1).padStart(2,"0")}</span>{label}</li>)}</ol><p>One step at a time.<br/>Connections are optional.</p><a href={setupLink(demo,theme,"device")} onClick={event=>{if(dirty || busy){event.preventDefault();setError(busy?"Finish or cancel the current operation first.":"Save your edits before opening all settings.");}}}>All settings</a></aside>
      <main className="onboarding-main">
        <p className="onboarding-kicker">{phase===1?`Essentials · ${index} of 3`:phase===2?"Make it yours · optional":phase===3?"Your setup summary":"Welcome home"}</p>
        <h1 ref={heading} tabIndex={-1}>{copy.title}</h1><p className="onboarding-intro">{copy.description}</p>
        {error && <div className="onboarding-alert" role="alert">{error}{!loaded && <button onClick={()=>void load()}>Retry connection</button>}</div>}
        {!loaded && !error && <p role="status">Loading your saved progress…</p>}
        {loaded && <>
          <div className="onboarding-body device-setup" key={step} onChangeCapture={()=>{if(["space","privacy","calendar","extras"].includes(step))setDirty(true);}}>
            {step==="welcome" && <>
              <div className="onboarding-themes" aria-label="Choose a theme">{(["luma-glass","hearth","neon-grid"] as Theme[]).map((value,i)=><button key={value} className={`theme-choice choice-${value}`} disabled={busy} aria-pressed={theme===value} onClick={()=>void chooseTheme(value)}><span className="theme-specimen" aria-hidden="true">12:48</span><strong>{["Luma Glass","Hearth","Neon Grid"][i]}</strong><span>{["Cool & clear","Warm & quiet","Pixel & playful"][i]}</span></button>)}</div>
              <div className="onboarding-note"><ShieldCheck aria-hidden="true"/><div><strong>Your room. Your information.</strong><p>Accounts stay on the Pi. Private cards stay hidden until your nearby phone or PIN unlocks them. You can finish without connecting an account.</p></div></div>
              <div className="onboarding-note"><div><strong>Hey Luma is {summary?.voice_enabled?"on":"off"}.</strong><p>When enabled, speech is processed locally. Luma does not save recordings. Calibration comes later.</p></div>{summary?.voice_enabled && <button disabled={busy} onClick={()=>void mute()}><MicOff/> Turn microphone off</button>}</div>
            </>}
            {step==="network" && <NetworkSetup demo={demo}/>}
            {step==="extras" && <ExtrasSetup demo={demo} embedded onSaved={saved} locked={locked}/>}
            {step==="space" && <DeviceSetup demo={demo} section="space" onSaved={saved}/>}
            {step==="privacy" && <><p className="onboarding-note">No phone or PIN? Time and weather still work. Remote Siri commands never unlock your private calendar.</p><DeviceSetup demo={demo} section="privacy" onSaved={saved}/></>}
            {step==="calendar" && <GoogleSetup demo={demo} embedded onSaved={saved}/>}
            {step==="phone" && <BluetoothSetup demo={demo}/>}
            {step==="voice" && <VoiceSetup demo={demo}/>}
            {step==="remote" && <><TailscaleSetup demo={demo}/><p className="setup-note">The Shortcut token is under Connections in <a href={setupLink(demo,theme,"device")}>All settings</a>. Your place here is saved.</p></>}
            {step==="review" && <>
              <div className="onboarding-review">{([["weather","Weather","Location saved","Add a location"],["pin","Privacy PIN","PIN saved","Not configured"],["google","Google Calendar","Account connected","Connect later"],["phone_selected","Nearby iPhone","Phone selected · presence still required","Pair later"],["voice_enabled","Hey Luma","Enabled · room check still required","Microphone off"]] as const).map(([key,label,yes,no])=><div key={key}><strong>{label}</strong><span>{demo?"Sample preview only":summary?.[key]?yes:no}</span></div>)}
                <div><strong>Focus / break</strong><span>{demo?'Sample preview only':`${summary?.timer_focus_minutes ?? 25} / ${summary?.timer_break_minutes ?? 5} min · Local timers`}</span></div>
                <div><strong>Weather hints</strong><span>{demo?'Sample preview only':summary?.weather_nudges_enabled?summary.weather?'Enabled · fresh forecast required':'Enabled · add a location':'Off · optional'}</span></div>
                <div><strong>Leave soon</strong><span>{demo?'Sample preview only':summary?.departure_enabled?`${summary.departure_calendars ?? 0} calendars · fresh Google sync required`:'Off · optional'}</span></div>
                <div><strong>Night & wake</strong><span>{demo?'Sample preview only':summary?.night_clock_enabled?`Clock · ${summary.night_brightness ?? 5}% · panel check required`:'Screen off during sleep · panel check required'}</span></div>
                <div><strong>Important dates</strong><span>{demo?'Sample preview only':`${summary?.countdowns??0} saved · ${summary?.public_countdowns??0} public in standby`}</span></div>
                <div><strong>Transit</strong><span>{demo?'Sample preview only':`${summary?.transit_stops??0} stops · ${summary?.public_transit_stops??0} public · ${summary?.transit_token?'token saved, feed access still required':'no token'}`}</span></div>
                <div><strong>Room devices</strong><span>{demo?'Sample preview only':summary?.room_recovery?'Settings need recovery':summary?.purifier_selected?'Purifier selected · physical check still required':summary?.purifier_session?'VeSync session saved · choose a purifier':'Not connected · optional'}</span></div>
                <div><strong>Fans</strong><span>{demo?'Sample preview only':summary?.fan_recovery?'Settings need recovery':`${summary?.fan_outputs??0}/2 outputs saved · ${summary?.fan_checks?'owner-recorded checks saved':'independent-operation checks needed'}`}</span></div>
                <div><strong>Scenes</strong><span>{demo?'Sample preview only':summary?.scenes_recovery?'Settings need recovery':`${summary?.scenes_enabled??0} enabled · ${summary?.scenes_automatic??0} automatic triggers · remote access off`}</span></div>
              </div>
              <p className="onboarding-note">This is a configuration review, not a hardware pass. Display, audio, campus access and phone controls still need checks on the assembled Pi. Private commands are verified in their own setup panel.</p>
              <details><summary>Return to a setup step</summary><div className="onboarding-revisit">{setupSteps.slice(0,-1).map(key=><button key={key} disabled={busy} onClick={()=>void move("visit",key)}>{setupCopy[key].label}<span>{progress.statuses[key]==="later"?"Saved for later":progress.statuses[key]==="reviewed"?"Reviewed":"Not reviewed"}</span></button>)}</div></details>
              <p className="onboarding-note">Focus timers are ready in dashboard controls. Daily rhythm, dates, transit, the purifier and fan learning have optional settings in Extras. Scenes and USB recovery are still in development. No appliance automation is enabled by finishing setup.</p>
            </>}
          </div>
          {notice && <p className="onboarding-save" role="status">{notice}</p>}
          {pending && <div className="onboarding-alert" role="alert"><strong>These edits haven’t been saved.</strong><p>Save in the panel above, or leave this step without those edits. Password and PIN drafts are never saved.</p><button onClick={()=>setPending(undefined)}>Keep editing</button><button onClick={()=>void move(pending.action,pending.step,true)}>Discard edits and continue</button></div>}
          {childBusy && <p role="status">Finish or cancel the operation above before continuing.</p>}
          <footer className="onboarding-actions">
            {index>0 && <button disabled={busy} onClick={()=>void move("visit",setupSteps[index-1])}><ArrowLeft/> Back</button>}
            {optionalSteps.includes(step) && <button disabled={busy} onClick={()=>void move("later",step)}>Set up later</button>}
            <button className="onboarding-primary" disabled={busy} onClick={()=>void move(step==="review"?"finish":"continue",step==="review"?undefined:step)}>{busy?saving?"Saving…":"In progress…":step==="welcome"?"Get started":step==="review"?"Open my dashboard":"Continue"}<ArrowRight/></button>
          </footer>
          {optionalSteps.includes(step) && <button className="onboarding-skip" disabled={busy} onClick={()=>void move("skip_optional")}>Finish the rest later →</button>}
        </>}
      </main>
    </div>
  </div></TouchInputProvider></SetupActivity.Provider>;
}
