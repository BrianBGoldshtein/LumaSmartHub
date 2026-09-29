import {useContext,useEffect,useLayoutEffect,useRef,useState} from 'react';
import {Wind} from 'lucide-react';
import {SetupActivity} from './setupActivity';
import {TouchField} from './TouchField';
import {scrollSetupToTop} from './setupScroll';
import {useConfirmKeyboard} from './useConfirmKeyboard';
import {emptyRoom,sampleRoom,samplePurifier,purifierStatus,purifierFresh,supportsPurifier,commandStatus,type RoomConfig,type PurifierDevice,type PurifierAction} from './roomState';
import './room.css';

type Step='overview'|'prepare'|'login'|'discover'|'review';
type Confirmation='discard'|'disconnect'|'unselect'|null;
class RoomError extends Error {status:number;constructor(message:string,status:number){super(message);this.status=status;}}
async function api(path='',body?:unknown){
  const controller=new AbortController(),deadline=setTimeout(()=>controller.abort(),30000);
  try{
    const response=await fetch(`/api/v1/room${path}`,{method:body===undefined?'GET':'POST',signal:controller.signal,cache:'no-store',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await response.json();
    if(!response.ok)throw new RoomError(typeof data.detail==='string'?data.detail:'Room devices could not respond. Reload saved state before trying again.',response.status);
    return data;
  }finally{clearTimeout(deadline);}
}

export function RoomSetup({demo,onDirty,onBusy,onSaved}:{demo:boolean;onDirty:(value:boolean)=>void;onBusy:(value:boolean)=>void;onSaved?:()=>void}){
  const activity=useContext(SetupActivity),alive=useRef(true),working=useRef(false),panel=useRef<HTMLDivElement>(null);
  const [config,setConfig]=useState<RoomConfig>(emptyRoom),[ready,setReady]=useState(demo),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const [step,setStep]=useState<Step>('overview'),[confirm,setConfirm]=useState<Confirmation>(null);
  const confirmPanel=useConfirmKeyboard(!!confirm,()=>{if(!busy)setConfirm(null);});
  const [username,setUsername]=useState(''),[password,setPassword]=useState(''),[country,setCountry]=useState('US'),[reviewed,setReviewed]=useState(false);
  const [rows,setRows]=useState<PurifierDevice[]>([]),[discovered,setDiscovered]=useState(false),[choice,setChoice]=useState<PurifierDevice|null>(null),[name,setName]=useState('');
  const [now,setNow]=useState(Date.now()),[discoverAfter,setDiscoverAfter]=useState(0);
  const dirty=!!username||!!password||country!=='US'||!!choice;
  useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
  useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
  useLayoutEffect(()=>scrollSetupToTop(panel.current),[step]);
  useEffect(()=>{alive.current=true;if(!demo)void load();return()=>{alive.current=false;};},[demo]);
  useEffect(()=>{const timer=setInterval(()=>setNow(Date.now()),1000);return()=>clearInterval(timer);},[]);
  // Local cached state only: this never triggers a provider request. Don't replace
  // an in-progress form or overlap owner operations; privacy unmounts this panel.
  useEffect(()=>{if(demo||step!=='overview'||!ready)return;const timer=setInterval(()=>{if(!working.current)void load(false);},15000);return()=>clearInterval(timer);},[demo,step,ready]);
  function resetDraft(){setUsername('');setPassword('');setCountry('US');setReviewed(false);setChoice(null);setName('');setRows([]);setDiscovered(false);setConfirm(null);}
  function leave(){resetDraft();setStep('overview');setMessage('');}
  function back(){if(dirty)setConfirm('discard');else leave();}
  async function run(action:()=>Promise<void>){
    if(working.current)return;working.current=true;setBusy(true);setMessage('');
    try{await action();}catch(e){if(alive.current){
      const error=e as Error;
      if(e instanceof RoomError&&e.status===403){resetDraft();setConfig(emptyRoom());setReady(false);setStep('overview');}
      else if(e instanceof RoomError){
        // A provider failure can invalidate the last reading. Re-read only the
        // local saved state so stale controls disappear without retrying VeSync.
        try{const latest:RoomConfig=await api();if(alive.current){setConfig(latest);setReady(true);}}
        catch{if(alive.current){setConfig(emptyRoom());setReady(false);setMessage('Could not reload saved room state. Check the purifier before sending another command.');}return;}
      }
      if(!alive.current)return;
      // A lost response must never imply a command failed or invite auto-replay.
      if(!(e instanceof RoomError)){setConfig(emptyRoom());setReady(false);setMessage('Connection interrupted. Nothing will be retried automatically. Reload saved state and check the purifier before sending another command.');}
      else setMessage(error.message);
    }}finally{working.current=false;if(alive.current)setBusy(false);}
  }
  async function load(show=true){await run(async()=>{const value=await api();if(alive.current){setConfig(value);setReady(true);if(show)setMessage('Saved configuration loaded.');}});}
  function saved(value:RoomConfig,notice:string){if(!alive.current)return;setConfig(value);leave();setReady(true);setMessage(notice);onSaved?.();}
  async function login(){
    if(!reviewed||!username.trim()||!password||!/^[A-Z]{2}$/.test(country))return;
    const credentials={username:username.trim(),password,country,revision:config.revision};
    setPassword('');
    await run(async()=>{const value:RoomConfig=demo?{...emptyRoom(),revision:'sample-only',connected:true}:await api('/vesync/login',credentials);
      // The service spaces VeSync setup requests by five seconds. Make the
      // first discovery available after that interval instead of inviting an
      // immediate, predictable rate-limit error during onboarding.
      setDiscoverAfter(demo?0:Date.now()+5500);
      saved(value,demo?'Sample session only. No credentials sent or saved.':'VeSync session saved. Discover your purifier next.');});
  }
  async function discover(){
    setStep('discover');setRows([]);setDiscovered(false);
    await run(async()=>{const value=demo?{devices:[samplePurifier]}:await api('/purifier/discover',{revision:config.revision});if(alive.current){setRows(value.devices);setDiscovered(true);}});
  }
  async function select(){if(!choice||!name.trim())return;await run(async()=>{
    const value=demo?sampleRoom():await api('/purifier/select',{revision:config.revision,device_id:choice.id,name:name.trim()});
    if(demo){value.selected={...choice,name:name.trim()};value.purifier!.device=value.selected;}
    saved(value,demo?'Sample purifier selected. No hardware checked.':'Purifier selected and reported state checked. No control command sent.');
  });}
  async function refresh(){await run(async()=>{const value=demo?{...sampleRoom(),selected:config.selected,purifier:{...sampleRoom().purifier!,device:config.selected!}}:await api('/purifier/refresh',{});if(alive.current){setConfig(value);setMessage(demo?'Sample reading refreshed.':'Reported state checked.');}});}
  async function command(action:PurifierAction,value:boolean|number|string){
    if(!supportsPurifier(config.purifier,action,value,Date.now()))return;
    await run(async()=>{
      if(demo){const next=structuredClone(config),state=next.purifier!.state!;if(action==='power')state.power=value as boolean;else if(action==='display')state.display_setting=value as boolean;else if(action==='speed'){state.speed=value as number;state.mode='manual';state.power=true;}else{state.mode=value as string;state.power=true;}next.purifier!.reported_at=new Date().toISOString();setConfig(next);setMessage('Sample action only. No purifier command sent.');return;}
      const result=await api('/purifier/command',{revision:config.revision,action,value});
      if(alive.current){setConfig(result.configuration);setMessage(result.result.message);}
    });
  }
  async function confirmAction(){
    if(confirm==='discard'){leave();onSaved?.();return;}
    await run(async()=>{const disconnect=confirm==='disconnect';const value=demo?{...emptyRoom(),revision:'sample-only',connected:!disconnect}:await api(disconnect?'/vesync/disconnect':'/purifier/select',{revision:config.revision,...(!disconnect?{device_id:null}:{})});saved(value,disconnect?'VeSync disconnected. This does not switch off the purifier.':'Purifier unselected. This does not switch it off.');});
  }
  const view=config.purifier,fresh=purifierFresh(view,now),caps=fresh?view?.capabilities:null;
  return <div ref={panel} className="room-setup"><h2><Wind aria-hidden="true"/> Your room</h2>
    {demo&&<p className="setup-note">Interactive sample · no account, network or appliance changes. Use made-up credentials only.</p>}
    {!ready?<><p>Load saved room settings to continue.</p><button disabled={busy} onClick={()=>void load()}>Reload saved state</button></>:config.recovery_error?<p role="alert">Room settings need recovery. Nothing was overwritten; device commands are disabled.</p>:<>
      {step!=='overview'&&<button disabled={busy} onClick={back}>← Back to room devices</button>}
      {step==='overview'?<>
        <p>One selected purifier. Private controls, on this hub.</p>
        <div className="room-device-card"><h3>{config.selected?.name||'Levoit Core 300S'}</h3><p className="room-status">{view?purifierStatus(view,now):config.connected?'Account saved · choose a purifier':'Not connected'}</p>
          {view&&<><p className="setup-note">{view.device.model}{view.reported_at?` · ${fresh?'Read':'Last reading'} ${new Date(view.reported_at).toLocaleTimeString([], {hour:'numeric',minute:'2-digit'})}`:''}</p>
            {view.state&&<dl className="room-readings"><div><dt>{fresh?'Power':'Last power'}</dt><dd>{view.state.power?'On':'Off'}</dd></div><div><dt>Mode</dt><dd>{view.state.mode}</dd></div>{view.state.speed!==null&&<div><dt>Fan speed</dt><dd>{view.state.speed}</dd></div>}<div><dt>Filter remaining</dt><dd>{view.state.filter_percent}%</dd></div>{view.state.pm25!==null&&<div><dt>PM2.5 · µg/m³</dt><dd>{view.state.pm25}</dd></div>}{view.state.display_setting!==null&&<div><dt>Display setting</dt><dd>{view.state.display_setting?'On':'Off'}</dd></div>}</dl>}
            <p className="setup-note">{commandStatus(view.last_command)}</p>
            {!fresh&&<p>Controls need a fresh reading. Background checks run about every two minutes, with longer waits after errors.</p>}
            {caps&&<fieldset className="room-controls" disabled={busy}><legend>Purifier controls</legend>
              {caps.power&&<div className="room-actions"><button onClick={()=>void command('power',true)}>Power on</button><button onClick={()=>void command('power',false)}>Power off</button></div>}
              {!!caps.speeds.length&&<div className="room-actions" aria-label="Fan speed">{caps.speeds.map(speed=><button key={speed} onClick={()=>void command('speed',speed)}>Speed {speed}</button>)}</div>}
              {!!caps.modes.length&&<div className="room-actions" aria-label="Purifier mode">{caps.modes.map(mode=><button key={mode} onClick={()=>void command('mode',mode)}>{mode==='auto'?'Auto':mode==='sleep'?'Sleep':'Manual'} mode</button>)}</div>}
              {(!!caps.speeds.length||!!caps.modes.length)&&<p className="setup-note">Changing speed or mode can turn the purifier on. Commands are sent once, then checked; no offline queue.</p>}
              {caps.display&&<div className="room-actions"><button onClick={()=>void command('display',true)}>Purifier display on</button><button onClick={()=>void command('display',false)}>Purifier display off</button></div>}
            </fieldset>}
          </>}
          <div className="room-actions"><button disabled={busy} onClick={()=>{setStep('prepare');setReviewed(false);}}>{config.connected?'Reconnect VeSync':'Connect VeSync'}</button>{config.connected&&<button disabled={busy||now<discoverAfter} onClick={()=>void discover()}>{now<discoverAfter?`Find my purifier in ${Math.ceil((discoverAfter-now)/1000)}s`:config.selected?'Choose another purifier':'Find my purifier'}</button>}{view&&<button disabled={busy} onClick={()=>void refresh()}>Check reported state</button>}</div>
          {config.connected&&<details><summary>Disconnect or change selection</summary><p>This only removes Luma’s connection or selection. The purifier keeps its current settings.</p><div className="room-actions">{config.selected&&<button disabled={busy} onClick={()=>setConfirm('unselect')}>Unselect purifier</button>}<button disabled={busy} onClick={()=>setConfirm('disconnect')}>Disconnect VeSync</button></div></details>}
        </div>
        <p className="setup-note">Connecting the purifier does not enable any scene or remote control. Set up each Woozoo separately in Two fans; infrared commands remain unconfirmed until you observe the fan.</p>
      </>:step==='prepare'?<>
        <h3>First, connect in VeSync</h3><ol className="room-prerequisites"><li>Enroll your Core 300S / 300S-P in the official VeSync app on your phone.</li><li>Use a permitted network that the purifier supports. Stanford Visitor’s terms page and eduroam are not assumed compatible with this appliance; check with campus support.</li><li>Confirm that the VeSync app can read and control that purifier.</li></ol>
        <p>Luma uses an unofficial, cloud-dependent integration. Your sign-in is sent to VeSync over HTTPS. Only the resulting session is saved privately on this hub—not your password.</p>
        {config.connected&&<p className="setup-note">A successful reconnection replaces the saved session and clears the current purifier selection. A failed sign-in leaves it unchanged.</p>}
        <label className="extras-toggle"><input type="checkbox" checked={reviewed} disabled={busy} onChange={event=>setReviewed(event.target.checked)}/><span>I have set up VeSync on a permitted network and understand the cloud connection.</span></label>
        <button disabled={busy||!reviewed} onClick={()=>setStep('login')}>Continue to local sign-in</button><button disabled={busy} onClick={back}>Set up later</button>
      </>:step==='login'?<>
        <h3>Connect your VeSync account</h3><form onSubmit={event=>{event.preventDefault();void login();}}><TouchField label="VeSync email" value={username} onChange={setUsername} maxLength={254} required disabled={busy}/><TouchField label="VeSync password" value={password} onChange={setPassword} secret maxLength={256} required disabled={busy}/><TouchField label="Account country · two letters, e.g. US" value={country} onChange={value=>setCountry(value.toUpperCase())} maxLength={2} pattern="[A-Z]{2}" required disabled={busy}/><button disabled={busy||!reviewed||!username.trim()||!password||!/^[A-Z]{2}$/.test(country)}>Connect account</button></form><p className="setup-note">Enter credentials here, never in chat. They are not included in setup progress or portable backups. Password entry clears after each attempt.</p>
      </>:step==='discover'?<>
        <h3>Choose your purifier</h3><p>Only compatible Core 300S models are listed. Discovery does not switch anything on.</p><button disabled={busy} onClick={()=>void discover()}>Refresh device list</button><div className="room-options">{rows.map(row=><button disabled={busy} key={row.id} onClick={()=>{activity.edited();setChoice(row);setName(row.name);setStep('review');}}><strong>{row.name}</strong><span>{row.model}</span></button>)}</div>{discovered&&!rows.length&&<p>No compatible purifier found. Check enrollment and the account, then try again.</p>}
      </>:<>
        <h3>Review your selection</h3><p>{choice?.name} · {choice?.model}</p><form onSubmit={event=>{event.preventDefault();void select();}}><TouchField label="Name on Luma" value={name} onChange={setName} maxLength={100} required disabled={busy}/><p>This saves the selection only after a successful status read. No control command or automation is sent.</p>{config.selected&&<p>Replaces “{config.selected.name}” on Luma only.</p>}<button disabled={busy||!name.trim()}>Select & check reported state</button></form>
      </>}
    </>}
    {confirm&&<div ref={confirmPanel} className="room-confirm" role="alertdialog" aria-modal="true" tabIndex={-1} aria-label={confirm==='discard'?'Discard room-device edits':confirm==='disconnect'?'Disconnect VeSync':'Remove purifier'}><p>{confirm==='discard'?'Discard unsaved room-device choices and credentials?':confirm==='disconnect'?'Remove the saved VeSync session and purifier selection? Luma will stop polling. This does not turn the purifier off.':'Remove the purifier selection from Luma? This does not turn it off.'}</p><div className="room-actions"><button disabled={busy} onClick={()=>void confirmAction()}>{confirm==='discard'?'Discard changes':'Confirm removal'}</button><button disabled={busy} onClick={()=>setConfirm(null)}>Keep current settings</button></div></div>}
    {busy&&<p role="status">Checking…</p>}{message&&<p role="status">{message}</p>}
  </div>;
}
