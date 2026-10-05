import {useEffect,useState} from 'react';
import {keywordAssetCopy,keywordDownloadPercent,type KeywordAssetState} from './keywordAssetState';

async function request(action?:'prepare'|'repair'){
  const response=await fetch(`/api/v1/voice/keyword-asset${action?`/${action}`:''}`,action?{
    method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({confirmed:true}),
  }:undefined);
  const value=await response.json();
  if(!response.ok)throw Error(typeof value.detail==='string'?value.detail:'Wake-model connection unavailable.');
  return value as KeywordAssetState;
}

export function KeywordSetup({demo,disabled,onActivity}:{demo:boolean;disabled:boolean;onActivity:(busy:boolean)=>void}){
  const [state,setState]=useState<KeywordAssetState>();
  const [error,setError]=useState(''),[busy,setBusy]=useState(false);
  useEffect(()=>{onActivity(busy||!!state?.job_active);return()=>onActivity(false);},[busy,state?.job_active,onActivity]);
  useEffect(()=>{
    if(demo)return;
    let stopped=false;
    const refresh=()=>{void request().then(value=>{if(!stopped){setState(value);setError('');}}).catch(()=>{
      if(!stopped){setState(undefined);setError('Wake-model status unavailable. Check the connection to Luma.');}
    });};
    refresh();const timer=window.setInterval(refresh,state?.job_active?1500:5000);
    return()=>{stopped=true;window.clearInterval(timer);};
  },[demo,state?.job_active]);
  async function prepare(action:'prepare'|'repair'){
    setBusy(true);setError('');
    try{setState(await request(action));}
    catch(error){setError(error instanceof Error?error.message:'Wake-model preparation unavailable.');}
    finally{setBusy(false);}
  }
  const percent=keywordDownloadPercent(state);
  return <div className="voice-asset-status keyword-asset-status" role="region" aria-label="Acoustic wake model">
    <strong>Hearing “Hey Luma” · offline</strong>
    <p role="status">{demo?'Signed acoustic wake model · preview only':keywordAssetCopy(state)}</p>
    {percent!==null&&<><progress max={100} value={percent} aria-label="Wake model download"/><span> {percent}%</span></>}
    {error&&<p role="alert">{error}</p>}
    {!demo&&state?.runtime_supported&&<button disabled={disabled||busy||state.job_active}
      onClick={()=>void prepare(state.asset_available?'repair':'prepare')}>
      {state.job_active?'Preparing local wake model…':state.asset_available?'Repair signed wake model':'Prepare signed wake model'}
    </button>}
    <small>One signed download, about 46 MB. Recognition stays on this Pi. Installing a model is not proof that your microphone or pronunciation passes; it does not identify you or unlock private data.</small>
  </div>;
}
