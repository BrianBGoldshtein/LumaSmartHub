import { useEffect, useState } from "react";
import {useSetupActivity} from "./setupActivity";
import { ArrowLeft, CalendarDays } from "lucide-react";
import {setupTheme,setupLink} from "./setupTheme";
import {TouchField,TouchInputProvider} from "./TouchField";
import {SystemKeyboardControl} from "./SystemKeyboardControl";
import {googleCallbackMessage} from "./googleSetupState";

type Calendar = { id:string; summary:string; background_color?:string; selected?:boolean; primary?:boolean; access_role?:string };
type EventColor={id:string;background:string};
async function api(path:string, method="GET", body?:unknown) {
  const response = await fetch(`/api/v1/${path}`, {method, headers:{"Content-Type":"application/json"}, body:body === undefined ? undefined : JSON.stringify(body)});
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Could not reach Luma.");
  return data;
}

export function GoogleSetup({demo,embedded=false,onSaved}:{demo:boolean;embedded?:boolean;onSaved?:()=>void}) {
  const [theme,setTheme]=useState(()=>setupTheme(new URLSearchParams(location.search).get("theme")));
  const [status,setStatus] = useState({configured:false,authorized:false,task_updates:false});
  const [calendars,setCalendars] = useState<Calendar[]>([]);
  const [selected,setSelected] = useState<string[]>([]);
  const [todo,setTodo] = useState("");
  const [completedColor,setCompletedColor]=useState(''),[colors,setColors]=useState<EventColor[]>([]);
  const [savedSelection,setSavedSelection]=useState('');
  const [sleepCalendars,setSleepCalendars]=useState<string[]>([]),[sleepTitle,setSleepTitle]=useState("Sleep");
  const [message,setMessage] = useState("");
  const [callbackMessage,setCallbackMessage]=useState(()=>googleCallbackMessage(new URLSearchParams(location.search).get("google_error")));
  const [busy,setBusy] = useState(false);
  const [ready,setReady]=useState(demo),[retry,setRetry]=useState(0);
  useSetupActivity(busy);
  useEffect(()=>{
    if (demo) {
      setStatus({configured:true,authorized:true,task_updates:false});
      setCalendars([{id:"work",summary:"Work",background_color:"#7986cb"},{id:"personal",summary:"Personal",background_color:"#33b679"},{id:'todos',summary:'Tasks',background_color:'#7986cb',access_role:'owner'}]);
      setColors([{id:'2',background:'#7ae7bf'},{id:'5',background:'#fbd75b'},{id:'8',background:'#e1e1e1'},{id:'11',background:'#dc2127'}]);
      setSelected(["work","personal"]);
      setSleepCalendars(["personal"]);
      return;
    }
    Promise.all([api("google/status"),api("settings")]).then(async ([state,settings])=>{
      setStatus(state); setTodo(settings.todo_calendar_id || "");setCompletedColor(settings.todo_completed_color_id || '');
      setTheme(setupTheme(settings.theme));setSleepTitle(settings.sleep_event_title);setSleepCalendars(settings.sleep_calendar_ids);
      if (state.authorized) {
        const [items,eventColors]:[Calendar[],EventColor[]] = await Promise.all([api("google/calendars"),api('google/event-colors')]);
        setColors(eventColors);
        setCalendars(items);
        setSleepCalendars(items.filter(c=>settings.sleep_calendar_ids.includes(c.id) || (c.primary && settings.sleep_calendar_ids.includes("primary"))).map(c=>c.id));
        setSelected(settings.visible_calendar_ids.length ? items.filter(c=>settings.visible_calendar_ids.includes(c.id) || (c.primary && settings.visible_calendar_ids.includes("primary"))).map(c=>c.id) : items.filter(c=>c.selected || c.primary).map(c=>c.id));
      }
      setReady(true);
    }).catch(e=>setMessage(String(e.message)));
  },[demo,retry]);
  const run = async (action:()=>Promise<void>)=>{
    setBusy(true); setMessage("");setCallbackMessage("");
    try { await action(); } catch(e) {setMessage(e instanceof Error ? e.message : "Please try again.");} finally {setBusy(false);}
  };
  const Panel=embedded?"div":"main";
  const selection=JSON.stringify({visible_calendar_ids:selected,todo_calendar_id:todo || null,todo_completed_color_id:completedColor || null,sleep_calendar_ids:sleepCalendars,sleep_event_title:sleepTitle.trim()});
  useEffect(()=>{if(ready && !savedSelection)setSavedSelection(selection);},[ready,selection,savedSelection]);
  if(!ready)return <div className="device-setup"><p role="status">{message || "Loading saved calendar settings…"}</p>{message && <button onClick={()=>{setMessage("");setRetry(value=>value+1);}}>Retry calendar settings</button>}<a href={setupLink(demo,theme,"onboarding")}>Return to guided setup</a></div>;
  return <TouchInputProvider><div className={embedded?"setup-embedded":`app theme-${theme} setup-page`}>{!embedded && <a className="setup-back" href={setupLink(demo,theme,"onboarding")}><ArrowLeft/> Continue guided setup</a>}<Panel className={embedded?"device-setup":"setup-content device-setup"}>
    {!embedded && <><CalendarDays size={40}/><h1>Google Calendar</h1><p>Your calendars. Your colors.</p></>}
    {demo && <p className="setup-note">Preview calendars — no Google account connected.</p>}
    {callbackMessage && <p role="alert" className="setup-message">{callbackMessage}</p>}
    <SystemKeyboardControl demo={demo}/>
    {!status.configured && <section><h2>Connect your account</h2><p>On the Pi, choose your Google Desktop OAuth client JSON, then sign in. The setup guide explains how to create it.</p><label className="upload-label">Choose client JSON<input aria-label="Google OAuth client JSON" type="file" accept=".json,application/json" disabled={busy} onChange={e=>{ const file=e.target.files?.[0]; if(file) void run(async()=>{await api("google/config","POST",JSON.parse(await file.text()));setStatus({...status,configured:true});}); }}/></label></section>}
    {status.configured && <button disabled={busy} onClick={()=>run(async()=>{if(demo){setMessage("Preview only. Sign-in is available on the Pi.");return;}const result=await api("google/authorize","POST");location.assign(result.url);})}>{status.authorized ? "Reconnect Google" : "Sign in with Google"}</button>}
    {status.authorized && <section><h2>Agenda calendars</h2><p className="setup-note">Select all that apply. Events from these calendars appear together, with their Google colors. Sleep and leaving reminders have separate calendar selections.</p><div className="calendar-choices">{calendars.map(calendar=><label key={calendar.id}><input type="checkbox" aria-label={`Agenda calendar: ${calendar.summary}`} checked={selected.includes(calendar.id)} onChange={e=>setSelected(e.target.checked ? [...selected,calendar.id] : selected.filter(id=>id!==calendar.id))}/><i style={{background:calendar.background_color || "#a9dfce"}}/><span>{calendar.summary}</span></label>)}</div>
      <label className="todo-calendar-label">To-do calendar<select value={todo} onChange={e=>setTodo(e.target.value)}><option value="">None</option>{calendars.map(c=><option value={c.id} key={c.id}>{c.summary}</option>)}</select></label>
      {todo && <div className="todo-setup"><p className="setup-note">All-day tasks appear on every day they occupy in Google Calendar. The last visible day is the due date; only the event title becomes the task.</p><h2>Completed color</h2>
        <p className="setup-note">Calendar default = outstanding. Only the selected color = completed. Other custom colors remain outstanding. Changing this choice changes how colors are interpreted; it does not recolor existing tasks.</p>
        <div className="task-colors" role="radiogroup" aria-label="Completed task color">{colors.map(color=><label key={color.id}><input type="radio" name="completed-color" value={color.id} checked={completedColor===color.id} disabled={busy} onChange={()=>setCompletedColor(color.id)}/><i style={{background:color.background}}/><span>Color {color.id}</span></label>)}</div>
        {completedColor && !colors.some(color=>color.id===completedColor) && <p role="alert" className="setup-note">Your saved color is unavailable. Select an available color before updating tasks.</p>}
        <p className="setup-note">{status.task_updates?'Task-update permission granted. Each change still requires calendar write access and an unlocked hub.':'Read-only connection: color changes made in Google still sync here. To complete tasks on Luma, explicitly enable task updates below.'}</p>
        {!status.task_updates && <><p className="setup-note">Google grants event-edit permission across calendars you can edit. Luma restricts its task controls to this selected calendar and changes only an event’s color. Save your selections before continuing to Google consent.</p><button disabled={busy || !completedColor} onClick={()=>run(async()=>{if(selection!==savedSelection){setMessage('Save calendars before enabling task updates.');return;}if(demo){setMessage('Preview only. No permissions requested.');return;}const result=await api('google/authorize-tasks','POST');location.assign(result.url);})}>Enable task updates with Google</button></>}
        {calendars.find(c=>c.id===todo)?.access_role && !['owner','writer'].includes(calendars.find(c=>c.id===todo)!.access_role!) && <p className="setup-note">This calendar is read-only. You can view completion colors, but Google will not allow Luma to change them.</p>}
      </div>}
      <p className="setup-note">Calendar colors stay the same in every theme. Custom event colors take priority.</p>
      <h2>Sleep schedule</h2><p className="setup-note">Choose your sleep calendar below. Add daily timed events named “Sleep”: the start begins night mode, and the end starts the five-minute wake. Overnight and repeating events work. This calendar need not appear on your agenda.</p>
      <div className="calendar-choices">{calendars.map(calendar=><label key={calendar.id}><input type="checkbox" aria-label={`Sleep calendar: ${calendar.summary}`} checked={sleepCalendars.includes(calendar.id)} onChange={e=>setSleepCalendars(e.target.checked?[...sleepCalendars,calendar.id]:sleepCalendars.filter(id=>id!==calendar.id))}/><i style={{background:calendar.background_color || "var(--accent)"}}/><span>{calendar.summary}</span></label>)}</div>
      <TouchField label="Sleep event title" value={sleepTitle} onChange={setSleepTitle} maxLength={100} disabled={busy}/>
      <p className="setup-note">Only matching timed events in the selected sleep calendars control sleep. All-day, cancelled and declined events are ignored. No sleep calendar selected = no automatic sleep schedule. “Good night”, “Good morning” and temporary wake still work.</p>
      <button disabled={busy || !sleepTitle.trim()} onClick={()=>run(async()=>{if(demo){setSavedSelection(selection);setMessage("Preview only. Your Google settings have not changed.");onSaved?.();return;}await api("settings","PATCH",JSON.parse(selection));setSavedSelection(selection);onSaved?.();await api("google/sync","POST");setMessage("Saved and synced. Your account will stay connected after a restart.");})}>{busy ? "Syncing…" : "Save calendars"}</button>
    </section>}
    {message && <p role="status" className="setup-message">{message}</p>}
  </Panel></div></TouchInputProvider>;
}
