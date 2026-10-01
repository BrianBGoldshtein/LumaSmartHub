import {useEffect,useState,type CSSProperties} from 'react';
import {ListChecks,ChevronLeft,ChevronRight,RefreshCw,Check} from 'lucide-react';
import type {Snapshot,CalendarEvent} from './types';
import {taskPages,taskDueLabel,deadlineStatus} from './todoState';
import {setupLink} from './setupTheme';

// Only the next page number survives slide cycling; never store task contents
// or completion guesses locally. Outstanding and completed tasks remain reachable.
let nextTaskPage=0;
export function TodosPage({snapshot,onUpdate,demo}:{snapshot:Snapshot;onUpdate:(next:Snapshot)=>void;demo:boolean}){
  const [page,setPage]=useState(()=>nextTaskPage),[busy,setBusy]=useState(false),[message,setMessage]=useState('');
  const pages=taskPages(snapshot.todos,page);
  const today=new Intl.DateTimeFormat('en-CA',{timeZone:snapshot.settings.timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
  useEffect(()=>{nextTaskPage=pages.index+1;},[pages.index]);
  useEffect(()=>{if(busy || pages.count<=1)return;const handle=setTimeout(()=>setPage(value=>value+1),pages.completedOnly?4000:8000);return()=>clearTimeout(handle);},[busy,pages.count,pages.completedOnly,page]);
  async function change(task:CalendarEvent){
    if(busy)return;
    setBusy(true);setMessage('');
    try{
      if(demo){onUpdate({...snapshot,todos:snapshot.todos.map(item=>item.id===task.id?{...item,completed:true,event_color:'#7ae7bf'}:item)});setMessage('Preview only · Google unchanged');return;}
      const response=await fetch('/api/v1/todos/complete',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({calendar_id:task.calendar_id,event_id:task.id,etag:task.etag,completed:true})});
      const data=await response.json();if(!response.ok)throw Error(data.detail || 'Task update not confirmed. Refresh before retrying.');
      onUpdate(data);setMessage('Completed in Google');
    }catch(error){setMessage((error as Error).message);}finally{setBusy(false);}
  }
  async function refresh(){
    setBusy(true);setMessage('');try{
      if(demo){setMessage('Preview only · sample tasks');return;}
      const result=await fetch('/api/v1/google/sync',{method:'POST'});if(!result.ok)throw Error('Google unavailable. Showing saved tasks.');
      const response=await fetch('/api/v1/state');if(!response.ok)throw Error('Could not reload tasks.');onUpdate(await response.json());setMessage('Synced with Google');
    }catch(error){setMessage((error as Error).message);}finally{setBusy(false);}
  }
  return <main className="page focus-page todos-page"><div className="section-heading"><h1>To-dos</h1><span><ListChecks/>{pages.total}</span></div>
    <section className="card todos-card">{pages.items.map(task=>{const deadline=deadlineStatus(task.due_date,today,snapshot.settings.theme);return <article className={`todo-row${task.completed?' is-complete':''}`} style={{'--event-color':/^#[0-9a-f]{6}$/i.test(task.event_color || task.calendar_color || '')?task.event_color || task.calendar_color:'var(--accent)','--deadline-color':deadline.color} as CSSProperties} key={`${task.calendar_id}:${task.id}`}>
      {task.completed?<span className="todo-check" role="img" aria-label="Completed"><Check aria-hidden="true"/></span>
        :<button className="todo-check" aria-label={`Complete: ${task.summary}`} aria-pressed={false} disabled={busy || (!demo && (!snapshot.todo_controls?.can_update || !task.etag))} onClick={()=>void change(task)}/>}
      <div><h3>{task.summary}</h3><p>{taskDueLabel(task.due_date,today)}</p></div>
      <span className={`deadline-orb deadline-${deadline.kind}`} role="img" aria-label={deadline.label} title={deadline.label}/>
    </article>;})}{!pages.total && <div className="empty-message"><ListChecks/><span>All caught up.</span></div>}</section>
    <footer className="todo-footer"><div className="todo-pagination">{pages.count>1 && <><button disabled={busy} aria-label="Previous tasks" onClick={()=>setPage(value=>value-1)}><ChevronLeft/></button><span>{pages.index+1} / {pages.count}</span><button disabled={busy} aria-label="Next tasks" onClick={()=>setPage(value=>value+1)}><ChevronRight/></button></>}<button disabled={busy} aria-label="Refresh tasks from Google" onClick={()=>void refresh()}><RefreshCw/></button></div>
      <span role="status">{busy?'Syncing…':message || (snapshot.todo_controls?.stale?'Saved tasks · awaiting sync':'')}</span>{!demo && !snapshot.todo_controls?.can_update && <a href={setupLink(false,snapshot.settings.theme,'google')}>Set up task updates</a>}
    </footer>
  </main>;
}
