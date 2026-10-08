import test from 'node:test';
import assert from 'node:assert/strict';
import {userGrid,synchronizedUserSections} from '../src/userPanelState.ts';
import {hourRulerTicks,HOUR,eventKey} from '../src/agendaState.ts';
import type {UserPanel,CalendarEvent} from '../src/types.ts';

const now=Date.UTC(2026,9,8,9),at=(minute:number)=>new Date(now+minute*60000).toISOString();
const event=(id:string,from:number,to:number):CalendarEvent=>({id,calendar_id:'same-calendar',summary:id,start:at(from),end:at(to),all_day:false});
const panel=(id:string,events:CalendarEvent[]):UserPanel=>({profile_id:id,nickname:id,configured:true,
  calendar:events,ongoing:[],todos:[],todo_controls:{can_update:false,stale:false},google:{authorized:true,last_synced:at(0),error:null,reconnect_required:false},
  agenda:{date:'2026-10-08',start:at(0),end:at(840),wake:null,sleep:null,stale:false,events}});

test('all five layout counts use every grid cell with no missing user or spare tile',()=>{
  for(let count=1;count<=5;count++){
    const grid=userGrid(count);
    assert.equal(grid.spans.length,count);
    assert.equal(grid.spans.reduce((a,b)=>a+b,0),grid.columns*grid.rows);
  }
  assert.deepEqual(userGrid(5),{columns:6,rows:2,spans:[2,2,2,3,3]});
  for(const bad of [0,6,-1,1.5])assert.throws(()=>userGrid(bad));
});

test('every presence combination renders everyone on exactly the same interval',()=>{
  for(let mask=0;mask<32;mask++){
    const panels=Array.from({length:5},(_,i)=>panel('person-'+i,[event('same-id',10+i*5,90+i*10)])).filter((_,i)=>mask&(1<<i));
    const sections=synchronizedUserSections(panels,now,600);
    if(!panels.length){assert.deepEqual(sections,[]);continue;}
    for(const section of sections){
      assert.equal(section.panels.length,panels.length);
      for(const own of section.panels){
        assert.equal(own.section.start,section.start);assert.equal(own.section.end,section.end);
        assert.ok(own.section.items.every(item=>item.event.profile_id===own.profile_id));
        for(const tick of hourRulerTicks(section.start,section.end))assert.equal(tick%HOUR,0);
      }
    }
    assert.equal(new Set(sections.flatMap(section=>section.panels.flatMap(own=>own.section.items.map(item=>eventKey(item.event))))).size,panels.length);
  }
});

test('exact five-minute starts and real partial overlaps survive a shared window',()=>{
  const events=[event('first',20,40),event('partial',25,50),event('next',50,60)];
  const sections=synchronizedUserSections([panel('one',events),panel('two',[event('other',30,55)])],now);
  for(const section of sections){
    const own=section.panels[0].section;
    for(const item of own.items){
      const top=Math.max(section.start,Date.parse(item.event.start));
      assert.ok(Math.abs(item.top-(top-section.start)/(section.end-section.start)*100)<.000001);
    }
    const first=own.items.find(item=>item.event.id==='first'),partial=own.items.find(item=>item.event.id==='partial');
    if(first&&partial){assert.notEqual(first.column,partial.column);assert.ok(partial.top>=first.top);}
  }
});

test('same interval includes every own overlapping event, without rotating lanes away',()=>{
  const one=panel('one',Array.from({length:12},(_,i)=>event('overlap-'+i,10,70))),two=panel('two',[event('long',0,200)]);
  for(const section of synchronizedUserSections([one,two],now)){
    for(const own of section.panels){
      const source=own.profile_id==='one'?one:two;
      const expected=source.agenda.events.filter(event=>Date.parse(event.start)<section.end&&Date.parse(event.end)>section.start).map(event=>event.id).sort();
      assert.deepEqual(own.section.items.map(item=>item.event.id).sort(),expected);
    }
  }
});
