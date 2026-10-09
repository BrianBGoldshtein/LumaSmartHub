import React,{useCallback,useEffect,useRef,useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Home,Settings,Download,LockKeyhole,Sun,Volume2,CalendarDays,Timer,Check,ShieldCheck} from 'lucide-react';
import '@fontsource/manrope/500.css';
import '@fontsource/manrope/700.css';
import '@fontsource/newsreader/600.css';
import '@fontsource/pixelify-sans/600.css';
import '@fontsource/space-grotesk/600.css';
import {bootstrapRemote,enrollRemote,RemoteClient,RemoteError} from '../companionClient';
import {createBrowserKey,loadCredential,saveCredential} from '../companionProof';
import type {BrowserCredential,RemoteContext} from '../companionProof';
import type {GoogleCalendar,GoogleEventColor,GoogleStatus} from '../googleSetupState';
import {calendarSelection} from '../googleSetupState';
import {timerText} from '../timerState';
import {clockText,enrollTicket,safeColor,upcoming,updateOutcome,primaryRemote,personalSteps} from './state';
import type {Preview,RemoteSettings,PersonalSettings,PersonalSetup,UpdateStatus,Candidate} from './state';
import type {Theme} from '../types';
import './style.css';
import {TemperatureReadout} from '../TemperatureReadout';
import {FanControlPanel} from '../FanControlPanel';

// Remove the one-use fragment before loading any network resource. It remains
// only in this document's memory, never a URL query, log or persistent store.
let initialTicket=enrollTicket(location.href,location.origin);
const googleReturn=new URLSearchParams(location.hash.slice(1)).get('google');
history.replaceState(null,'','/remote/');
type Tab='hub'|'personal'|'settings'|'software';
const themes=[['luma-glass','Glass'],['hearth','Hearth'],['neon-grid','Neon']] as const;
function message(error:unknown){return error instanceof RemoteError?error.message:'Luma is unavailable. Reconnect and refresh.';}

function RemoteApp(){
  const [tab,setTab]=useState<Tab>('hub'),[client,setClient]=useState<RemoteClient|null>(null);
  const [credential,setCredential]=useState<BrowserCredential|null>(null),[context,setContext]=useState<RemoteContext|null>(null);
  const [preview,setPreview]=useState<Preview|null>(null),[settings,setSettings]=useState<RemoteSettings|null>(null);
  const [personal,setPersonal]=useState<PersonalSettings|null>(null),[adminUnlocked,setAdminUnlocked]=useState(false),[confirmPrimary,setConfirmPrimary]=useState(false),[pin,setPin]=useState('');
  const [status,setStatus]=useState<UpdateStatus|null>(null),[candidate,setCandidate]=useState<Candidate|null>(null);
  const [code,setCode]=useState(''),[notice,setNotice]=useState('Opening your private connection…');
  const [busy,setBusy]=useState(false),[ready,setReady]=useState(false),[epoch,setEpoch]=useState(0);
  const [updateTarget,setUpdateTarget]=useState<string|null>(null);
  const [updateResult,setUpdateResult]=useState<string|null>(null);
  const [appearance,setAppearance]=useState<Theme>('luma-glass');
  const [callbackNote,setCallbackNote]=useState(googleReturn==='ok'?'Google connected. Refresh calendar choices.':googleReturn==='failed'?'Google sign-in did not finish. Reconnect your phone to Luma and try again. Existing sign-in is retained.':'');
  const generation=useRef(0),pollBusy=useRef(false),installed=useRef(false);
  const clientRef=useRef<RemoteClient|null>(null);clientRef.current=client;
  const clear=()=>{setPreview(null);setSettings(null);setPersonal(null);setAdminUnlocked(false);setConfirmPrimary(false);setPin('');setStatus(null);setCandidate(null);};
  const failed=(error:unknown)=>{if(error instanceof RemoteError&&error.kind==='admin'){setAdminUnlocked(false);setConfirmPrimary(true);setPin('');}
    else clear();setNotice(message(error));};
  useEffect(()=>{
    let live=true;const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),15000);
    Promise.all([bootstrapRemote(location.origin,fetch,controller.signal),loadCredential()]).then(([connection,key])=>{
      if(!live)return;setContext(connection);setCredential(key);setReady(true);
      setNotice(key?'Connect your selected iPhone to Luma.':'Enroll this browser from Luma’s Settings.');
    }).catch(()=>{if(live){setReady(true);setNotice('Open Luma’s private HTTPS address with Tailscale connected.');}});
    return()=>{live=false;clearTimeout(timeout);controller.abort();};
  },[]);
  useEffect(()=>{setClient(credential&&context?new RemoteClient(credential,context):null);},[credential,context]);
  useEffect(()=>{
    const fragment=()=>{
      const ticket=enrollTicket(location.href,location.origin),returned=new URLSearchParams(location.hash.slice(1)).get('google');
      history.replaceState(null,'','/remote/');
      if(ticket){generation.current++;clientRef.current?.suspend();clear();setBusy(false);pollBusy.current=false;
        initialTicket=ticket;setCredential(null);setClient(null);setCode('');setNotice('Ready to enroll this browser.');}
      if(returned==='ok'||returned==='failed')setCallbackNote(returned==='ok'?'Google connected. Refresh calendar choices.':'Google sign-in did not finish. Existing sign-in is retained.');
    };
    window.addEventListener('hashchange',fragment);return()=>window.removeEventListener('hashchange',fragment);
  },[]);
  useEffect(()=>{
    const suspend=()=>{generation.current++;clientRef.current?.suspend();clear();setBusy(false);pollBusy.current=false;};
    const visibility=()=>{if(document.visibilityState!=='visible'){suspend();setNotice('Private preview paused.');}
      else{setEpoch(value=>value+1);setNotice('Checking your iPhone connection…');}};
    const offline=()=>{suspend();setNotice('Offline. Private preview cleared.');};
    const online=()=>{setEpoch(value=>value+1);};
    document.addEventListener('visibilitychange',visibility);window.addEventListener('pagehide',suspend);
    window.addEventListener('offline',offline);window.addEventListener('online',online);
    return()=>{suspend();document.removeEventListener('visibilitychange',visibility);window.removeEventListener('pagehide',suspend);
      window.removeEventListener('offline',offline);window.removeEventListener('online',online);};
  },[]);
  useEffect(()=>{
    if(!client)return;let live=true;let handle:number|undefined;
    const poll=async()=>{
      if(!live)return;
      if(document.visibilityState==='visible'&&navigator.onLine&&!pollBusy.current){
        pollBusy.current=true;const current=generation.current;
        try{
          const value=await client.request<Preview>('GET','/remote/api/preview');
          if(!live||current!==generation.current)return;
          setPreview(value);setAppearance(value.settings.theme);setNotice('');setCode('');
          if(tab==='personal'){
            const result=await client.request<PersonalSettings>('GET','/remote/api/personal-settings');
            if(live&&current===generation.current)setPersonal(result);
          }
          if(primaryRemote(value)&&(tab==='settings'||tab==='software')){
            const authority=await client.request<{unlocked:boolean}>('GET','/remote/api/admin/status');
            if(!live||current!==generation.current)return;setAdminUnlocked(authority.unlocked);
            if(authority.unlocked&&!confirmPrimary&&tab==='settings'){
              const result=await client.request<RemoteSettings>('GET','/remote/api/settings');
              if(live&&current===generation.current)setSettings(result);
            }
          }
          if(primaryRemote(value)&&(tab==='software'||installed.current)){
            const result=await client.request<UpdateStatus>('GET','/remote/api/updates/status');
            if(live&&current===generation.current){setStatus(result);
              if(updateTarget){const outcome=updateOutcome(result,updateTarget);
                if(outcome){installed.current=false;setUpdateTarget(null);setUpdateResult(outcome);}}
            }
          }
        }catch(error){if(live&&current===generation.current)failed(error);}
        finally{if(current===generation.current)pollBusy.current=false;}
      }
      if(live)handle=window.setTimeout(poll,5000);
    };void poll();return()=>{live=false;if(handle!==undefined)clearTimeout(handle);};
  },[client,epoch,tab,updateTarget,confirmPrimary]);
  async function run(action:()=>Promise<void>){
    const current=generation.current;setBusy(true);setNotice('');pollBusy.current=true;
    try{await action();}catch(error){if(current===generation.current)failed(error);}
    finally{if(current===generation.current){setBusy(false);pollBusy.current=false;}}
  }
  const request=async<T,>(method:string,path:string,payload?:unknown)=>{
    if(!client)throw new Error();const current=generation.current;
    const result=await client.request<T>(method,path,payload);
    if(current!==generation.current)throw new RemoteError('connection','Private preview paused.');return result;
  };
  const command=(name:string,value?:unknown)=>run(async()=>{
    const result=await request<{preview:Preview}>('POST','/remote/api/command',{name,...(value===undefined?{}:{value})});setPreview(result.preview);
  });
  const save=(patch:Partial<RemoteSettings>)=>run(async()=>{setSettings(await request<RemoteSettings>('PATCH','/remote/api/settings',patch));setEpoch(value=>value+1);});
  const savePersonal=(patch:Partial<RemoteSettings>)=>run(async()=>{setPersonal(await request<PersonalSettings>('PATCH','/remote/api/personal-settings',patch));setEpoch(value=>value+1);});
  const unlockPrimary=()=>{const entered=pin;setPin('');void run(async()=>{
    await request('POST','/remote/api/admin/unlock',{pin:entered});setAdminUnlocked(true);setConfirmPrimary(false);setEpoch(value=>value+1);
  });};
  const enroll=()=>run(async()=>{
    if(!context||!initialTicket)throw new RemoteError('expired','Request a new enrollment QR on Luma.');
    const current=generation.current,key=await createBrowserKey();
    const claimed=await enrollRemote(initialTicket,key,context);
    initialTicket=null;
    if(current!==generation.current)throw new RemoteError('connection','Enrollment paused. Request a new QR on Luma.');
    const saved={...key,deviceId:claimed.device_id};await saveCredential(saved);
    if(current!==generation.current)return;
    setCredential(saved);setCode(claimed.comparison_code);setNotice('Compare this code on Luma, then approve there with your hub PIN.');
  });
  // Keep only this public appearance hint in RAM when private data is cleared;
  // a disconnect should not flash the page into an unrelated theme.
  const theme=preview?.settings.theme??appearance;
  return <div className={`remote theme-${theme}`}>
    <header><a href="/remote/" aria-label="Luma remote home"><i className="remote-orb"/><b>Luma</b><span>remote</span></a><span className="link-status"><ShieldCheck size={16}/>{preview?'Private link':'Locked'}</span></header>
    <main>
      {updateResult&&<div className="notice" role="status"><p>{updateResult}</p><button onClick={()=>setUpdateResult(null)}>Dismiss</button></div>}
      {callbackNote&&<div className="notice" role="status"><p>{callbackNote}</p><button onClick={()=>setCallbackNote('')}>Dismiss</button></div>}
      {!preview?<section className="locked"><LockKeyhole size={36}/><h1>Your hub.<br/>Within reach.</h1><p role="status">{code?`Approval code: ${code}`:notice}</p>
        {updateTarget&&<p>Update {updateTarget} was accepted. Keep Pi power connected. Reconnecting is not confirmation of success; check the installed version when your private link returns.</p>}
        {code&&<p>Match the six digits on the hub before approving. Approval never requires sending your PIN to this phone.</p>}
        {code&&notice&&<p role="status">{notice}</p>}
        {ready&&context&&initialTicket&&!code&&<button className="primary" disabled={busy} onClick={()=>void enroll()}>Enroll this browser</button>}
        {credential&&<button disabled={busy} onClick={()=>setEpoch(value=>value+1)}>Check connection</button>}
        <details><summary>First time here?</summary><ol><li>Keep Tailscale connected on your iPhone. Pair it with Luma and enable Share System Notifications.</li><li>Want a Home Screen app? Use Safari → Share → Add to Home Screen, open it, then enroll that window. Safari and Home Screen enroll separately.</li><li>On the hub, open Settings → iPhone remote, enter your PIN and create a QR. Open its private link in this window, or paste that link below.</li><li>Enroll and compare the approval code on both screens. Approve on Luma.</li></ol>
          <form onSubmit={event=>{event.preventDefault();const input=event.currentTarget.elements.namedItem('link') as HTMLInputElement;
            const ticket=enrollTicket(input.value,location.origin);input.value='';if(ticket){initialTicket=ticket;setNotice('Ready to enroll.');setEpoch(value=>value+1);}else setNotice('Use the fresh enrollment link from this Luma hub.');}}>
            <label>Enrollment link<input name="link" type="url" autoComplete="off" autoCapitalize="none" spellCheck={false} required maxLength={500}/></label><button>Use link</button>
          </form><p>Your browser key is saved locally. Hub data is not saved offline. Access requires this selected iPhone’s authorized Bluetooth session.</p></details>
      </section>:<>
        {notice&&<p role="status" className="notice">{notice}</p>}
        {tab==='hub'&&<Hub preview={preview} busy={busy} command={command} task={(event)=>run(async()=>{
          setPreview(await request<Preview>('POST','/remote/api/todos/complete',{calendar_id:event.calendar_id,event_id:event.id,completed:!event.completed,etag:event.etag}));
        })}/>}
        {tab==='personal'&&(personal?<><h1>{preview.nickname}’s calendars</h1><PersonalGuide busy={busy} request={request} run={run}/><CalendarSettings settings={personal} busy={busy} save={savePersonal} request={request} run={run} personalOnly/></>:<p>Loading your calendar choices…</p>)}
        {primaryRemote(preview)&&(tab==='settings'||tab==='software')&&(!adminUnlocked||confirmPrimary)&&<section className="locked"><LockKeyhole/><h1>Primary settings</h1><p>Enter your primary hub PIN. Calendar choices and your timer need no administrator unlock.</p>
          <form onSubmit={event=>{event.preventDefault();unlockPrimary();}}><label>Primary PIN<input type="password" inputMode="numeric" autoComplete="off" pattern="[0-9]{4,8}" required minLength={4} maxLength={8} value={pin} onChange={event=>setPin(event.target.value.replace(/[^0-9]/g,''))} disabled={busy}/></label><button disabled={busy}>Unlock primary settings</button></form></section>}
        {primaryRemote(preview)&&(tab==='settings'||tab==='software')&&adminUnlocked&&!confirmPrimary&&<div className="buttons"><span>Primary settings unlocked · 5 minutes</span><button disabled={busy} onClick={()=>{setPin('');setConfirmPrimary(true);}}>Confirm PIN</button>
          <button disabled={busy} onClick={()=>void run(async()=>{await request('POST','/remote/api/admin/lock',{});setAdminUnlocked(false);setSettings(null);setCandidate(null);setPin('');})}>Lock settings</button></div>}
        {primaryRemote(preview)&&tab==='settings'&&adminUnlocked&&!confirmPrimary&&(settings?<SettingsPanel key={epoch} settings={settings} busy={busy} save={save} request={request} run={run}/>:<p>Loading settings…</p>)}
        {primaryRemote(preview)&&tab==='software'&&adminUnlocked&&!confirmPrimary&&<section className="software"><h1>Luma software</h1><p>Current version <b>{status?.current_version??'Checking…'}</b></p>
          {status?.state&&status.state!=='idle'&&<div className="notice" role="status"><b>{status.phase??status.state}</b><p>{status.message}</p><span>{status.target_version&&`Target ${status.target_version}`}</span>{status.elapsed_seconds!==undefined&&<small>{Math.floor(status.elapsed_seconds/60)} min elapsed</small>}</div>}
          <p>Signed GitHub releases. Settings, Google sign-in and saved games stay on your Pi.</p>
          <button disabled={busy||status?.state==='installing'} onClick={()=>void run(async()=>{const result=await request<Candidate>('POST','/remote/api/updates/check',{});setCandidate(result);})}>Check for updates</button>
          {candidate?.state==='current'&&<p role="status">You’re up to date.</p>}
          {candidate?.candidate_id&&<article className="release"><h2>{candidate.version}</h2><pre>{candidate.release_notes}</pre><p>Keep Pi power connected. Your remote may disconnect while Luma restarts; this is not confirmation of success. Reconnect to check the installed version.</p>
            <button className="primary" disabled={busy||status?.state==='installing'} onClick={()=>{if(!confirm(`Install reviewed Luma ${candidate.version}? Keep Pi power connected.`))return;
              void run(async()=>{await request('POST','/remote/api/updates/install',{candidate_id:candidate.candidate_id});installed.current=true;setUpdateResult(null);setUpdateTarget(candidate.version??null);setCandidate(null);setNotice('Update accepted. Keep power connected; checking progress.');setEpoch(value=>value+1);});}}>Review complete · Install</button>
            <button onClick={()=>setCandidate(null)} disabled={busy}>Cancel</button></article>}
        </section>}
      </>}
    </main>
    <nav aria-label="Remote pages">{([['hub','Hub',Home],['personal','My calendars',CalendarDays],['settings','Settings',Settings],['software','Software',Download]] as const).filter(([id])=>id==='hub'||id==='personal'||primaryRemote(preview)).map(([id,label,Icon])=><button key={id} aria-current={tab===id?'page':undefined} onClick={()=>setTab(id)}><Icon size={21}/>{label}</button>)}</nav>
  </div>;
}

function Hub({preview,busy,command,task}:{preview:Preview;busy:boolean;command:(name:string,value?:unknown)=>Promise<void>;task:(event:Preview['todos'][number])=>Promise<void>}){
  const zone=preview.settings.timezone,events=upcoming(preview.calendar,preview.server_time);
  const [timerUnit,setTimerUnit]=useState('minutes');
  return <>
    <section className="hero"><span>{new Intl.DateTimeFormat(undefined,{weekday:'long',month:'short',day:'numeric',timeZone:zone}).format(new Date(preview.server_time))}</span>
      <h1>{clockText(preview.server_time,zone)}</h1><div className="weather"><b>{preview.weather?`${Math.round(preview.weather.temperature)}°`:'—'}</b><div>{preview.weather?.summary??'Weather unavailable'}<small>{preview.settings.weather_location_label}{preview.weather?.stale?' · Saved forecast':''}</small></div></div>
      {preview.weather&&<small className="attribution">{preview.weather.attribution}</small>}
      <TemperatureReadout reading={preview.device_temperature}/>
    </section>
    <section><div className="section-title"><h2><CalendarDays size={20}/> Upcoming</h2><span>On the hub</span></div>
      {preview.privacy_redacted?<p>Hub is in private standby. Private details remain hidden.</p>:events.length?events.slice(0,8).map(event=><article className="event" key={`${event.calendar_id}:${event.id}`} style={{borderColor:safeColor(event.event_color??event.calendar_color)}}>
        <time>{event.all_day?'All day':clockText(event.start,zone)}</time><div><b>{event.summary}</b>{event.location&&<small>{event.location}</small>}</div>
      </article>):<p>No upcoming events in the hub’s current window.</p>}
    </section>
    {!preview.privacy_redacted&&<section><h2>To-dos</h2>{preview.todos.length?preview.todos.map(event=><div className={`task ${event.completed?'completed':''}`} key={`${event.calendar_id}:${event.id}`}>
      <button aria-label={`${event.completed?'Reopen':'Complete'} ${event.summary}`} aria-pressed={!!event.completed} disabled={busy||!preview.todo_controls.can_update||preview.todo_controls.stale||!event.etag} onClick={()=>void task(event)}>{event.completed?<Check size={19}/>:<span/>}</button>
      <div><b>{event.summary}</b><small>{event.due_date?`Due ${event.due_date}`:''}</small></div>
    </div>):<p>No tasks today.</p>}{(!preview.todo_controls.can_update||preview.todo_controls.stale)&&<small>Task editing requires Google write permission and a fresh sync.</small>}</section>}
    {preview.departure&&!preview.privacy_redacted&&<section><h2>Leave at {clockText(preview.departure.depart_at,zone)}</h2><p>{preview.departure.title}</p></section>}
    <section><h2><Timer size={20}/> Timer</h2>{preview.timer.status!=='idle'&&<div className="timer"><b>{timerText(preview.timer.remaining_seconds)}</b><p>{preview.timer.label} · {preview.timer.status}</p>
      <div className="buttons">{preview.timer.status==='running'&&<button disabled={busy} onClick={()=>void command('pause_timer')}>Pause</button>}{preview.timer.status==='paused'&&<button disabled={busy} onClick={()=>void command('resume_timer')}>Resume</button>}<button disabled={busy} onClick={()=>void command('cancel_timer')}>Cancel</button></div></div>}
      <form onSubmit={event=>{event.preventDefault();const form=new FormData(event.currentTarget);const amount=Number(form.get('amount')),unit=String(form.get('unit'));
        const active=['running','paused','awaiting_time'].includes(preview.timer.status);if(active&&!confirm('Replace the current timer?'))return;
        void command('start_timer',{seconds:amount*(unit==='hours'?3600:unit==='minutes'?60:1),label:String(form.get('label')).trim()||'Timer',...(active?{replace_id:preview.timer.id}:{})});}}>
        <div className="split"><label>Duration<input name="amount" type="number" required min="1" max={timerUnit==='hours'?4:timerUnit==='minutes'?240:14400} step="1" defaultValue="5"/></label><label>Unit<select name="unit" value={timerUnit} onChange={event=>setTimerUnit(event.target.value)}><option>seconds</option><option>minutes</option><option>hours</option></select></label></div>
        <small>Timers run for up to four hours.</small>
        <label>Name<input name="label" maxLength={40} placeholder="Tea, study, laundry…"/></label><button disabled={busy}>Start timer</button>
      </form>
    </section>
    {primaryRemote(preview)&&<section><h2>Wall controls</h2><div className="buttons"><button disabled={busy} onClick={()=>void command('previous_page')}>Previous</button><button disabled={busy} onClick={()=>void command('next_page')}>Next</button><button disabled={busy} onClick={()=>void command('pause_cycle')}>Pause cycle</button><button disabled={busy} onClick={()=>void command('resume_cycle')}>Resume</button><button disabled={busy} onClick={()=>void command('good_night')}>Good night</button><button disabled={busy} onClick={()=>void command('wake')}>Wake</button></div></section>}
  </>;
}

type SettingsProps={settings:RemoteSettings;busy:boolean;save:(patch:Partial<RemoteSettings>)=>Promise<void>;
  request:<T>(method:string,path:string,payload?:unknown)=>Promise<T>;run:(action:()=>Promise<void>)=>Promise<void>};
function PersonalGuide({busy,request,run}:Pick<SettingsProps,'busy'|'request'|'run'>){
  const [setup,setSetup]=useState<PersonalSetup|null>(null);
  useEffect(()=>{let live=true;void run(async()=>{const value=await request<PersonalSetup>('GET','/remote/api/setup');if(live)setSetup(value);});
    return()=>{live=false;};},[]);
  if(!setup)return <section><p role="status">Loading your saved setup…</p></section>;
  const step=personalSteps.indexOf(setup.setup_stage),last=step===personalSteps.length-1;
  const progress=(stage:PersonalSetup['setup_stage'],sharing=setup.wall_share_approved)=>void run(async()=>{
    setSetup(await request<PersonalSetup>('POST','/remote/api/setup',{stage,wall_share_approved:sharing}));
  });
  return <section aria-label="Your personal setup">
    <small>Personal setup · {step+1} of {personalSteps.length} · Saved on Luma</small>
    <h2>{['Your private phone link','Connect your Google account','Choose your calendars','Ready when you are'][step]}</h2>
    <p>{['Your browser is enrolled and your iPhone is authorized. Pairing and primary approval are already complete.',
      'Use Google sign-in below. This links only your account. Google is optional; your timer works without it.',
      'Select every calendar you want, your all-day task calendar and a completed color. Save the choices below.',
      'Your preferences are saved. Choose whether your calendar and tasks can appear on the shared wall when your phone is connected.'][step]}</p>
    {last&&<label className="check"><input type="checkbox" checked={setup.wall_share_approved} disabled={busy}
      onChange={event=>progress('ready',event.target.checked)}/> Share my calendar and tasks on the wall while I’m connected</label>}
    {last&&<small>Others nearby may see shared details. Turning sharing off does not delete your calendars or block your own phone preview and timer.</small>}
    <div className="buttons">{step>0&&<button disabled={busy} onClick={()=>progress(personalSteps[step-1])}>Back</button>}
      {!last&&<button disabled={busy} onClick={()=>progress(personalSteps[step+1])}>{step===0?'Continue setup':step===1?'Continue · Google is optional':'Continue to sharing'}</button>}
      {last&&<span role="status">Setup saved · {setup.wall_share_approved?'Wall sharing on':'Wall sharing off'}</span>}</div>
  </section>;
}
function SettingsPanel({settings,busy,save,request,run}:SettingsProps){
  const coolingRequest=useCallback(<T,>(method:string,path:string,body?:unknown)=>request<T>(method,'/remote/api/'+path,body),[request]);
  const [section,setSection]=useState<'appearance'|'calendars'>('appearance');
  return <><h1>Make it yours</h1><div className="segmented"><button disabled={busy} aria-pressed={section==='appearance'} onClick={()=>setSection('appearance')}>Appearance</button><button disabled={busy} aria-pressed={section==='calendars'} onClick={()=>setSection('calendars')}>Calendars</button></div>
    {section==='calendars'?<CalendarSettings settings={settings} busy={busy} save={save} request={request} run={run}/>:<>
      <FanControlPanel request={coolingRequest}/>
      <section><h2>Theme</h2><div className="themes">{themes.map(([id,name])=><button aria-pressed={settings.theme===id} disabled={busy} key={id} onClick={()=>void save({theme:id})}>{name}</button>)}</div>
        <form onSubmit={event=>{event.preventDefault();const values=new FormData(event.currentTarget);void save({brightness:Number(values.get('brightness')),volume:Number(values.get('volume'))});}}>
          <label><Sun size={19}/> Brightness<input type="range" name="brightness" min="0" max="100" defaultValue={settings.brightness}/></label>
          <label><Volume2 size={19}/> Volume<input type="range" name="volume" min="0" max="100" defaultValue={settings.volume}/></label><button disabled={busy}>Save brightness & volume</button>
        </form>
      </section>
      <section><h2>Weather & time</h2><form onSubmit={event=>{event.preventDefault();const values=new FormData(event.currentTarget);const lat=String(values.get('latitude')),lon=String(values.get('longitude'));
        if((lat==='')!==(lon===''))return;void save({weather_location_label:String(values.get('location')),latitude:lat===''?null:Number(lat),longitude:lon===''?null:Number(lon),timezone:String(values.get('timezone'))});}}>
        <label>Place<input name="location" maxLength={100} defaultValue={settings.weather_location_label}/></label>
        <div className="split"><label>Latitude<input name="latitude" type="number" step="any" min="-90" max="90" defaultValue={settings.latitude??''}/></label><label>Longitude<input name="longitude" type="number" step="any" min="-180" max="180" defaultValue={settings.longitude??''}/></label></div>
        <small>Stanford longitude is negative. Leave both coordinates blank to disable forecasts.</small><label>Timezone<input name="timezone" required maxLength={80} defaultValue={settings.timezone}/></label><button disabled={busy}>Save location</button></form>
      </section>
      <section><h2>Quiet nights</h2><label className="check"><input type="checkbox" checked={settings.night_clock_enabled} disabled={busy} onChange={event=>void save({night_clock_enabled:event.target.checked})}/> Barely visible night clock</label>
        <label className="check"><input type="checkbox" checked={settings.voice_enabled} disabled={busy} onChange={event=>void save({voice_enabled:event.target.checked})}/> Hey Luma enabled</label>
        <label className="check"><input type="checkbox" checked={settings.notification_chime_enabled} disabled={busy} onChange={event=>void save({notification_chime_enabled:event.target.checked})}/> Notification chime</label>
        <details><summary>Night light & chime volume</summary><form onSubmit={event=>{event.preventDefault();const values=new FormData(event.currentTarget);
          void save({night_brightness:Number(values.get('night')),notification_chime_volume:Number(values.get('chime'))});}}>
          <label>Night brightness (%)<input name="night" type="number" min="0" max="100" step="1" required defaultValue={settings.night_brightness}/></label>
          <small>Keep this near zero for a barely visible clock in darkness.</small>
          <label>Chime volume (%)<input name="chime" type="number" min="0" max="100" step="1" required defaultValue={settings.notification_chime_volume}/></label><button disabled={busy}>Save night & chime</button></form></details>
        <p>Microphone calibration, pairing, private-network setup and browser revocation stay on the hub.</p>
      </section>
      <section><h2>Timer defaults</h2><form onSubmit={event=>{event.preventDefault();const values=new FormData(event.currentTarget);
        void save({timer_focus_minutes:Number(values.get('focus')),timer_break_minutes:Number(values.get('break'))});}}>
        <div className="split"><label>Focus minutes<input name="focus" type="number" min="1" max="240" step="1" required defaultValue={settings.timer_focus_minutes}/></label>
        <label>Break minutes<input name="break" type="number" min="1" max="240" step="1" required defaultValue={settings.timer_break_minutes}/></label></div><button disabled={busy}>Save timer defaults</button></form>
      </section>
      <section><h2>Weather reminders</h2><label className="check"><input type="checkbox" checked={settings.weather_nudges_enabled} disabled={busy} onChange={event=>void save({weather_nudges_enabled:event.target.checked})}/> Weather warnings on the hub</label>
        <details><summary>Adjust warning thresholds</summary><form onSubmit={event=>{event.preventDefault();const values=new FormData(event.currentTarget);
          void save({weather_rain_percent:Number(values.get('rain')),weather_gust_mph:Number(values.get('gust')),weather_hot_f:Number(values.get('hot')),weather_cold_f:Number(values.get('cold'))});}}>
          <div className="split"><label>Rain chance (%)<input name="rain" type="number" min="1" max="100" step="1" required defaultValue={settings.weather_rain_percent}/></label>
          <label>Gusts (mph)<input name="gust" type="number" min="5" max="100" step="1" required defaultValue={settings.weather_gust_mph}/></label></div>
          <div className="split"><label>Hot above (°F)<input name="hot" type="number" min="-50" max="130" step="1" required defaultValue={settings.weather_hot_f}/></label>
          <label>Cold below (°F)<input name="cold" type="number" min="-50" max="130" step="1" required defaultValue={settings.weather_cold_f}/></label></div><button disabled={busy}>Save weather warnings</button></form></details>
      </section>
      <section><h2>Wall cycle</h2><form onSubmit={event=>{event.preventDefault();const values=new FormData(event.currentTarget);
        const pages=values.getAll('page').map(String),cycle=pages.map(page=>({page,seconds:Number(values.get(`seconds-${page}`))}));void save({cycle});
      }}>{[['home','Home'],['agenda','Calendar'],['weather','Weather'],['todos','To-dos'],['ambient','Games & animations'],['countdowns','Countdowns'],['transit','Transit']].map(([page,label])=>
        <div key={page} className="split"><label className="check"><input type="checkbox" name="page" value={page} defaultChecked={settings.cycle.some(row=>row.page===page)}/>{label}</label>
          <label>Seconds<input type="number" name={`seconds-${page}`} min="5" max="600" step="1" defaultValue={settings.cycle.find(row=>row.page===page)?.seconds??25}/></label></div>)}
        <small>Choose at least one. Countdown/transit slides need configured content. Privacy standby uses its own safe cycle.</small><button disabled={busy}>Save wall cycle</button></form></section>
    </>}
  </>;
}

function CalendarSettings({settings,busy,save,request,run,personalOnly=false}:Omit<SettingsProps,'settings'>&{settings:PersonalSettings&Partial<RemoteSettings>;personalOnly?:boolean}){
  type Status=GoogleStatus&{web_configured:boolean;redirect_uri:string};
  const [status,setStatus]=useState<Status|null>(null),[calendars,setCalendars]=useState<GoogleCalendar[]|null>(null),[colors,setColors]=useState<GoogleEventColor[]>([]);
  const [error,setError]=useState(''),[retry,setRetry]=useState(0);
  useEffect(()=>{let live=true;setCalendars(null);setError('');
    request<Status>('GET','/remote/api/google/status').then(value=>{
      if(live)setStatus(value);if(!value.authorized)return null;
      return Promise.all([request<GoogleCalendar[]>('GET','/remote/api/google/calendars'),request<GoogleEventColor[]>('GET','/remote/api/google/colors')]);
    }).then(result=>{if(live&&result){setCalendars(result[0]);setColors(result[1]);}})
      .catch(()=>{if(live)setError('Calendar list unavailable. Saved selections have not changed.');});return()=>{live=false;};
  },[retry]);
  function consent(task_updates:boolean){void run(async()=>{
    const result=await request<{url:string}>('POST','/remote/api/google/authorize',{task_updates});
    const url=new URL(result.url);if(url.protocol!=='https:'||url.hostname!=='accounts.google.com'||url.username||url.password)throw Error();
    location.assign(result.url);
  });}
  return <section><h2>Google Calendar</h2><p>{status?.authorized?'Google linked':'Google needs renewed sign-in.'}</p>
    {status?.web_configured?<div className="buttons"><button disabled={busy} onClick={()=>consent(false)}>{status.authorized?'Reconnect Google':'Sign in with Google'}</button>
      {!status.task_updates&&<button disabled={busy} onClick={()=>{if(confirm('Allow Luma to edit event colors on your selected task calendar? Google grants event-edit scope across writable calendars; Luma restricts task edits to your selection.'))consent(true);}}>Enable task updates</button>}</div>:
      personalOnly?<p>{status?.authorized?'Google is connected on the hub. To renew sign-in from this phone, ask the primary user to configure Google Web sign-in.':'The primary user needs to configure Google Web sign-in first. You can skip Google and still use your timer.'}</p>:<details><summary>Enable Google sign-in from this phone</summary><p>Your existing Desktop client stays unchanged. In your Google Cloud project, create an OAuth client of type Web application. Add this exact authorized redirect URI, then download its JSON.</p><code className="notice">{status?.redirect_uri??`${location.origin}/remote/google/callback`}</code>
        <p>Keep the same consent project and Calendar API. Client JSON stays on the Pi; never publish it to GitHub.</p>
        <label>Google Web client JSON<input type="file" accept=".json,application/json" disabled={busy} onChange={event=>{
          const input=event.currentTarget,file=input.files?.[0];input.value='';if(!file)return;
          void run(async()=>{if(file.size>65536)throw new RemoteError('invalid','Use a client JSON smaller than 64 KB.');
            await request('POST','/remote/api/google/web-client',JSON.parse(await file.text()));setRetry(value=>value+1);});
        }}/></label><p>On Home Screen, Google may open Safari for consent. After completing sign-in, return to your enrolled Home Screen window and refresh; each window has its own browser key.</p>
      </details>}
    {error&&<p role="alert">{error}</p>}{!calendars&&<button disabled={busy} onClick={()=>setRetry(value=>value+1)}>Retry calendar list</button>}
    <button disabled={busy||!status?.authorized} onClick={()=>void run(async()=>{await request('POST','/remote/api/google/sync',{});setRetry(value=>value+1);})}>Sync now</button>
    {calendars&&<form onSubmit={event=>{event.preventDefault();const values=new FormData(event.currentTarget);
      if(values.has('departureEnabled')&&!values.getAll('departure').length){setError('Choose a leaving-reminder calendar, or leave reminders off.');return;}
      void save({visible_calendar_ids:values.getAll('agenda').map(String),todo_calendar_id:String(values.get('todo'))||null,
        todo_completed_color_id:String(values.get('completed'))||null,...(personalOnly?{}:{sleep_calendar_ids:values.getAll('sleep').map(String),sleep_event_title:String(values.get('sleepTitle'))}),
        departure_calendar_ids:values.getAll('departure').map(String),departure_enabled:values.has('departureEnabled'),departure_include_virtual:values.has('includeVirtual'),
        departure_prep_minutes:Number(values.get('prep')),departure_travel_minutes:Number(values.get('travel'))});
    }}>
      <h3>Agenda · select all that apply</h3>{calendars.map(calendar=><label className="check" key={calendar.id}><input type="checkbox" name="agenda" value={calendar.id} defaultChecked={calendarSelection(settings.visible_calendar_ids,calendars).includes(calendar.id)}/><i style={{background:safeColor(calendar.background_color)}}/>{calendar.summary}</label>)}
      <label>To-do calendar<select name="todo" defaultValue={settings.todo_calendar_id??''}><option value="">None</option>{calendars.map(calendar=><option value={calendar.id} key={calendar.id}>{calendar.summary}</option>)}</select></label>
      <label>Completed color<select name="completed" defaultValue={settings.todo_completed_color_id??''}><option value="">Not selected</option>{colors.map(color=><option key={color.id} value={color.id}>Color {color.id}</option>)}</select></label>
      <div className="color-key">{colors.map(color=><span key={color.id}><i style={{background:safeColor(color.background)}}/>{color.id}</span>)}</div><p>Only your chosen completed color marks a task done. Other custom colors remain outstanding.</p>
      {!personalOnly&&<><h3>Room Sleep calendars · primary only</h3>{calendars.map(calendar=><label className="check" key={calendar.id}><input type="checkbox" name="sleep" value={calendar.id} defaultChecked={settings.sleep_calendar_ids?.includes(calendar.id)}/>{calendar.summary}</label>)}
      <label>Sleep event name<input name="sleepTitle" required maxLength={100} defaultValue={settings.sleep_event_title}/></label></>}
      <h3>Leaving reminders</h3>{calendars.map(calendar=><label className="check" key={calendar.id}><input type="checkbox" name="departure" value={calendar.id} defaultChecked={settings.departure_calendar_ids.includes(calendar.id)}/>{calendar.summary}</label>)}
      <label className="check"><input type="checkbox" name="departureEnabled" defaultChecked={settings.departure_enabled}/> Enable leaving reminders</label>
      <label className="check"><input type="checkbox" name="includeVirtual" defaultChecked={settings.departure_include_virtual}/> Include virtual events</label>
      <div className="split"><label>Preparation minutes<input name="prep" type="number" min="0" max="240" step="1" required defaultValue={settings.departure_prep_minutes}/></label>
      <label>Travel minutes<input name="travel" type="number" min="0" max="240" step="1" required defaultValue={settings.departure_travel_minutes}/></label></div>
      <button className="primary" disabled={busy}>Save calendar choices</button>
    </form>}
  </section>;
}
createRoot(document.getElementById('root')!).render(<RemoteApp/>);
