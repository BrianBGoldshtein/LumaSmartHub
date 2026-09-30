import {useEffect,useMemo,useRef,useState,type CSSProperties} from 'react';
import {ChevronLeft,ChevronRight,Pause,Play,X} from 'lucide-react';
import type {Snapshot,CalendarEvent} from './types';
import {agendaSections,calendarColor,eventKey,HOUR} from './agendaState';
import './agenda.css';

// Only a position survives slide cycling, never event content or private text.
let nextAgendaSection=0;
export function AgendaPage({snapshot,onInteraction}:{snapshot:Snapshot;onInteraction?:()=>void}){
  const [index,setIndex]=useState(()=>nextAgendaSection),[columns,setColumns]=useState(2),[paused,setPaused]=useState(false),[selected,setSelected]=useState<string|null>(null);
  const root=useRef<HTMLElement>(null),close=useRef<HTMLButtonElement>(null),restoreFocus=useRef<HTMLButtonElement|null>(null);
  const agenda=snapshot.privacy_redacted?null:snapshot.agenda;
  const sections=useMemo(()=>agenda?agendaSections(agenda,columns):[],[agenda,columns]);
  const page=((index%Math.max(1,sections.length))+Math.max(1,sections.length))%Math.max(1,sections.length),section=sections[page];
  const detail=agenda?.events.find(event=>eventKey(event)===selected);
  const timezone=snapshot.settings.timezone;
  const clock=(value:string|number)=>new Intl.DateTimeFormat('en-US',{hour:'numeric',minute:'2-digit',timeZone:timezone}).format(new Date(value));
  const date=(value:string|number)=>new Intl.DateTimeFormat('en-US',{weekday:'short',month:'short',day:'numeric',timeZone:timezone}).format(new Date(value));
  useEffect(()=>{const observer=new ResizeObserver(entries=>{setColumns(entries[0].contentRect.width<620?1:2);});if(root.current)observer.observe(root.current);return()=>observer.disconnect();},[]);
  useEffect(()=>{nextAgendaSection=page+1;},[page]);
  useEffect(()=>{if(paused||detail||sections.length<=1)return;const timer=setTimeout(()=>setIndex(value=>value+1),9000);return()=>clearTimeout(timer);},[paused,detail,sections.length,index]);
  useEffect(()=>{if(detail)close.current?.focus();},[selected,!!detail]);
  function dismiss(){setSelected(null);restoreFocus.current?.focus();}
  const style=(event:CalendarEvent)=>({'--event-color':calendarColor(event)} as CSSProperties);
  const now=Date.parse(snapshot.server_time);
  return <main ref={root} className="page focus-page day-agenda" onPointerDown={onInteraction} onKeyDown={onInteraction}>
    <div className="section-heading"><h1>Calendar</h1><span>{date(agenda?.start||snapshot.server_time)}</span></div>
    {section? <>
      <div className="agenda-window-title"><h2>{section.allDay.length&&!section.items.length?'All day':`${clock(section.start)} – ${clock(section.end)}`}</h2>{section.lanes>1&&<span>Overlaps {section.lane+1}/{section.lanes}</span>}</div>
      {section.allDay.length>0&&section.items.length>0&&<section className="agenda-all-day-ribbon" aria-label="All-day event">{section.allDay.map(event=><button key={eventKey(event)} style={style(event)} onClick={e=>{restoreFocus.current=e.currentTarget;setSelected(eventKey(event));}}><strong>{event.summary}</strong><span>{event.calendar_name||'All day'} · All day</span></button>)}</section>}
      {section.allDay.length>0&&!section.items.length ? <section className="agenda-all-day" style={{gridTemplateRows:`repeat(${section.allDay.length},minmax(0,1fr))`}} aria-label="All-day events">{section.allDay.map(event=><button key={eventKey(event)} style={style(event)} onClick={e=>{restoreFocus.current=e.currentTarget;setSelected(eventKey(event));}}><strong>{event.summary}</strong><span>{event.calendar_name||'All day'}</span></button>)}</section>:
      <section className="agenda-timeline" aria-label={`Calendar from ${clock(section.start)} to ${clock(section.end)}`}>
        {Array.from({length:Math.ceil((section.end-section.start)/HOUR)+1},(_,i)=>Math.min(section.end,section.start+i*HOUR)).map(tick=><div className="agenda-hour" key={tick} style={{top:`${(tick-section.start)/(section.end-section.start)*100}%`}}><time>{clock(tick)}</time><span/></div>)}
        <div className="agenda-appointments">{section.items.map(item=><button key={eventKey(item.event)} className={`agenda-appointment${item.height<38?' is-compact':''}${item.event.summary.length>44?' is-long-title':''}${item.event.summary.length>90?' is-verbose':''}${Date.parse(item.event.end)<=now?' is-past':''}`} style={{...style(item.event),'--agenda-top':`${item.top}%`,'--agenda-height':`${item.height}%`,'--agenda-left':`${item.column/item.columns*100}%`,'--agenda-width':`${100/item.columns}%`} as CSSProperties} onClick={e=>{restoreFocus.current=e.currentTarget;setSelected(eventKey(item.event));}} aria-label={`${item.event.summary}, ${clock(item.event.start)} to ${clock(item.event.end)}, ${item.event.calendar_name||'Calendar'}`}>
          <strong>{item.event.summary}</strong><time>{clock(item.event.start)} – {clock(item.event.end)}</time>
        </button>)}</div>
        {now>=section.start&&now<section.end&&<div className="agenda-now" style={{top:`${(now-section.start)/(section.end-section.start)*100}%`}} aria-label={`Now ${clock(now)}`}/>}
      </section>}
      <footer className="agenda-controls"><button aria-label="Previous calendar section" onClick={()=>{setPaused(true);setIndex(value=>value-1);}}><ChevronLeft/></button><span>{page+1} / {sections.length}</span><button aria-label="Next calendar section" onClick={()=>{setPaused(true);setIndex(value=>value+1);}}><ChevronRight/></button><button aria-label={paused?'Resume calendar rotation':'Pause calendar rotation'} onClick={()=>setPaused(value=>!value)}>{paused?<Play/>:<Pause/>}</button></footer>
    </>:<div className="empty-message">{agenda?'No events today.':'Calendar available when connected.'}</div>}
    {detail&&<div className="agenda-detail-shade" onClick={dismiss}><section className="agenda-detail" role="dialog" aria-modal="true" aria-label="Event details" style={style(detail)} onClick={event=>event.stopPropagation()} onKeyDown={event=>{if(event.key==='Escape')dismiss();if(event.key==='Tab'){event.preventDefault();close.current?.focus();}}}>
      <button ref={close} aria-label="Close event details" onClick={dismiss}><X/></button><p>{detail.calendar_name||'Calendar'}</p><h2>{detail.summary}</h2><p>{detail.all_day?'All day':`${clock(detail.start)} – ${clock(detail.end)}`}</p><p>{date(detail.start)}{date(Date.parse(detail.end)-(detail.all_day?1:0))!==date(detail.start)?` – ${date(Date.parse(detail.end)-(detail.all_day?1:0))}`:''}</p>{detail.location&&<p>{detail.location}</p>}
    </section></div>}
  </main>;
}
