import test from 'node:test';
import assert from 'node:assert/strict';
import {departureText,departureMinutes,departurePreferences,departurePatch} from '../src/departureState.ts';
const event={key:'key',title:'Dinner',start:'2026-09-26T20:25:00Z',depart_at:'2026-09-26T20:10:00Z',prep_minutes:5,travel_minutes:10};
test('reminder countdown uses server anchor and monotonic elapsed, expires at start',()=>{
  assert.equal(departureText(event,'2026-09-26T20:00:00Z'),'Leave in 10 min');
  assert.equal(departureText(event,'2026-09-26T20:00:00Z',10*60000),'Time to leave');
  assert.equal(departureText(event,'2026-09-26T20:00:00Z',25*60000),null);
  assert.equal(departureText(event,'invalid'),null);
  assert.equal(departureText(event,'2026-09-26T20:00:00Z',-1000),'Leave in 10 min');
});
test('defaults are opt-in and validate explicit calendars plus whole minute buffers',()=>{
  const defaults=departurePreferences();assert.equal(defaults.departure_enabled,false);
  assert.deepEqual(departurePatch(defaults),{departure_enabled:false,departure_calendar_ids:[],departure_include_virtual:false,departure_prep_minutes:5,departure_travel_minutes:10});
  assert.throws(()=>departurePatch({...defaults,departure_enabled:true}));
  assert.equal(departurePatch({...defaults,departure_enabled:true,departure_calendar_ids:['work']}).departure_enabled,true);
  for(const value of ['','-1','1.5','241','abc'])assert.throws(()=>departureMinutes(value));
  assert.equal(departureMinutes('0'),0);assert.equal(departureMinutes('240'),240);
});
