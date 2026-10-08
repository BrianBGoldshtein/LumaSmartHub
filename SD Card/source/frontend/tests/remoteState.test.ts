import test from 'node:test';
import assert from 'node:assert/strict';
import {safeColor,enrollTicket,upcoming,clockText,updateOutcome} from '../src/remote/state.ts';
const origin='https://luma.example-tail.ts.net';
test('one-use enrollment accepts only this exact remote URL without query',()=>{
  assert.equal(enrollTicket(`${origin}/remote/#enroll=${'a'.repeat(43)}`,origin),'a'.repeat(43));
  for(const link of [`${origin}/remote/?secret=1#enroll=${'a'.repeat(43)}`,`https://evil.test/remote/#enroll=${'a'.repeat(43)}`,
    `${origin}/remote/else#enroll=${'a'.repeat(43)}`,`${origin}/remote/#enroll=short`])assert.equal(enrollTicket(link,origin),null);
});

test('accepted remote updates finish only with matching target and installed version',()=>{
  for(const status of [
    {state:'installing',current_version:'0.2.11',target_version:'0.3.0'},
    {state:'installed',current_version:'0.2.11',target_version:'0.3.0'},
    {state:'installed',current_version:'0.3.0',target_version:'0.2.11'},
  ])assert.equal(updateOutcome(status,'0.3.0'),null);
  assert.equal(updateOutcome({state:'installed',current_version:'0.3.0',target_version:'0.3.0'},'0.3.0'),'Luma 0.3.0 is installed.');
  assert.match(updateOutcome({state:'failed',current_version:'0.2.11',target_version:'0.3.0'},'0.3.0')!,/did not finish.*0.2.11/);
});
test('provider colors cannot inject URLs or arbitrary style values',()=>{
  assert.equal(safeColor('#Aa0088'),'#Aa0088');
  for(const value of ['url(https://evil.test)','red','var(--secret)',undefined])assert.equal(safeColor(value),'#b4e1d7');
});
test('minimal phone agenda discards ended events and preserves start-time order',()=>{
  const event=(id:string,start:string,end:string)=>({id,calendar_id:'c',summary:id,start,end,all_day:false});
  const events=[event('past','2026-10-08T09:00:00Z','2026-10-08T10:00:00Z'),event('later','2026-10-08T15:00:00Z','2026-10-08T16:00:00Z'),event('live','2026-10-08T11:00:00Z','2026-10-08T13:00:00Z')];
  assert.deepEqual(upcoming(events,'2026-10-08T12:00:00Z').map(event=>event.id),['live','later']);
  assert.equal(events[0].id,'past');assert.ok(clockText('2026-10-08T12:00:00Z','UTC').includes('12'));
});
