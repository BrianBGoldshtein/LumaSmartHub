import test from 'node:test';
import assert from 'node:assert/strict';
import {emptyScenes,sceneDraft,actionLabel,resultLabel,remoteReauthorizationReady,sampleScenes} from '../src/sceneState.ts';

test('four independent scenes start empty and disabled without remote permission',()=>{
  const config=emptyScenes();assert.equal(Object.keys(config.definitions).length,4);assert.equal(config.remote_control,false);
  for(const row of Object.values(config.definitions))assert.deepEqual(row,{enabled:false,automatic:false,actions:[]});
  config.definitions.morning.actions.push({device:'purifier',action:'power',value:false,binding:'x'});
  assert.equal(config.definitions.night.actions.length,0);
});
test('editor draft strips server review flags and never mutates saved actions',()=>{
  const row=sampleScenes().devices[0].actions[0];const saved={enabled:true,automatic:false,needs_review:true,actions:[row]};
  const copy=sceneDraft(saved);copy.actions[0].value=true;
  assert.equal(saved.actions[0].value,false);assert.equal('needs_review' in copy,false);
});
test('old device bindings require review and uncertain outcomes never imply success',()=>{
  const config=sampleScenes(),item=config.devices[0].actions[0];
  assert.equal(actionLabel(item,config.devices),'Bedroom purifier · Off');
  assert.match(actionLabel({...item,binding:'changed'},config.devices),/review needed/);
  assert.match(resultLabel('unknown'),/unknown/);assert.match(resultLabel('not_started'),/Not run/);
  assert.match(resultLabel('skipped_override'),/manual override/);
});
test('stale remote grant offers reauthorization only after its scene is locally usable',()=>{
  const config=sampleScenes(),action=config.devices[0].actions[0];
  config.remote.scenes.night.needs_review=true;
  config.definitions.night={enabled:true,automatic:false,actions:[action]};
  assert.equal(remoteReauthorizationReady(config,['night']),true);
  config.definitions.night.needs_review=true;
  assert.equal(remoteReauthorizationReady(config,['night']),false);
  config.definitions.night.needs_review=false;
  config.definitions.night.enabled=false;
  assert.equal(remoteReauthorizationReady(config,['night']),false);
  assert.equal(remoteReauthorizationReady(config,[]),false);
});
