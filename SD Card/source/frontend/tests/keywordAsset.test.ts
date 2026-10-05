import test from 'node:test';
import assert from 'node:assert/strict';
import {keywordAssetCopy,keywordDownloadPercent,type KeywordAssetState} from '../src/keywordAssetState.ts';

const state:KeywordAssetState={phase:'not_installed',asset_available:false,job_active:false,
  runtime_supported:true,error:null,downloaded_bytes:0,total_bytes:0,model_id:'test',asset_version:'0.2.9'};

test('wake model UI never equates installed files with owner/microphone acceptance',()=>{
  assert.match(keywordAssetCopy({...state,phase:'ready',asset_available:true}),/still need a wake check/);
  assert.match(keywordAssetCopy({...state,phase:'installing',job_active:true}),/Installing and testing/);
  assert.match(keywordAssetCopy({...state,phase:'recovering',job_active:true}),/Recovering/);
  assert.match(keywordAssetCopy({...state,runtime_supported:false}),/not this preview/);
  assert.match(keywordAssetCopy(undefined),/Checking/);
});

test('fixed error messages cannot echo arbitrary remote/private error data',()=>{
  assert.match(keywordAssetCopy({...state,error:'keyword_recovery_required'}),/Do not erase/);
  assert.match(keywordAssetCopy({...state,error:'keyword_release_missing'}),/not attached/);
  const unknown=keywordAssetCopy({...state,error:'secret@example.com /private/path'});
  assert.doesNotMatch(unknown,/secret|private\/path/);
  assert.match(unknown,/Nothing was activated/);
});

test('download progress is bounded and only shown for an active download',()=>{
  const downloading={...state,job_active:true,phase:'downloading',total_bytes:1000,downloaded_bytes:250};
  assert.equal(keywordDownloadPercent(downloading),25);
  assert.equal(keywordDownloadPercent({...downloading,downloaded_bytes:2000}),100);
  for(const next of [state,{...downloading,job_active:false},{...downloading,total_bytes:0},
    {...downloading,downloaded_bytes:-1},{...downloading,total_bytes:Infinity},
    {...downloading,downloaded_bytes:NaN},{...downloading,phase:'verifying'}]){
    assert.equal(keywordDownloadPercent(next),null);
  }
});
