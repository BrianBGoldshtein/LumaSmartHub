import test from 'node:test';
import assert from 'node:assert/strict';
import {extraPreferences,extraPatch,precipitationLabel} from '../src/weatherState.ts';

test('unknown precipitation is never presented as zero',()=>{
  for(const value of [null,undefined,NaN,Infinity,-1,101])assert.equal(precipitationLabel(value),'—');
  assert.equal(precipitationLabel(0),'0%');
  assert.equal(precipitationLabel(55),'55%');
});
test('extras remain optional and saves are scoped to the selected feature',()=>{
  const preferences=extraPreferences();
  assert.equal(preferences.weather_nudges_enabled,false);
  assert.deepEqual(extraPatch('timer',preferences),{timer_focus_minutes:25,timer_break_minutes:5});
  assert.deepEqual(extraPatch('weather',preferences),{weather_nudges_enabled:false,weather_rain_percent:50,weather_gust_mph:25,weather_hot_f:90,weather_cold_f:45});
});
test('saved preferences restore and invalid thresholds cannot save',()=>{
  assert.equal(extraPreferences({weather_cold_f:-10}).weather_cold_f,'-10');
  for(const changes of [{weather_rain_percent:''},{weather_gust_mph:'3'},{weather_hot_f:'45'},{weather_hot_f:'90.5'},{weather_cold_f:'1e2'}]){
    assert.throws(()=>extraPatch('weather',{...extraPreferences(),...changes}));
  }
});
