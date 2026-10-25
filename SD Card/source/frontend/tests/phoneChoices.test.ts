import test from 'node:test';
import assert from 'node:assert/strict';
import {PHONE_PAGE_SIZE,phonePage,phoneSignal,type PhoneChoice} from '../src/phoneChoices.ts';
const rows:PhoneChoice[]=Array.from({length:181},(_,index)=>({path:`/phone/${index}`,name:`Phone ${index}`,
  address:`AA:BB:CC:DD:${Math.floor(index/256).toString(16).padStart(2,'0')}:${(index%256).toString(16).padStart(2,'0')}`,
  rssi:-30-index%70}));

test('all crowded scan rows are reachable across bounded pages in backend order',()=>{
  const seen:PhoneChoice[]=[];
  for(let page=0;page<phonePage(rows,'',0).pages;page++){
    const result=phonePage(rows,'',page);assert.ok(result.rows.length<=PHONE_PAGE_SIZE);seen.push(...result.rows);
  }
  assert.deepEqual(seen,rows);assert.equal(new Set(seen.map(r=>r.path)).size,181);
});
test('search reaches a phone past old row 40, preserves exact identity and matches case/address',()=>{
  assert.deepEqual(phonePage(rows,'pHoNe 180',0).rows,[rows[180]]);
  assert.deepEqual(phonePage(rows,'aabbccdd00b4',0).rows,[rows[180]]);
  assert.deepEqual(phonePage(rows,'AA-BB-CC-DD-00-B4',0).rows,[rows[180]]);
});
test('accent-insensitive names and unidentified devices are searchable, never hidden by default',()=>{
  const values=[{path:'/emilie',name:'Émilie’s iPhone',address:'11:22:33:44:55:66'},
    {path:'/anonymous',name:'AABBCCDDEEFF',address:'AA:BB:CC:DD:EE:FF'}];
  assert.equal(phonePage(values,'EMILIE',0).rows[0].path,'/emilie');
  assert.equal(phonePage(values,'',0).total,2);
  assert.equal(phonePage(values,'DDEEFF',0).rows[0].path,'/anonymous');
});
test('shrinking live results and invalid page indexes clamp safely',()=>{
  assert.deepEqual(phonePage(rows,'Phone 180',30).rows,[rows[180]]);
  for(const page of [-1,Infinity,NaN])assert.equal(phonePage(rows,'',page).index,0);
  assert.deepEqual(phonePage([],'missing',12),{rows:[],total:0,pages:1,index:0,start:0,end:0});
  assert.equal(phonePage(rows,'NOT HERE',0).total,0);
});
test('signal labels never pretend missing/invalid readings are proximity measurements',()=>{
  assert.equal(phoneSignal(-40),'Strong · -40 dBm');assert.equal(phoneSignal(-68),'Fair · -68 dBm');
  assert.equal(phoneSignal(-90),'Weak · -90 dBm');assert.equal(phoneSignal(0),'Strong · 0 dBm');
  for(const value of [undefined,null,127,NaN,-128,2.5])assert.equal(phoneSignal(value),'Signal unavailable');
});
