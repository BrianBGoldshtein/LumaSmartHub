import {useEffect,useRef,useState} from 'react';
import {ArrowLeft,Check,Smartphone,Users,CalendarDays,ShieldCheck} from 'lucide-react';
import {TouchField,TouchInputProvider} from './TouchField';
import {announceAdminNeeded} from './adminState';
import {setupTheme,setupLink} from './setupTheme';
import {useSetupActivity} from './setupActivity';
import type {GoogleCalendar,GoogleEventColor,GoogleStatus} from './googleSetupState';
import type {PersonalSettings} from './remote/state';
import './userSetup.css';

type User={profile_id:string;role:string;nickname:string;phone_registered:boolean;setup_stage:string;wall_share_approved:boolean;connected:boolean};
type Pairing={session:string|null;phase:string;devices:{path:string;name:string;address:string}[];challenge:string|null;passkey:string|null;message:string};
type Personal={profile_id:string;nickname:string;role:string;setup_stage:string;wall_share_approved:boolean;phone_registered:boolean;phone_authorized:boolean;connection_status:string;remote_allowed:boolean;google:GoogleStatus;personal:PersonalSettings;theme:string;pairing:Pairing};
const steps=['phone','remote','google','calendars','ready'] as const;
const titles=['Your iPhone','Phone remote','Your Google','Your calendars','Ready'];

async function api<T>(path:string,method='GET',body?:unknown):Promise<T>{
  const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),45000);
  try{
    const result=await fetch('/api/v1/'+path,{method,cache:'no-store',signal:controller.signal,
      headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
    const data=await result.json();
    if(!result.ok){announceAdminNeeded(data);throw Error(typeof data.detail==='string'?data.detail:'Personal setup is unavailable.');}
    return data as T;
  }finally{clearTimeout(timer);}
}

export function UsersSetup({demo}:{demo:boolean}){
  const [theme,setTheme]=useState(()=>setupTheme(new URLSearchParams(location.search).get('theme')));
  const [users,setUsers]=useState<User[]>([]),[name,setName]=useState(''),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[rename,setRename]=useState<string|null>(null);
  useSetupActivity(busy);
  async function load(){
    if(demo){setUsers([{profile_id:'primary',nickname:'Brian',role:'primary',phone_registered:true,setup_stage:'ready',wall_share_approved:true,connected:true}]);return;}
    const [data,settings]=await Promise.all([api<{users:User[]}>('users'),api<{theme:string}>('settings')]);
    setUsers(data.users);setTheme(setupTheme(settings.theme));
  }
  useEffect(()=>{void load().catch(()=>{setUsers([]);setMessage('Unlock primary settings to manage users.');});},[demo]);
  async function action(value:Record<string,unknown>,open=false){
    setBusy(true);setMessage('');
    try{
      if(demo){setMessage('Preview only. No person or phone was changed.');return;}
      await api('users/manage','POST',value);
      setRename(null);setName('');
      if(open){location.assign('/?setup=personal');return;}
      await load();setMessage('Saved.');
    }catch(error){setMessage(error instanceof Error?error.message:'Please try again.');}
    finally{setBusy(false);}
  }
  return <TouchInputProvider><div className={`app theme-${theme} setup-page`}><a className="setup-back" href={setupLink(demo,theme,'device')}><ArrowLeft/> Settings</a>
    <main className="setup-content device-setup user-setup"><Users size={40}/><h1>Your people.</h1><p>One primary. Up to four secondary users. Each keeps their own calendars, to-dos and timer.</p>
      <section><h2>Registered users · {users.length}/5</h2><div className="user-list">{users.map(user=><article key={user.profile_id}>
        <div><h3>{user.nickname}</h3><p>{user.role==='primary'?'Primary · hub settings and updates':'Secondary · personal calendars and timer'}<br/>{user.connected?'Authorized iPhone connected':user.phone_registered?'iPhone registered · not currently authorized':'Phone setup needed'}</p></div>
        <div className="user-actions"><button disabled={busy} onClick={()=>void action({action:'resume',profile_id:user.profile_id},true)}>Open personal setup</button>
          <button disabled={busy} onClick={()=>{setRename(user.profile_id);setName(user.nickname);}}>Rename</button>
          {user.phone_registered&&<button disabled={busy} onClick={()=>{if(confirm(`Clear ${user.nickname}’s phone registration? Their Google choices stay saved; old browser and personal-setup access are revoked. The Bluetooth bond itself is not erased.`))void action({action:'clear_phone',profile_id:user.profile_id},true);}}>Change phone…</button>}
          {user.role!=='primary'&&<button className="user-danger" disabled={busy} onClick={()=>{if(confirm(`Remove ${user.nickname}? This deletes their Luma Google credentials, saved events, timer and browser grants. It does not delete Google calendar events or the Bluetooth bond.`))void action({action:'remove',profile_id:user.profile_id});}}>Remove user…</button>}
        </div></article>)}</div></section>
      <form onSubmit={event=>{event.preventDefault();void action(rename?{action:'rename',profile_id:rename,nickname:name}:{action:'create',nickname:name},!rename);}}>
        <section><h2>{rename?'Rename user':'Add someone'}</h2><TouchField label="Nickname" required maxLength={24} value={name} onChange={setName} disabled={busy||(!rename&&users.length>=5)} placeholder="e.g. Alex"/>
          <p className="setup-note">Approve once here, then hand the wall screen to that person. They pair their own iPhone, optionally connect their Google account and choose what to share. You don’t need to stay nearby.</p>
          <button disabled={busy||!name.trim()||(!rename&&users.length>=5)}><Check/>{rename?'Save name':'Approve & begin guided setup'}</button>{rename&&<button type="button" disabled={busy} onClick={()=>{setRename(null);setName('');}}>Cancel</button>}
        </section></form>{message&&<p role="status" className="setup-message">{message}</p>}
    </main></div></TouchInputProvider>;
}

export function PersonalSetup({demo}:{demo:boolean}){
  const [view,setView]=useState<Personal|null>(null),[theme,setTheme]=useState(()=>setupTheme(new URLSearchParams(location.search).get('theme')));
  const [busy,setBusy]=useState(false),[message,setMessage]=useState(''),[share,setShare]=useState(false),[retry,setRetry]=useState(0);
  const [qr,setQr]=useState<{qr:string;url:string}|null>(null),[pending,setPending]=useState<{device_id:string;comparison_code:string}|null>(null);
  const selectedUser=useRef<string|null>(null);
  useSetupActivity(busy||['scanning','pairing','confirming'].includes(view?.pairing.phase??''));
  useEffect(()=>{
    let stopped=false,timer:ReturnType<typeof setTimeout>;
    async function poll(){
      try{
        if(demo)throw Error('Personal enrollment needs a real Luma. No preview device was paired.');
        const value=await api<Personal>('user-self/status');
        if(!stopped){if(selectedUser.current!==value.profile_id){selectedUser.current=value.profile_id;setShare(value.wall_share_approved);setQr(null);setPending(null);setMessage('');}setView(value);setTheme(setupTheme(value.theme));}
      }catch(error){if(!stopped){selectedUser.current=null;setView(null);setQr(null);setPending(null);setMessage(error instanceof Error?error.message:'Connect your authorized iPhone to continue.');}}
      if(!stopped)timer=setTimeout(()=>void poll(),2000);
    }
    void poll();return()=>{stopped=true;clearTimeout(timer);};
  },[demo,retry]);
  useEffect(()=>{
    if(!qr||!view?.remote_allowed)return;
    let live=true,timer:ReturnType<typeof setTimeout>;
    async function poll(){try{const result=await api<{pending:{device_id:string;comparison_code:string}|null}>('user-self/remote/pending');if(live)setPending(result.pending);}catch{if(live)setPending(null);}if(live)timer=setTimeout(()=>void poll(),2000);}
    void poll();return()=>{live=false;clearTimeout(timer);};
  },[qr,view?.remote_allowed]);
  async function run(operation:()=>Promise<void>){setBusy(true);setMessage('');try{await operation();}catch(error){setMessage(error instanceof Error?error.message:'Please try again.');}finally{setBusy(false);}}
  async function progress(stage:string,wall_share_approved?:boolean){
    const value=await api<Personal>('user-self/progress','POST',{stage,...(wall_share_approved===undefined?{}:{wall_share_approved})});setView(value);
  }
  const index=Math.max(0,steps.indexOf(view?.setup_stage as typeof steps[number]));
  return <TouchInputProvider><div className={`app theme-${theme} setup-page`}><a className="setup-back" href={setupLink(false,theme)}><ArrowLeft/> Dashboard</a>
    <main className="setup-content device-setup user-setup"><span className="user-eyebrow">Luma / personal setup</span><h1>{view?`${view.nickname}’s space.`:'Your personal space.'}</h1>
      {!view?<section><h2><ShieldCheck/> Personal setup paused</h2><p>Your saved progress is safe. Reconnect your registered iPhone and enable Share System Notifications. A newly paired phone is not authorized until Bluetooth services finish.</p><p>If this is your first visit or approval expired, ask the primary user to open your setup in Settings → Users.</p><button onClick={()=>setRetry(value=>value+1)}>Check again</button><a href={setupLink(false,theme,'users')}>Primary user · open Users →</a></section>:<>
        <nav aria-label="Personal setup steps" className="user-steps">{steps.map((step,i)=><span key={step} aria-current={i===index?'step':undefined}><b>{i+1}</b>{titles[i]}</span>)}</nav>
        <p className="setup-note">Progress stays on this Luma. Your personal setup does not unlock room settings or updates.</p>
        {view.setup_stage==='phone'&&<section><h2><Smartphone/> Pair your iPhone</h2><p>Open iPhone Settings → Bluetooth. Choose your phone below, then compare the six-digit code on both screens. Only approve if they match.</p>
          {!['scanning','pairing','confirming'].includes(view.pairing.phase)&&<button disabled={busy} onClick={()=>void run(async()=>{await api('user-self/pairing/start','POST');setRetry(value=>value+1);})}>Find my iPhone</button>}
          <div className="network-list">{view.pairing.devices.map(device=><button key={device.path} disabled={busy} onClick={()=>void run(async()=>{await api('user-self/pairing/select','POST',{session:view.pairing.session,device:device.path});})}><Smartphone/><span>{device.name}<small>{device.address}</small></span></button>)}</div>
          {view.pairing.phase==='confirming'&&<div className="pairing-confirmation"><output aria-label="Pairing code">{view.pairing.passkey}</output><button disabled={busy} onClick={()=>void run(async()=>{await api('user-self/pairing/confirm','POST',{session:view.pairing.session,challenge:view.pairing.challenge,accepted:true});})}>Codes match · pair</button><button disabled={busy} onClick={()=>void run(async()=>{await api('user-self/pairing/confirm','POST',{session:view.pairing.session,challenge:view.pairing.challenge,accepted:false});})}>Reject</button></div>}
          {['scanning','pairing','confirming'].includes(view.pairing.phase)&&<button disabled={busy} onClick={()=>void run(async()=>{await api('user-self/pairing/cancel','POST',{session:view.pairing.session});})}>Cancel pairing</button>}
          <p role="status">{view.pairing.message}</p><p>Enable Share System Notifications beside Luma on the iPhone. Your private data stays hidden until Luma verifies that access.</p></section>}
        {view.setup_stage==='remote'&&<section><h2><Smartphone/> Take Luma with you</h2><p>{view.remote_allowed?'Optional. Your own private Safari/Home Screen remote sees only your calendar and timer. Use your own Tailscale account; ask the primary user to share the Luma node with it. Never share the primary login.':'This hub uses primary-only phone remotes. Your calendars, Bluetooth presence and timer still work here.'}</p>
          {view.remote_allowed&&<><button disabled={busy} onClick={()=>void run(async()=>setQr(await api('user-self/remote/issue','POST',{})))}>Show my enrollment QR</button>{qr&&<div className="user-enrollment"><img src={qr.qr} alt="Personal phone enrollment QR"/><p>Open in your phone’s Safari. Keep both screens nearby and compare the code. This QR expires in five minutes.</p></div>}{pending&&<div className="pairing-confirmation"><output aria-label="Browser comparison code">{pending.comparison_code}</output><p>Does your phone show these same digits?</p><button disabled={busy} onClick={()=>void run(async()=>{await api('user-self/remote/approve','POST',pending);setQr(null);setPending(null);setMessage('Your phone remote is approved.');})}>Codes match · approve my remote</button></div>}</>}
        </section>}
        {view.setup_stage==='google'&&<section><h2><CalendarDays/> Your Google account</h2><p>Optional. Sign into your own account—not the primary user’s. Luma saves its refresh token on this device, so you don’t need to sign in after ordinary power loss.</p><p>{view.google.authorized?'Google account linked.':view.google.configured?'Google Desktop sign-in is available.':'The primary user needs to import a Google Desktop client first. You can finish without Google.'}</p>
          <button disabled={busy||!view.google.configured} onClick={()=>void run(async()=>{const result=await api<{url:string}>('user-self/google/authorize','POST',{});const url=new URL(result.url);if(url.protocol!=='https:'||url.hostname!=='accounts.google.com'||url.username||url.password)throw Error('Google sign-in URL is invalid.');location.assign(result.url);})}>{view.google.authorized?'Reconnect my Google':'Sign in with my Google'}</button>
          {!view.google.task_updates&&<button disabled={busy||!view.google.configured} onClick={()=>{if(confirm('Allow Google event-edit permission so Luma can change completion colors on your chosen task calendar? Luma restricts its task edits to that calendar.'))void run(async()=>{const result=await api<{url:string}>('user-self/google/authorize','POST',{task_updates:true});const url=new URL(result.url);if(url.protocol!=='https:'||url.hostname!=='accounts.google.com'||url.username||url.password)throw Error('Google sign-in URL is invalid.');location.assign(result.url);});}}>Enable my task updates</button>}
          {new URLSearchParams(location.search).get('google_error')==='1'&&<p role="alert">Sign-in did not finish. Your previous Google connection was kept. Try again while your authorized phone is connected.</p>}
        </section>}
        {view.setup_stage==='calendars'&&<PersonalCalendars key={view.profile_id} view={view} busy={busy} run={run} onSaved={()=>progress('ready')}/>}
        {view.setup_stage==='ready'&&<section><h2><Check/> Make yourself at home</h2><label className="user-check"><input type="checkbox" checked={share} onChange={event=>setShare(event.target.checked)} disabled={busy}/> Show my selected calendar and to-dos on the shared wall while my authorized iPhone is nearby.</label><p className="setup-note">Others in the room can see shared information while you’re present. It hides immediately when your notification authorization is lost. Sleep and other room-wide settings still belong to the primary user.</p><button disabled={busy} onClick={()=>void run(async()=>{await progress('ready',share);setMessage('Personal setup saved.');})}>Save my sharing choice</button><a href={setupLink(false,theme)}>Return to the dashboard →</a></section>}
        <div className="user-actions">{index>1&&<button disabled={busy} onClick={()=>void run(()=>progress(steps[index-1]))}>← Back</button>}
          {index>0&&index<4&&<button disabled={busy} onClick={()=>void run(()=>progress(steps[index+1]))}>{view.setup_stage==='calendars'?'Finish without changing calendars':view.setup_stage==='google'&&!view.google.authorized?'Set Google up later →':'Continue →'}</button>}
          <button disabled={busy} onClick={()=>void run(async()=>{await api('user-self/lock','POST');setView(null);setQr(null);setPending(null);})}>Lock personal setup</button></div>
      </>}{message&&<p role="status" className="setup-message">{message}</p>}
    </main></div></TouchInputProvider>;
}

function PersonalCalendars({view,busy,run,onSaved}:{view:Personal;busy:boolean;run:(task:()=>Promise<void>)=>Promise<void>;onSaved:()=>Promise<void>}){
  const [catalog,setCatalog]=useState<GoogleCalendar[]|null>(null),[colors,setColors]=useState<GoogleEventColor[]>([]),[error,setError]=useState(''),[retry,setRetry]=useState(0);
  useEffect(()=>{let live=true;setCatalog(null);setColors([]);setError('');if(view.google.authorized)Promise.all([api<GoogleCalendar[]>('user-self/google/calendars'),api<GoogleEventColor[]>('user-self/google/colors')]).then(([items,palette])=>{if(live){setCatalog(items);setColors(palette);}}).catch(()=>{if(live)setError('Could not load your calendar list. Saved choices have not changed.');});return()=>{live=false;};},[view.profile_id,retry]);
  return <section><h2><CalendarDays/> Choose your calendars</h2><p>Agenda: select all that apply. To-dos: one calendar of all-day tasks; each event’s end is its due date. Only your chosen completed color marks a task done.</p>
    {!view.google.authorized?<p>No Google account linked yet. You can finish setup and add it later.</p>:!catalog?<><p role="status">{error||'Loading your calendars…'}</p><button disabled={busy} onClick={()=>setRetry(value=>value+1)}>Retry my calendar list</button></>:<form onSubmit={event=>{event.preventDefault();const form=new FormData(event.currentTarget);void run(async()=>{await api('user-self/settings','PATCH',{visible_calendar_ids:form.getAll('agenda').map(String),todo_calendar_id:String(form.get('todo'))||null,todo_completed_color_id:String(form.get('color'))||null});await api('user-self/google/sync','POST',{});await onSaved();});}}>
      <div className="user-calendars">{catalog.map(item=><label key={item.id} className="user-check"><input type="checkbox" name="agenda" value={item.id} defaultChecked={view.personal.visible_calendar_ids.includes(item.id)} disabled={busy}/><i style={{background:/^#[0-9a-f]{6}$/i.test(item.background_color??'')?item.background_color:'var(--accent)'}}/>{item.summary}</label>)}</div>
      <label>To-do calendar<select name="todo" defaultValue={view.personal.todo_calendar_id??''} disabled={busy}><option value="">None</option>{catalog.map(item=><option key={item.id} value={item.id}>{item.summary}</option>)}</select></label>
      <label>Completed task color<select name="color" defaultValue={view.personal.todo_completed_color_id??''} disabled={busy}><option value="">Not chosen</option>{colors.map(item=><option key={item.id} value={item.id}>Color {item.id}</option>)}</select></label>
      <div className="user-palette">{colors.map(item=><span key={item.id}><i style={{background:/^#[0-9a-f]{6}$/i.test(item.background)?item.background:'var(--accent)'}}/>{item.id}</span>)}</div><button disabled={busy}>Save my calendars & continue</button>
    </form>}
  </section>;
}
