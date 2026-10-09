import test from 'node:test';
import assert from 'node:assert/strict';
import {temperatureView} from '../src/temperatureState.ts';
import type {DeviceTemperature} from '../src/temperatureState.ts';
const now=Date.parse('2026-10-08T12:00:00Z');
const sample=(celsius:number|null=56.5):DeviceTemperature=>({celsius,status:'normal',sampled_at:new Date(now).toISOString()});
test('CPU temperature uses Celsius and legible warning labels',()=>{
  assert.deepEqual(temperatureView(sample(),now),{value:'56.5°C',label:'Normal',status:'normal'});
  assert.equal(temperatureView(sample(70),now).label,'Warm');
  assert.equal(temperatureView(sample(80),now).label,'High · check cooling');
});
test('missing, corrupt and failed readings never show zero or stale temperature',()=>{
  for(const value of [undefined,null,sample(null),sample(0),sample(-10),sample(126),sample(NaN),sample(Infinity),{...sample(),status:'unavailable' as const},{...sample(),sampled_at:'bad'}]){
    assert.equal(temperatureView(value,now).label,'Sensor unavailable');
    assert.equal(temperatureView(value,now).value,'—');
  }
});
test('old/future readings expire even without a new preview and valid readings recover',()=>{
  assert.equal(temperatureView(sample(),now+31000).status,'unavailable');
  assert.equal(temperatureView({...sample(),sampled_at:new Date(now+6000).toISOString()},now).status,'unavailable');
  assert.equal(temperatureView({...sample(),sampled_at:new Date(now+31000).toISOString()},now+31000).value,'56.5°C');
});
