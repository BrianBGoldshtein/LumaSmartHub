import test from 'node:test';
import assert from 'node:assert/strict';
import {datePages,visibleDates,disconnectedDates,dateColor,dateCaption,dateCycle,sampleDates} from '../src/countdownState.ts';
test('dates paginate every item in groups of three and wrap both ways',()=>{
  const items=Array.from({length:12},(_,i)=>({...sampleDates[0],id:String(i)}));
  assert.deepEqual([0,1,2,3].flatMap(page=>datePages(items,page).items.map(item=>item.id)),items.map(item=>item.id));
  assert.equal(datePages(items,-1).index,3);assert.equal(datePages(items,4).index,0);
  assert.equal(datePages([],1).count,1);
});
test('privacy shows only deliberately public dates and safe color tokens',()=>{
  assert.deepEqual(visibleDates(sampleDates,true).map(item=>item.id),['sample-2']);
  assert.equal(visibleDates(sampleDates,false).length,3);
  assert.equal(dateColor('url(https://example.com)'),'var(--accent)');
  assert.equal(dateColor('#abcdef'),'#abcdef');
});
test('stale and removed dates never look live',()=>{
  assert.equal(dateCaption({...sampleDates[0],state:'deleted'}),'Removed from Google');
  assert.equal(dateCaption({...sampleDates[0],state:'stale'}),'Saved date · awaiting sync');
  assert.equal(dateCaption({...sampleDates[0],state:'unavailable'}),'Check Google access');
  assert.equal(dateCaption({...sampleDates[0],state:'unlinked'}),'Reconnect Google');
});
test('connection loss drops private dates and marks retained public Google dates stale',()=>{
  const input=[...sampleDates,{...sampleDates[0],id:'public-google',public:true},{...sampleDates[0],id:'deleted',public:true,state:'deleted'}];
  const result=disconnectedDates(input);
  assert.deepEqual(result.map(item=>item.id),['sample-2','public-google','deleted']);
  assert.deepEqual(result.map(item=>item.state),['ready','stale','deleted']);
  assert.equal(input[3].state,'ready');
});
test('dates join an existing cycle only while visible without mutating settings',()=>{
  const base=[{page:'home',seconds:45},{page:'weather',seconds:25}];
  assert.equal(dateCycle(base,true).length,3);assert.equal(base.length,2);
  assert.equal(dateCycle(dateCycle(base,true),true).length,3);
  assert.deepEqual(dateCycle(dateCycle(base,true),false),base);
});
