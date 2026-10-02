import test from 'node:test';
import assert from 'node:assert/strict';
import {agendaSections,upcomingAgendaSections,calendarColor,eventKey,HOUR} from '../src/agendaState.ts';
import type {CalendarEvent} from '../src/types.ts';
const at=(hour:number)=>new Date(Date.UTC(2026,8,28)+hour*3600000).toISOString();
const event=(id:string,start:number,end:number,extra={})=>({id,calendar_id:'work',summary:id,start:at(start),end:at(end),all_day:false,...extra});
const agenda=(events:CalendarEvent[])=>({date:'2026-09-28',start:at(7),end:at(23),wake:at(7),sleep:at(23),stale:false,events});
test('all timed events across every calendar share one dense time-window slide',()=>{
  const events=Array.from({length:40},(_,i)=>event(String(i),9,10,{calendar_id:`cal-${i}`}));
  for(const columns of [1,2,3]){
    const pages=agendaSections(agenda(events),columns);
    const rendered=pages.flatMap(page=>page.items.map(item=>eventKey(item.event)));
    assert.equal(new Set(rendered).size,40);assert.equal(rendered.length,40);
    const overlapping=pages.filter(page=>page.start<=Date.parse(at(9))&&page.end>Date.parse(at(9)));
    assert.equal(overlapping.length,1);
    assert.equal(overlapping[0].items.length,40);
    assert.equal(overlapping[0].dense,true);
  }
});
test('every displayed interval contains all events intersecting it without a rival partial slide',()=>{
  const events=[event('long',8,15),event('a',9,11),event('b',9.5,10),event('c',9.5,10),event('late',18,19)];
  const sections=agendaSections(agenda(events));
  const intervals=new Set<string>();
  for(const section of sections.filter(page=>page.items.length)){
    const key=`${section.start}:${section.end}`;
    assert.ok(!intervals.has(key),`duplicate partial interval ${key}`);
    intervals.add(key);
    const expected=events.filter(item=>Date.parse(item.start)<section.end&&Date.parse(item.end)>section.start).map(item=>item.id).sort();
    assert.deepEqual(section.items.map(item=>item.event.id).sort(),expected);
  }
});
test('short adjacent events never visually collide in the same lane',()=>{
  const pages=agendaSections(agenda(Array.from({length:12},(_,i)=>event(String(i),9+i/12,9+(i+1)/12))));
  for(const page of pages)for(const a of page.items)for(const b of page.items){
    if(a===b||a.column!==b.column)continue;
    assert.ok(a.top+a.height<=b.top+.00001 || b.top+b.height<=a.top+.00001);
  }
});
test('only real overlap creates a right-hand lane, including partial overlap',()=>{
  const events=[event('first',10+5/60,10+20/60),event('partial',10+15/60,10+25/60),event('next',10+25/60,10.5)];
  const section=agendaSections(agenda(events)).find(page=>page.items.some(item=>item.event.id==='first'))!;
  const [first,partial,next]=events.map(row=>section.items.find(item=>item.event.id===row.id)!);
  assert.equal(section.start,Date.parse(at(10)));
  assert.deepEqual([first.column,partial.column,next.column],[0,1,0]);
  assert.equal(first.columns,2);
  assert.equal(partial.columns,2);
  assert.equal(next.columns,1);
  assert.ok(partial.top>first.top && partial.top<first.top+first.height);
  assert.ok(Math.abs(partial.top+partial.height-next.top)<0.00001);
});
test('one-minute appointments do not invent five-minute overlaps',()=>{
  const pages=agendaSections(agenda([event('a',10+20/60,10+21/60),event('b',10+22/60,10+23/60)]));
  const section=pages.find(page=>page.items.some(item=>item.event.id==='a'))!;
  const [a,b]=section.items;
  assert.deepEqual([a.column,b.column],[0,0]);
  assert.deepEqual([a.columns,b.columns],[1,1]);
  assert.ok(a.top+a.height<b.top);
});
test('a brief event gets visual space for title-first typography',()=>{
  const pages=agendaSections(agenda([event('Short but readable',9,9.2)]));
  const page=pages.find(section=>section.items.some(item=>item.event.id==='Short but readable'))!;
  const item=page.items[0];
  assert.equal(page.start,Date.parse(at(9)));
  assert.equal(page.end,Date.parse(at(9.5)));
  assert.equal(item.top,0);
  assert.ok(item.height>=39.9 && item.height<=40.1);
});
test('nearby short appointments use regular half-hour windows without false overlap',()=>{
  const pages=agendaSections(agenda([event('first',9,9+25/60),event('next',9.5,9+50/60)]));
  const section=pages.find(page=>page.items.some(item=>item.event.id==='first'))!;
  const next=pages.find(page=>page.items.some(item=>item.event.id==='next'))!;
  assert.equal(section.start,Date.parse(at(9)));
  assert.equal(section.end,Date.parse(at(9.5)));
  assert.equal(next.start,Date.parse(at(9.5)));
  assert.equal(next.end,Date.parse(at(10)));
  assert.equal(section.items.length,1);
  assert.equal(next.items.length,1);
});
test('five-minute offsets retain exact vertical positions even at the end of a section',()=>{
  const events=[event('ten-twenty',10+20/60,10+25/60),event('ten-twenty-five',10+25/60,10+30/60),event('ten-thirty',10.5,10+35/60),event('end',12+55/60,13)];
  const pages=agendaSections(agenda(events));
  const section=pages.find(page=>page.items.some(item=>item.event.id==='ten-twenty'))!;
  assert.equal(section.start,Date.parse(at(10)));
  assert.equal(section.end,Date.parse(at(10.5)));
  const placed=events.slice(0,2).map(row=>section.items.find(item=>item.event.id===row.id)!);
  assert.ok(placed[0].top<placed[1].top);
  assert.ok(Math.abs(placed[1].top-placed[0].top-100/6)<0.001);
  assert.deepEqual(placed.map(item=>item.column),[0,0], 'sequential starts are not concurrent columns');
  const thirty=pages.find(page=>page.items.some(item=>item.event.id==='ten-thirty'))!;
  assert.equal(thirty.start,Date.parse(at(10.5)));
  assert.equal(thirty.items.find(item=>item.event.id==='ten-thirty')!.top,0);
  const late=pages.find(page=>page.items.some(item=>item.event.id==='end'))!;
  const final=late.items.find(item=>item.event.id==='end')!;
  assert.ok(Math.abs(final.top-(Date.parse(events[3].start)-late.start)/(late.end-late.start)*100)<0.001);
});
test('cross-window appointments continue and all-day items paginate without truncation',()=>{
  const events=[event('long',10,16),...Array.from({length:10},(_,i)=>event(`all-${i}`,0,24,{all_day:true}))];
  const pages=agendaSections(agenda(events));
  assert.equal(pages.flatMap(p=>p.allDay).length,10);
  assert.equal(pages.filter(p=>p.allDay.length).length,1);
  assert.equal(pages.flatMap(p=>p.items).filter(i=>i.event.id==='long').length,1);
  assert.equal(pages.find(p=>p.items.some(i=>i.event.id==='long'))?.end-Date.parse(at(10)),6*HOUR);
  assert.ok(pages.flatMap(p=>p.items).every(item=>item.top>=0&&item.top+item.height<=100.00001));
});
test('overlapping long events share one long ruler instead of duplicating across slides',()=>{
  const pages=agendaSections(agenda([event('first',9,15),event('second',12,17)]));
  const populated=pages.filter(page=>page.items.length);
  assert.equal(populated.length,1);
  assert.equal(populated[0].start,Date.parse(at(9)));
  assert.equal(populated[0].end,Date.parse(at(17)));
  assert.deepEqual(populated[0].items.map(item=>item.column),[0,1]);
});
test('many hourly events fit more hours per slide as the screen gets taller',()=>{
  const events=Array.from({length:8},(_,i)=>event(`hour-${i}`,9+i,10+i));
  const small=agendaSections(agenda(events),2,600).filter(page=>page.items.length);
  const large=agendaSections(agenda(events),2,1080).filter(page=>page.items.length);
  assert.equal(small.length,2);
  assert.equal(small[0].start,Date.parse(at(9)));
  assert.equal(small[0].end,Date.parse(at(15)));
  assert.equal(large.length,1);
  assert.equal(large[0].start,Date.parse(at(9)));
  assert.equal(large[0].end,Date.parse(at(17)));
  assert.deepEqual(large[0].items.map(item=>item.column),Array(8).fill(0));
});
test('a brief appointment still gets a short window inside a long event',()=>{
  const pages=agendaSections(agenda([event('long',9,15),event('brief',12+20/60,12+25/60)]));
  const brief=pages.find(page=>page.items.some(item=>item.event.id==='brief'))!;
  assert.equal(brief.start,Date.parse(at(12)));
  assert.equal(brief.end,Date.parse(at(12.5)));
  assert.deepEqual(brief.items.map(item=>item.event.id).sort(),['brief','long']);
});
test('one all-day item shares the first populated time window instead of taking a blank slide',()=>{
  const pages=agendaSections(agenda([event('all',0,24,{all_day:true}),event('first',9,10)]));
  assert.equal(pages.length,3);
  assert.equal(pages.filter(page=>page.allDay.length>0).length,1);
  assert.equal(pages.find(page=>page.allDay.length>0)?.items[0]?.event.id,'first');
  assert.equal(pages.flatMap(page=>page.allDay).length,1);
});
test('shared IDs on different calendars stay distinct and event colors override calendar colors',()=>{
  const a=event('same',9,10,{calendar_color:'#abcdef',event_color:'#123456'}),b={...a,calendar_id:'other'};
  assert.notEqual(eventKey(a),eventKey(b));assert.equal(calendarColor(a),'#123456');
  assert.equal(calendarColor({...a,event_color:'url(evil)'}),'var(--accent)');
});
test('empty day retains every time section and invalid ranges are rejected',()=>{
  assert.equal(agendaSections(agenda([])).length,1);
  assert.deepEqual(agendaSections({...agenda([]),end:at(6)}),[]);
});
test('a non-hour wake and sleep still produce clock-aligned ruler boundaries',()=>{
  const source={...agenda([event('near wake',8.75,9.25)]),start:at(8.75),end:at(22.5)};
  const pages=agendaSections(source);
  assert.equal(pages[0].start,Date.parse(at(8)));
  assert.equal(pages.at(-1)!.end,Date.parse(at(23)));
  assert.ok(pages.every(page=>page.start%HOUR===0||page.start%(HOUR/2)===0));
  assert.ok(pages.every(page=>page.end%HOUR===0||page.end%(HOUR/2)===0));
});
test('automatic calendar rotation at 11 PM shows now and tomorrow, never 8 AM',()=>{
  const items=[event('morning-past',8,9),event('ongoing',22,23.5),
    event('tomorrow-early',31,32),event('beyond-14h',39,40)];
  const source=agenda(items);
  const upcoming=upcomingAgendaSections(source,Date.parse(at(23)));
  const ids=upcoming.flatMap(section=>section.items.map(item=>item.event.id));
  assert.deepEqual(ids,['ongoing','tomorrow-early']);
  assert.ok(upcoming.every(section=>section.items.length || section.allDay.length));
  assert.ok(agendaSections(source).some(section=>section.items.some(item=>item.event.id==='morning-past')));
});
test('automatic calendar rotation has no empty slides when the next event is far away',()=>{
  const source=agenda([event('past',8,9),event('later',37,38)]);
  assert.deepEqual(upcomingAgendaSections(source,Date.parse(at(23))),[]);
});
