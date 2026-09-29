import {useEffect,useState,type CSSProperties} from 'react';
import {CalendarDays,ChevronLeft,ChevronRight} from 'lucide-react';
import type {Snapshot} from './types';
import {datePages,dateColor,dateCaption,visibleDates} from './countdownState';
import './countdowns.css';

let nextDatePage=0;
export function CountdownsPage({snapshot}:{snapshot:Snapshot}){
  const [page,setPage]=useState(()=>nextDatePage),items=visibleDates(snapshot.countdowns,snapshot.privacy_redacted);
  const pages=datePages(items,page),key=items.map(item=>item.id).join('|');
  useEffect(()=>{nextDatePage=pages.index+1;},[pages.index]);
  useEffect(()=>{if(pages.count<=1)return;const timer=setInterval(()=>setPage(value=>value+1),8000);return()=>clearInterval(timer);},[key,pages.count]);
  return <main className="page focus-page countdown-page"><div className="section-heading"><h1>Dates</h1><span><CalendarDays/>{items.length}</span></div>
    <section className={`countdown-list${pages.items.length===1?' single':''}`}>{pages.items.map(item=><article className="countdown-row" key={item.id} style={{'--date-color':dateColor(item.color)} as CSSProperties}>
      <div className={`countdown-value${item.value===null?' word':String(item.value).length>3?' long-number':''}`}><strong>{item.value??item.label}</strong>{item.unit&&<span>{item.unit}</span>}</div>
      <div className="countdown-title"><h2>{item.title}</h2><p>{dateCaption(item)}</p></div>
    </article>)}{!items.length&&<div className="empty-message"><CalendarDays/><span>No dates to show.</span></div>}</section>
    {pages.count>1&&<footer className="todo-footer"><div className="todo-pagination"><button aria-label="Previous dates" onClick={()=>setPage(value=>value-1)}><ChevronLeft/></button><span>{pages.index+1} / {pages.count}</span><button aria-label="Next dates" onClick={()=>setPage(value=>value+1)}><ChevronRight/></button></div></footer>}
  </main>;
}
