import test from 'node:test';
import assert from 'node:assert/strict';
import {agendaSections,calendarColor,eventKey} from '../src/agendaState.ts';
import type {CalendarEvent} from '../src/types.ts';
const at=(hour:number)=>new Date(Date.UTC(2026,8,28)+hour*3600000).toISOString();
const event=(id:string,start:number,end:number,extra={})=>({id,calendar_id:'work',summary:id,start:at(start),end:at(end),all_day:false,...extra});
const agenda=(events:CalendarEvent[])=>({date:'2026-09-28',start:at(7),end:at(23),wake:at(7),sleep:at(23),stale:false,events});
test('all timed events across every calendar survive dense timeline pagination',()=>{
  const events=Array.from({length:40},(_,i)=>event(String(i),9,10,{calendar_id:`cal-${i}`}));
  for(const columns of [1,2,3]){
    const pages=agendaSections(agenda(events),columns);
    const rendered=pages.flatMap(page=>page.items.map(item=>eventKey(item.event)));
    assert.equal(new Set(rendered).size,40);assert.equal(rendered.length,40);
    for(const page of pages)assert.ok(page.items.every(item=>item.columns<=columns));
  }
});
test('short adjacent events never visually collide in the same lane',()=>{
  const pages=agendaSections(agenda(Array.from({length:12},(_,i)=>event(String(i),9+i/12,9+(i+1)/12))));
  for(const page of pages)for(const a of page.items)for(const b of page.items){
    if(a===b||a.column!==b.column)continue;
    assert.ok(a.top+a.height<=b.top+.00001 || b.top+b.height<=a.top+.00001);
  }
});
test('cross-window appointments continue and all-day items paginate without truncation',()=>{
  const events=[event('long',10,16),...Array.from({length:10},(_,i)=>event(`all-${i}`,0,24,{all_day:true}))];
  const pages=agendaSections(agenda(events));
  assert.equal(pages.flatMap(p=>p.allDay).length,10);
  assert.equal(pages.flatMap(p=>p.items).filter(i=>i.event.id==='long').length,3);
  assert.ok(pages.flatMap(p=>p.items).every(item=>item.top>=0&&item.top+item.height<=100.00001));
});
test('shared IDs on different calendars stay distinct and event colors override calendar colors',()=>{
  const a=event('same',9,10,{calendar_color:'#abcdef',event_color:'#123456'}),b={...a,calendar_id:'other'};
  assert.notEqual(eventKey(a),eventKey(b));assert.equal(calendarColor(a),'#123456');
  assert.equal(calendarColor({...a,event_color:'url(evil)'}),'var(--accent)');
});
test('empty day retains every time section and invalid ranges are rejected',()=>{
  assert.equal(agendaSections(agenda([])).length,4);
  assert.deepEqual(agendaSections({...agenda([]),end:at(6)}),[]);
});
