import {useContext,useEffect,useState} from 'react';
import {CalendarDays} from 'lucide-react';
import {SetupActivity} from './setupActivity';
import {TouchField} from './TouchField';
import {dateCaption,dateColor,sampleDates,type CountdownConfig,type CountdownItem,type CountdownView} from './countdownState';
import './countdowns.css';

type Draft={title:string;day:string;at:string;timezone:string;annual:boolean;public:boolean;item_id?:string;revision?:string};
type Candidate={id:string;calendar_id:string;title:string;start:string;end:string;all_day:boolean;color?:string|null};
type Calendar={id:string;summary:string};
const empty:CountdownConfig={items:[],views:[],limit:12,recovery_error:false};
async function api(path:string,method='GET',body?:unknown){
  const response=await fetch(`/api/v1/${path}`,{method,cache:'no-store',headers:{'Content-Type':'application/json'},body:body===undefined?undefined:JSON.stringify(body)});
  const data=await response.json();if(!response.ok)throw Error(typeof data.detail==='string'?data.detail:'Check the date, time and title, then try again.');return data;
}
const localDay=(zone:string)=>new Intl.DateTimeFormat('en-CA',{year:'numeric',month:'2-digit',day:'2-digit',timeZone:zone}).format(new Date());
function preview(item:CountdownItem):CountdownView{
  const day=item.date||item.start?.slice(0,10)||'2026-10-10';
  const days=Math.round((Date.parse(day)-Date.parse(localDay(item.timezone)))/86400000);
  return {id:item.id,title:item.title,public:item.public,source:item.source,target:item.start||`${day}T12:00:00Z`,date:day,timed:!!item.time,label:days===0?'Today':days===1?'Tomorrow':days<0?'Passed':`${days} days`,value:days>1?days:null,unit:days>1?'days':null,state:'ready',past:days<0};
}

export function CountdownSetup({demo,onDirty,onBusy,onSaved}:{demo:boolean;onDirty:(value:boolean)=>void;onBusy:(value:boolean)=>void;onSaved?:()=>void}){
  const activity=useContext(SetupActivity);
  const [config,setConfig]=useState<CountdownConfig>(empty),[ready,setReady]=useState(false),[busy,setBusy]=useState(false),[message,setMessage]=useState(''),[retry,setRetry]=useState(0);
  const [zone,setZone]=useState('America/Los_Angeles'),[authorized,setAuthorized]=useState(false),[mode,setMode]=useState<'list'|'manual'|'google'>('list');
  const [draft,setDraft]=useState<Draft>({title:'',day:'',at:'',timezone:'America/Los_Angeles',annual:false,public:false}),[baseline,setBaseline]=useState('');
  const [calendars,setCalendars]=useState<Calendar[]>([]),[calendar,setCalendar]=useState(''),[start,setStart]=useState(''),[end,setEnd]=useState('');
  const [candidates,setCandidates]=useState<Candidate[]>([]),[nextPage,setNextPage]=useState<string|null>(null),[selected,setSelected]=useState<Candidate|null>(null),[pinPublic,setPinPublic]=useState(false);
  const [remove,setRemove]=useState<CountdownItem|null>(null),[discard,setDiscard]=useState(false);
  const dirty=mode==='manual'?JSON.stringify(draft)!==baseline:mode==='google'&&!!selected;
  useEffect(()=>{onDirty(dirty);return()=>onDirty(false);},[dirty,onDirty]);
  useEffect(()=>{onBusy(busy);return()=>onBusy(false);},[busy,onBusy]);
  useEffect(()=>{let live=true;
    if(demo){setReady(true);setAuthorized(true);return;}
    Promise.all([api('countdowns'),api('settings'),api('google/status')]).then(([saved,settings,status])=>{if(live){setConfig(saved);setZone(settings.timezone);setAuthorized(status.authorized);setReady(true);}}).catch(e=>{if(live)setMessage(e.message);});
    return()=>{live=false;};
  },[demo,retry]);
  const edit=<K extends keyof Draft>(key:K,value:Draft[K])=>{activity.edited();setDraft(current=>({...current,[key]:value}));setMessage('');};
  async function run(action:()=>Promise<void>){setBusy(true);setMessage('');try{await action();}catch(e){setMessage((e as Error).message);}finally{setBusy(false);}}
  const saved=(next:CountdownConfig)=>{setConfig(next);setMode('list');setSelected(null);setRemove(null);setDiscard(false);setMessage(demo?'Preview saved here only — no device changes.':'Saved on Luma.');onSaved?.();};
  const chooseManual=(item?:CountdownItem)=>{
    const values:Draft={title:item?.title||'',day:item?.date||localDay(zone),at:item?.time||'',timezone:item?.timezone||zone,annual:item?.annual||false,public:item?.public||false,...(item?{item_id:item.id,revision:item.revision}:{})};
    setDraft(values);setBaseline(JSON.stringify(values));setMode('manual');setMessage('');
  };
  const back=()=>{if(dirty)setDiscard(true);else{setMode('list');setSelected(null);setMessage('');}};
  async function saveManual(){
    const parsed=new Date(`${draft.day}T12:00:00Z`);
    if(!draft.title.trim()||draft.title.trim().length>100||!/^\d{4}-\d{2}-\d{2}$/.test(draft.day)||Number.isNaN(parsed.getTime())||parsed.toISOString().slice(0,10)!==draft.day||parsed.getUTCFullYear()<2000||parsed.getUTCFullYear()>2100)throw Error('Choose a title and a valid date from 2000 to 2100.');
    try{new Intl.DateTimeFormat('en-US',{timeZone:draft.timezone}).format(parsed);}catch{throw Error('Use an IANA timezone, such as America/Los_Angeles.');}
    if(demo){const item:CountdownItem={id:draft.item_id||crypto.randomUUID(),revision:crypto.randomUUID(),source:'manual',title:draft.title.trim(),date:draft.day,time:draft.at||null,timezone:draft.timezone,annual:draft.annual,public:draft.public};const items=[...config.items.filter(i=>i.id!==item.id),item];saved({...config,items,views:items.map(preview)});return;}
    saved(await api('countdowns/manual','POST',{...draft,at:draft.at||null}));
  }
  async function openGoogle(){
    if(!authorized){setMessage('Connect Google Calendar in its setup panel first. Manual dates work without an account.');return;}
    const choices:Calendar[]=demo?[{id:'sample',summary:'Sample calendar'}]:await api('google/calendars');
    setCalendars(choices);setCalendar(choices[0]?.id||'');setStart(localDay(zone));
    const later=new Date(`${localDay(zone)}T12:00:00Z`);later.setUTCDate(later.getUTCDate()+31);setEnd(later.toISOString().slice(0,10));
    setCandidates([]);setNextPage(null);setSelected(null);setPinPublic(false);setMode('google');
  }
  async function search(pageToken?:string){
    setSelected(null);
    if(!calendar)throw Error('Choose a calendar first.');
    if(demo){setCandidates(sampleDates.map(item=>({id:item.id,calendar_id:'sample',title:item.title,start:item.target,end:item.target,all_day:!item.timed,color:item.color})));setNextPage(null);return;}
    const result=await api('countdowns/search','POST',{calendar_id:calendar,start,end,page_token:pageToken});setCandidates(result.events);setNextPage(result.next_page||null);
    if(!result.events.length)setMessage('No events on this page. Try another date window, or the next page if available.');
  }
  async function pin(){
    if(!selected)return;
    if(demo){const item:CountdownItem={id:crypto.randomUUID(),revision:crypto.randomUUID(),source:'google',title:selected.title,timezone:zone,public:pinPublic,start:selected.start,all_day:selected.all_day,calendar_id:selected.calendar_id,event_id:selected.id};const items=[...config.items,item];saved({...config,items,views:items.map(preview)});return;}
    saved(await api('countdowns/google','POST',{calendar_id:selected.calendar_id,event_id:selected.id,public:pinPublic}));
  }
  async function visibility(item:CountdownItem){
    if(demo){const items=config.items.map(i=>i.id===item.id?{...i,public:!i.public}:i);saved({...config,items,views:items.map(preview)});return;}
    saved(await api(`countdowns/${item.id}/visibility`,'PATCH',{revision:item.revision,public:!item.public}));
  }
  async function removeDate(){
    if(!remove)return;
    if(demo){const items=config.items.filter(i=>i.id!==remove.id);saved({...config,items,views:items.map(preview)});return;}
    saved(await api(`countdowns/${remove.id}`,'DELETE',{revision:remove.revision}));
  }
  const publicChoice=(value:boolean,set:(next:boolean)=>void)=><><label className="extras-toggle"><input type="checkbox" checked={value} disabled={busy} onChange={event=>{activity.edited();set(event.target.checked);}}/><span>Show this date in private standby</span></label><p className="setup-note">Off by default. If enabled, anyone in the room can see this title and date without your phone. Google title/date changes will also be public.</p></>;
  return <><h2><CalendarDays/>Important dates</h2><p>A few things to look forward to.</p>
    {!ready?<><p role="status">{message||'Loading saved dates…'}</p><button disabled={busy} onClick={()=>{setMessage('');setRetry(value=>value+1);}}>Retry</button></>:config.recovery_error?<p role="alert">Saved dates need recovery. The original data has not been overwritten.</p>:<>
    {mode==='list'?<>
      <p className="setup-note">{config.items.length} / {config.limit} dates saved. Private unless you choose otherwise. Visible dates join the screen cycle automatically.</p>
      <div className="date-actions"><button disabled={busy||config.items.length>=config.limit} onClick={()=>chooseManual()}>Add a date</button><button disabled={busy||config.items.length>=config.limit} onClick={()=>void run(openGoogle)}>Link Google event</button></div>
      <div className="date-editor-list">{config.items.map(item=>{const view=config.views.find(v=>v.id===item.id);return <article key={item.id} style={{borderLeftColor:dateColor(view?.color)}}><h3>{item.title}</h3><p className="setup-note">{view?`${view.label} · ${dateCaption(view)}`:item.date} · {item.public?'Public':'Private'}{item.annual?' · Annual':''}</p><div className="date-actions">{item.source==='manual'&&<button disabled={busy} onClick={()=>chooseManual(item)}>Edit {item.title}</button>}<button disabled={busy} onClick={()=>setRemove(item)}>Remove {item.title}</button></div><details><summary>Visibility for {item.title}</summary><p className="setup-note">Making public reveals this title/date without your phone, including future Google changes.</p><button disabled={busy} onClick={()=>void run(()=>visibility(item))}>{item.public?'Make private':'Make public'}</button></details></article>;})}</div>
      {!!config.items.some(item=>item.source==='google')&&<button disabled={busy} onClick={()=>void run(async()=>{if(demo){setMessage('Preview only — no Google request.');return;}setConfig(await api('countdowns/refresh','POST'));setMessage('Refresh finished. Check each event’s status.');})}>Refresh linked dates</button>}
      <p className="setup-note">Try “Hey Luma, show countdowns”. Past dates remain here for editing; only upcoming dates and today appear on the slide.</p>
    </>:<>
      <button disabled={busy} onClick={back}>Back to saved dates</button>
      {mode==='manual'?<form onSubmit={event=>{event.preventDefault();void run(saveManual);}}>
        <TouchField label="Date title" value={draft.title} onChange={value=>edit('title',value)} maxLength={100} required disabled={busy}/>
        <label>Date<input type="date" min="2000-01-01" max="2100-12-31" value={draft.day} required disabled={busy} onInput={event=>edit('day',event.currentTarget.value)} onChange={event=>edit('day',event.target.value)}/></label>
        <details><summary>Time & annual repeat</summary><label>Time · optional<input type="time" value={draft.at} disabled={busy} onInput={event=>edit('at',event.currentTarget.value)} onChange={event=>edit('at',event.target.value)}/></label><TouchField label="Date timezone" value={draft.timezone} onChange={value=>edit('timezone',value)} maxLength={100} required disabled={busy}/><label className="extras-toggle"><input type="checkbox" checked={draft.annual} disabled={busy} onChange={event=>edit('annual',event.target.checked)}/><span>Repeat each year</span></label><p className="setup-note">February 29 uses February 28 in non-leap years. Repeated daylight-saving hours use the first occurrence; skipped times require another time. Future annual gaps move forward.</p></details>
        {publicChoice(draft.public,value=>edit('public',value))}<button disabled={busy}>{busy?'Saving…':'Save date'}</button>
      </form>:<>
        <p className="setup-note">Read-only. Pin one occurrence, never change Google. Choose up to 93 days at a time; the end date is exclusive. Only linked events refresh in the background.</p>
        <label>Google calendar<select disabled={busy} value={calendar} onChange={event=>{setCalendar(event.target.value);setCandidates([]);setSelected(null);setNextPage(null);}}>{calendars.map(cal=><option key={cal.id} value={cal.id}>{cal.summary}</option>)}</select></label>
        <div className="setup-grid"><label>From date<input type="date" value={start} disabled={busy} onInput={event=>{setStart(event.currentTarget.value);setCandidates([]);setSelected(null);setNextPage(null);}} onChange={event=>{setStart(event.target.value);setCandidates([]);setSelected(null);setNextPage(null);}}/></label><label>Until date · exclusive<input type="date" value={end} disabled={busy} onInput={event=>{setEnd(event.currentTarget.value);setCandidates([]);setSelected(null);setNextPage(null);}} onChange={event=>{setEnd(event.target.value);setCandidates([]);setSelected(null);setNextPage(null);}}/></label></div>
        <div className="date-actions"><button disabled={busy} onClick={()=>void run(()=>search())}>Find events</button>{nextPage&&<button disabled={busy} onClick={()=>void run(()=>search(nextPage))}>Next events</button>}</div>
        {candidates.map(item=><button className="date-choice" key={item.id} disabled={busy} onClick={()=>{activity.edited();setSelected(item);setPinPublic(false);}} style={{borderLeft:`6px solid ${dateColor(item.color)}`}}>{item.title}<span>{new Intl.DateTimeFormat('en-US',{dateStyle:'medium',...(item.all_day?{}:{timeStyle:'short' as const}),timeZone:zone}).format(new Date(item.start))}{item.all_day?' · All day':''}</span></button>)}
        {selected&&<section className="date-confirm"><h3>Pin {selected.title}?</h3>{publicChoice(pinPublic,setPinPublic)}<button disabled={busy} onClick={()=>void run(pin)}>Pin this event</button></section>}
      </>}
      {discard&&<div className="date-confirm" role="alert"><p>Discard these unsaved date edits?</p><div className="date-actions"><button disabled={busy} onClick={()=>{setMode('list');setSelected(null);setDiscard(false);onSaved?.();}}>Discard edits</button><button disabled={busy} onClick={()=>setDiscard(false)}>Keep editing</button></div></div>}
    </>}
    {remove&&<section className="date-confirm" role="alert"><p>Remove “{remove.title}” from Luma? This does not delete anything from Google Calendar.</p><div className="date-actions"><button disabled={busy} onClick={()=>void run(removeDate)}>Remove from Luma</button><button disabled={busy} onClick={()=>setRemove(null)}>Keep date</button></div></section>}
    {message&&<p className="setup-message" role="status">{message}</p>}
    </>}
  </>;
}
import {setupFetch as fetch} from './setupTransport';
