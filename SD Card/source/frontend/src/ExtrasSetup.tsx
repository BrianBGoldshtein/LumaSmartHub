import {useEffect,useRef,useState} from 'react';
import {Timer,CloudSun,ArrowLeft,Footprints,Moon,CalendarDays,TrainFront,Wind,HardDrive} from 'lucide-react';
import {DepartureSetup} from './DepartureSetup';
import {NightSetup} from './NightSetup';
import {CountdownSetup} from './CountdownSetup';
import {TransitSetup} from './TransitSetup';
import {RoomSetup} from './RoomSetup';
import {FanSetup} from './FanSetup';
import {SceneSetup} from './SceneSetup';
import {BackupSetup} from './BackupSetup';
import {TouchField,TouchInputProvider} from './TouchField';
import {useSetupActivity} from './setupActivity';
import {setupLink,setupTheme} from './setupTheme';
import {scrollSetupToTop} from './setupScroll';
import {extraPreferences,extraPatch,type ExtraTask,type ExtraPreferences} from './weatherState';

export function ExtrasSetup({demo,embedded=false,onSaved,locked=false}:{demo:boolean;embedded?:boolean;onSaved?:()=>void;locked?:boolean}){
  const shellRef=useRef<HTMLDivElement>(null);
  const [values,setValues]=useState(()=>extraPreferences()),[baseline,setBaseline]=useState(()=>extraPreferences());
  const [task,setTask]=useState<ExtraTask|'departure'|'night'|'countdowns'|'transit'|'room'|'fans'|'scenes'|'backup'|null>(null),[saving,setBusy]=useState(false),[ready,setReady]=useState(demo),[message,setMessage]=useState('');
  const [childDirty,setChildDirty]=useState(false),[childBusy,setChildBusy]=useState(false);
  const busy=saving||childBusy;
  const [hasLocation,setHasLocation]=useState(false),[retry,setRetry]=useState(0),[theme,setTheme]=useState(()=>setupTheme(new URLSearchParams(location.search).get('theme')));
  const activity=useSetupActivity(busy),dirty=childDirty||JSON.stringify(values)!==JSON.stringify(baseline);
  useEffect(()=>{
    const warn=(event:BeforeUnloadEvent)=>{if(dirty){event.preventDefault();event.returnValue='';}};
    window.addEventListener('beforeunload',warn);return()=>window.removeEventListener('beforeunload',warn);
  },[dirty]);
  useEffect(()=>{
    if(demo)return;
    const controller=new AbortController();
    fetch('/api/v1/settings',{signal:controller.signal}).then(async response=>{if(!response.ok)throw Error();return response.json();}).then(data=>{
      const saved=extraPreferences(data);setValues(saved);setBaseline(saved);setTheme(setupTheme(data.theme));setHasLocation(data.latitude!=null && data.longitude!=null);setReady(true);
    }).catch(()=>{if(!controller.signal.aborted)setMessage('Could not load preferences. Try again when Luma reconnects.');});
    return()=>controller.abort();
  },[demo,retry]);
  const edit=(key:keyof ExtraPreferences,value:string|boolean)=>{activity.edited();setValues(current=>({...current,[key]:value}));setMessage('');};
  function choose(next:ExtraTask|'departure'|'night'|'countdowns'|'transit'|'room'|'fans'|'scenes'|'backup'|null){
    if(dirty){setMessage('Save these preferences before choosing another extra. You can also leave this setup step and discard edits.');return;}
    setTask(next);setMessage('');
    scrollSetupToTop(shellRef.current);
  }
  async function save(){
    if(!task || task==='departure' || task==='night' || task==='countdowns' || task==='transit' || task==='room' || task==='fans' || task==='scenes' || task==='backup')return;
    let patch:Record<string,number|boolean>;
    try{patch=extraPatch(task,values);}catch(e){setMessage((e as Error).message);return;}
    setBusy(true);setMessage('');
    try{
      if(!demo){const response=await fetch('/api/v1/settings',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify(patch)});if(!response.ok)throw Error('Could not save preferences. Please try again.');}
      setBaseline({...values});setMessage(demo?'Preview checked — no device changes.':'Preferences saved.');onSaved?.();
    }catch(e){setMessage((e as Error).message);}finally{setBusy(false);}
  }
  const Panel=embedded?'div':'main';
  const number=(key:keyof ExtraPreferences,label:string,signed=false)=><TouchField label={label} value={String(values[key])} onChange={value=>edit(key,value)} mode={signed?'decimal':'digits'} maxLength={signed?4:3} required disabled={busy}/>;
  return <TouchInputProvider><div ref={shellRef} className={embedded?'setup-embedded':`app theme-${theme} setup-page`}><Panel className={embedded?'device-setup':'setup-content device-setup'}>
    {!embedded && <><a className="setup-back" href={setupLink(demo,theme,'device')} onClick={event=>{if(dirty||busy){event.preventDefault();setMessage('Save your preferences before leaving.');}}}>← All settings</a><h1>Make it yours.</h1></>}
    {!ready?<><p role="status">{message || 'Loading saved preferences…'}</p>{message && <button onClick={()=>{setMessage('');setRetry(value=>value+1);}}>Retry</button>}</>:<>
      {!task?<section><h2>Daily rhythm</h2><p>Choose an extra to personalize. Everything here is optional.</p><div className="extras-choices">
        <button onClick={()=>choose('timer')}><Timer aria-hidden="true"/><strong>Focus & break</strong><span>{baseline.timer_focus_minutes} / {baseline.timer_break_minutes} min · Ready locally</span></button>
        <button onClick={()=>choose('weather')}><CloudSun aria-hidden="true"/><strong>Weather hints</strong><span>{baseline.weather_nudges_enabled?hasLocation?'Enabled · forecast required':'Needs a location':'Off · optional'}</span></button>
        <button onClick={()=>choose('departure')}><Footprints aria-hidden="true"/><strong>Leave soon</strong><span>Optional · Google Calendar</span></button>
        <button onClick={()=>choose('night')}><Moon aria-hidden="true"/><strong>Night & wake</strong><span>Dim clock · gentle mornings</span></button>
      </div><h2>Dates & travel</h2><div className="extras-choices"><button onClick={()=>choose('countdowns')}><CalendarDays aria-hidden="true"/><strong>Important dates</strong><span>Manual dates · Google event links</span></button><button onClick={()=>choose('transit')}><TrainFront aria-hidden="true"/><strong>Transit</strong><span>Saved stops · live or scheduled departures</span></button></div><h2>Room devices</h2><div className="extras-choices"><button onClick={()=>choose('room')}><Wind aria-hidden="true"/><strong>Air purifier</strong><span>Optional · VeSync cloud connection</span></button><button onClick={()=>choose('fans')}><Wind aria-hidden="true"/><strong>Two fans</strong><span>USB infrared · guided learning & tests</span></button><button onClick={()=>choose('scenes')}><Moon aria-hidden="true"/><strong>Room scenes</strong><span>Morning · Night · Arrive · Away</span></button></div><h2>Keep & restore</h2><div className="extras-choices"><button onClick={()=>choose('backup')}><HardDrive aria-hidden="true"/><strong>Settings backup</strong><span>Encrypted USB · review before restore</span></button></div></section>:<section>
        <button disabled={busy} onClick={()=>choose(null)}><ArrowLeft aria-hidden="true"/> Choose another extra</button>
        {task==='backup'?<BackupSetup demo={demo} locked={locked} onSaved={onSaved}/>:task==='scenes'?locked?<p role="status">Unlock with your nearby phone or PIN to configure scenes.</p>:<SceneSetup demo={demo} onDirty={setChildDirty} onBusy={setChildBusy} onSaved={()=>{setMessage('');onSaved?.();}}/>:task==='fans'?locked?<p role="status">Unlock with your nearby phone or PIN to configure fans.</p>:<FanSetup demo={demo} onDirty={setChildDirty} onBusy={setChildBusy} onSaved={()=>{setMessage('');onSaved?.();}}/>:task==='room'?locked?<p role="status">Unlock with your nearby phone or PIN to configure room devices.</p>:<RoomSetup demo={demo} onDirty={setChildDirty} onBusy={setChildBusy} onSaved={()=>{setMessage('');onSaved?.();}}/>:task==='transit'?locked?<p role="status">Unlock with your nearby phone or PIN to configure transit.</p>:<TransitSetup demo={demo} onDirty={setChildDirty} onBusy={setChildBusy} onSaved={()=>{setMessage('');onSaved?.();}}/>:task==='countdowns'?locked?<p role="status">Private dates are hidden. Connect your nearby phone or unlock with your PIN from the dashboard to continue.</p>:<CountdownSetup demo={demo} onDirty={setChildDirty} onBusy={setChildBusy} onSaved={()=>{setMessage('');onSaved?.();}}/>:task==='departure'?<DepartureSetup demo={demo} onDirty={setChildDirty} onBusy={setChildBusy} onSaved={()=>{setMessage('');onSaved?.();}}/>:task==='night'?<NightSetup demo={demo} onDirty={setChildDirty} onBusy={setChildBusy} onSaved={()=>{setMessage('');onSaved?.();}}/>:<>
        <h2>{task==='timer'?<><Timer/>Focus & break</>:<><CloudSun/>Weather hints</>}</h2>
        <p>{task==='timer'?'One local timer. No account or phone needed.':'One useful forecast hint, inside your weather card. No extra alerts.'}</p>
        <form onSubmit={event=>{event.preventDefault();void save();}}>
          {task==='timer'?<div className="setup-grid">{number('timer_focus_minutes','Focus · minutes')}{number('timer_break_minutes','Break · minutes')}</div>:<>
            <label className="extras-toggle"><input type="checkbox" checked={values.weather_nudges_enabled} disabled={busy} onChange={event=>edit('weather_nudges_enabled',event.target.checked)}/><span>Show weather hints</span></label>
            {!hasLocation && <p className="setup-note">{demo?'Preview only.':'No location saved yet.'} Hints need a location in Your space and an internet connection. You can save preferences now.</p>}
            <p className="setup-note">Over the next six hours: wet weather first, then wind, then heat or cold. Missing or stale forecasts produce no hint. Hints are public, including in private standby.</p>
            <details><summary>Adjust thresholds</summary><div className="setup-grid">{number('weather_rain_percent','Precipitation chance · %')}{number('weather_gust_mph','Wind gusts · mph')}{number('weather_hot_f','Hot · feels like °F',true)}{number('weather_cold_f','Cool · feels like °F',true)}</div></details>
          </>}
          <button disabled={busy}>{busy?'Saving…':task==='timer'?'Save timer defaults':'Save weather preferences'}</button>
        </form>
        {task==='timer'?<><p className="setup-note">A clear multi-tone local alarm sounds at completion, even during Sleep/display-off. Hub volume at zero stays silent; a reboot never replays an old alarm.</p><p className="setup-note">Try “Hey Luma, start focus timer” or open Focus timer from dashboard controls. Custom labels stay hidden in private standby.</p></>:<p className="setup-note">Uses the same Open-Meteo forecast, refreshed about every 15 minutes. Convenience hints, not emergency alerts. No account required; your configured coordinates are sent to the weather provider.</p>}
        </>}
      </section>}
      <details><summary>About optional features</summary><p className="setup-note">Room scenes remain off until you configure and explicitly enable them. USB backups include encrypted portable settings, not accounts, credentials, recordings or game scores. Backups are best tested before you rely on them.</p></details>
    </>}
    {ready && message && <p className="setup-message" role="status">{message}</p>}
  </Panel></div></TouchInputProvider>;
}
