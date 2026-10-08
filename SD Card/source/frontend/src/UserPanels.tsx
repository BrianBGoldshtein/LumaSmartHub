import {useEffect,useMemo,useRef,useState,type CSSProperties} from 'react';
import {ChevronLeft,ChevronRight,Check,X,Pause,Play} from 'lucide-react';
import type {Snapshot,CalendarEvent} from './types';
import {userGrid,synchronizedUserSections} from './userPanelState';
import {calendarColor,eventKey,hourRulerTicks} from './agendaState';
import {taskPages,deadlineStatus,taskDueLabel} from './todoState';
import './userPanels.css';

export function UserPanels({snapshot,mode,onInteraction}:{snapshot:Snapshot;mode:'home'|'agenda'|'todos';onInteraction?:()=>void}){
  const panels=snapshot.privacy_redacted?[]:snapshot.user_panels||[];
  const [index,setIndex]=useState(0),[height,setHeight]=useState(600),[paused,setPaused]=useState(false),[selected,setSelected]=useState<string|null>(null);
  const root=useRef<HTMLElement>(null),close=useRef<HTMLButtonElement>(null),returnFocus=useRef<HTMLButtonElement|null>(null);
  const now=Date.parse(snapshot.server_time),timezone=snapshot.settings.timezone;
  const sections=useMemo(()=>synchronizedUserSections(panels,now,height/(panels.length>=4?2:1)),[panels,now,height]);
  const section=sections[((index%Math.max(1,sections.length))+Math.max(1,sections.length))%Math.max(1,sections.length)];
  const clock=(value:string|number)=>new Intl.DateTimeFormat('en-US',{hour:'numeric',minute:'2-digit',timeZone:timezone}).format(new Date(value));
  const today=new Intl.DateTimeFormat('en-CA',{timeZone:timezone,year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(now));
  const detail=panels.flatMap(panel=>panel.agenda.events).find(event=>eventKey(event)===selected);
  const taskGroups=panels.map(panel=>taskPages(panel.todos,index));
  const taskCount=Math.max(1,...taskGroups.map(group=>group.count));
  const allCompleted=taskGroups.some(group=>group.items.length)&&taskGroups.every(group=>!group.items.length||group.completedOnly);
  const count=mode==='agenda'?sections.length:mode==='todos'?taskCount:1;
  useEffect(()=>{const observer=new ResizeObserver(entries=>setHeight(Math.round(entries[0].contentRect.height)));if(root.current)observer.observe(root.current);return()=>observer.disconnect();},[]);
  useEffect(()=>{if(paused||detail||count<=1)return;const handle=setTimeout(()=>setIndex(value=>value+1),mode==='todos'&&allCompleted?4000:9000);return()=>clearTimeout(handle);},[paused,detail,count,index,mode,allCompleted]);
  useEffect(()=>{if(detail)close.current?.focus();},[!!detail,selected]);
  const dismiss=()=>{setSelected(null);returnFocus.current?.focus();};
  if(!panels.length)return null;
  const grid=userGrid(panels.length);
  const style=(event:CalendarEvent)=>({'--event-color':calendarColor(event)} as CSSProperties);
  const eventButton=(event:CalendarEvent)=> <button key={eventKey(event)} className="user-next-event" style={style(event)} onClick={e=>{returnFocus.current=e.currentTarget;setSelected(eventKey(event));}}><time>{event.all_day?'All day':clock(event.start)}</time><strong>{event.summary}</strong></button>;
  return <main ref={root} data-users={panels.length} className={`multi-users ${mode==='home'?'':'page focus-page'} user-mode-${mode}`} onPointerDown={onInteraction} onKeyDown={onInteraction}>
    {mode!=='home'&&<div className="section-heading"><h1>{mode==='agenda'?'Calendar':'To-dos'}</h1>{mode==='agenda'&&section&&<span>{clock(section.start)} – {clock(section.end)}</span>}</div>}
    <section className="user-panel-grid" style={{'--user-columns':grid.columns,'--user-rows':grid.rows} as CSSProperties} aria-label="Present users">
      {panels.map((panel,position)=>{
        const own=section?.panels.find(row=>row.profile_id===panel.profile_id)?.section;
        return <article key={panel.profile_id} className="user-panel" style={{gridColumn:`span ${grid.spans[position]}`}} aria-label={`${panel.nickname} ${mode==='todos'?'tasks':'calendar'}`}>
          <header><h2>{panel.nickname}</h2>{panel.agenda.stale&&<span>Saved</span>}</header>
          {mode==='home'&&<div className="user-next-list">{panel.calendar.slice(0,2).map(eventButton)}{!panel.calendar.length&&<p className="user-empty">Nothing upcoming</p>}</div>}
          {mode==='todos'&&<div className="user-task-list" style={{'--task-rows':Math.max(1,taskGroups[position].items.length)} as CSSProperties}>{taskGroups[position].items.map(task=>{
            const deadline=deadlineStatus(task.due_date,today,snapshot.settings.theme);
            return <article key={eventKey(task)} className={`user-task${task.completed?' is-complete':''}`} style={{...style(task),'--deadline-color':deadline.color} as CSSProperties}>
              <span className="user-task-status" aria-label={task.completed?'Completed':'Outstanding'}>{task.completed?<Check/>:<i/>}</span><div><strong>{task.summary}</strong><small>{taskDueLabel(task.due_date,today)}</small></div><span className="deadline-orb" role="img" aria-label={deadline.label}/>
            </article>;
          })}{!panel.todos.length&&<p className="user-empty">All caught up</p>}</div>}
          {mode==='agenda'&&own&&<>
            {own.allDay.length>0&&<div className="user-all-day">{own.allDay.map(eventButton)}</div>}
            {section.panels.some(row=>row.section.items.length>0)&&<div className="user-timeline">
              {hourRulerTicks(section.start,section.end).map(tick=><div key={tick} className="user-hour" style={{top:`${(tick-section.start)/(section.end-section.start)*100}%`}}><time>{clock(tick)}</time><span/></div>)}
              <div className="user-appointments"><div className="user-appointment-track" style={{'--user-lanes':Math.max(1,...own.items.map(item=>item.columns))} as CSSProperties}>{own.items.map(item=><button key={eventKey(item.event)} className="user-appointment" style={{...style(item.event),top:`${item.top}%`,height:`${item.height}%`,left:`${item.column/item.columns*100}%`,width:`${100/item.columns}%`}} aria-label={`${item.event.summary}, ${clock(item.event.start)} to ${clock(item.event.end)}`} onClick={e=>{returnFocus.current=e.currentTarget;setSelected(eventKey(item.event));}}><strong>{item.event.summary}</strong><time>{clock(item.event.start)} – {clock(item.event.end)}</time></button>)}</div></div>
              {now>=section.start&&now<section.end&&<div className="user-now" style={{top:`${(now-section.start)/(section.end-section.start)*100}%`}}/>}
            </div>}
          </>}
          {mode==='agenda'&&!section&&<p className="user-empty">Nothing upcoming</p>}
        </article>;
      })}
    </section>
    {count>1&&<footer className="user-controls"><button aria-label="Previous shared section" onClick={()=>{setPaused(true);setIndex(value=>value-1);}}><ChevronLeft/></button><span>{((index%count)+count)%count+1} / {count}</span><button aria-label="Next shared section" onClick={()=>{setPaused(true);setIndex(value=>value+1);}}><ChevronRight/></button><button aria-label={paused?'Resume all panels':'Pause all panels'} onClick={()=>setPaused(value=>!value)}>{paused?<Play/>:<Pause/>}</button></footer>}
    {detail&&<div className="agenda-detail-shade" onClick={dismiss}><section className="agenda-detail" role="dialog" aria-modal="true" aria-label="Event details" style={style(detail)} onClick={e=>e.stopPropagation()} onKeyDown={event=>{if(event.key==='Escape')dismiss();if(event.key==='Tab'){event.preventDefault();close.current?.focus();}}}><button ref={close} aria-label="Close event details" onClick={dismiss}><X/></button><h2>{detail.summary}</h2><p>{detail.all_day?'All day':`${clock(detail.start)} – ${clock(detail.end)}`}</p>{detail.location&&<p>{detail.location}</p>}</section></div>}
  </main>;
}
