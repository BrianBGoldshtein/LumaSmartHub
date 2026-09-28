import {useEffect,useMemo,useState} from 'react';
import {ChevronLeft,ChevronRight,TrainFront} from 'lucide-react';
import type {Snapshot} from './types';
import {ageTransit,visibleTransit} from './transitState';
import './transit.css';

let nextStop=0;
export function TransitPage({snapshot,demo=false}:{snapshot:Snapshot;demo?:boolean}){
  const [index,setIndex]=useState(()=>nextStop),[elapsed,setElapsed]=useState(0);
  const anchor=useMemo(()=>({server:Date.parse(snapshot.server_time),local:performance.now()}),[snapshot.server_time]);
  useEffect(()=>{setElapsed(0);const timer=setInterval(()=>setElapsed(performance.now()-anchor.local),1000);return()=>clearInterval(timer);},[anchor]);
  const now=anchor.server+elapsed,items=visibleTransit(snapshot.transit,snapshot.privacy_redacted),page=((index%Math.max(1,items.length))+Math.max(1,items.length))%Math.max(1,items.length);
  const current=items[page],view=current?ageTransit(current,now):null;
  useEffect(()=>{nextStop=page+1;},[page]);
  useEffect(()=>{if(items.length<2)return;const timer=setTimeout(()=>setIndex(value=>value+1),10000);return()=>clearTimeout(timer);},[index,items.length]);
  useEffect(()=>{if(demo||!current)return;const visible=()=>{void fetch('/api/v1/transit/visible',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({item_id:current.id})}).catch(()=>{});};visible();const timer=setInterval(visible,20000);return()=>{clearInterval(timer);};},[demo,current?.id]);
  return <main className="page focus-page transit-page" aria-label="Transit"><div className="section-heading"><h1>{view?.title||'Transit'}</h1><span><TrainFront/>{view?.operator||'Your stops'}</span></div>
    {view?<><header className="transit-heading"><p>Transit · {view.stop}{view.direction?` · ${view.direction}`:''}{view.state==='stale'?' · Saved times':''}</p></header>
      <section className="transit-departures" aria-label={`Departures from ${view.stop}`}>{view.departures.map((row,i)=><article className="transit-row" key={`${row.at}-${i}`}>
        <div className="transit-route">{row.route||'Transit'}</div><div className="transit-destination"><h3>{row.destination||row.direction||'Departure'}</h3><p>{row.stale?row.kind==='predicted'?'Saved prediction':'Saved schedule':row.kind==='predicted'?'Live prediction':'Scheduled'} · {new Intl.DateTimeFormat('en-US',{hour:'numeric',minute:'2-digit',timeZone:snapshot.settings.timezone}).format(new Date(row.at))}</p></div><div className={`transit-minutes${row.minutes>=100?' long-number':''}`}><strong>{row.minutes===0?'Now':row.minutes}</strong>{row.minutes>0&&<span>min</span>}</div>
      </article>)}{!view.departures.length&&<div className="empty-message"><TrainFront/><span>{view.state==='empty'?'No departures in this window.':'Departure times unavailable.'}</span></div>}</section></>:<div className="empty-message"><TrainFront/><span>No visible stops. Add one in Dates & travel.</span></div>}
    <footer className="transit-footer"><a href="https://511.org" target="_blank" rel="noreferrer">data provided by 511.org</a>{demo&&<span>Sample preview</span>}{items.length>1&&<div className="todo-pagination"><button aria-label="Previous transit stop" onClick={()=>setIndex(value=>value-1)}><ChevronLeft/></button><span>{page+1} / {items.length}</span><button aria-label="Next transit stop" onClick={()=>setIndex(value=>value+1)}><ChevronRight/></button></div>}</footer>
  </main>;
}
