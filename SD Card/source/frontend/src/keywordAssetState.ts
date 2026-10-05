export type KeywordAssetState={
  phase:string;asset_available:boolean;job_active:boolean;runtime_supported:boolean;
  error:string|null;downloaded_bytes:number;total_bytes:number;model_id:string;asset_version:string;
};

const errorCopy:Record<string,string>={
  keyword_release_missing:'The signed wake model is not attached to this release yet. Retry later.',
  keyword_download_failed:'The download did not complete. Check internet access and retry.',
  keyword_download_timeout:'The download took too long. The previous model was kept; retry when the connection improves.',
  keyword_storage_full:'The Pi needs at least 350 MB free to safely prepare this model.',
  keyword_recovery_required:'The wake-model files need local recovery. Do not erase the SD card; report this status.',
  keyword_runtime_unsupported:'This model requires the Luma ARM64 Python 3.13 system image.',
  keyword_signature_invalid:'The model signature could not be verified. Nothing was activated.',
  keyword_install_failed:'The model did not pass its local install check. Retry the signed download.',
  keyword_files_need_repair:'The model files are incomplete. Report this status before changing the SD card.',
};

export function keywordAssetCopy(state:KeywordAssetState|undefined):string {
  if(!state)return 'Checking the signed wake model…';
  if(state.error)return errorCopy[state.error]??'The signed wake model could not be prepared. Nothing was activated.';
  if(state.job_active){
    const phases:Record<string,string>={queued:'Wake-model preparation queued…',recovering:'Recovering an interrupted wake-model installation…',checking:'Checking the signed model release…',downloading:'Downloading the signed wake model…',verifying:'Verifying its signature and pinned files…',installing:'Installing and testing the local acoustic worker…'};
    return phases[state.phase]??'Preparing the signed wake model…';
  }
  if(state.asset_available)return 'Signed acoustic model installed · your room and voice still need a wake check.';
  if(!state.runtime_supported)return 'Model preparation is available on the Raspberry Pi, not this preview.';
  return 'The dedicated acoustic model hears the wake name independently of command transcription.';
}

export function keywordDownloadPercent(state:KeywordAssetState|undefined):number|null {
  if(!state?.job_active||state.phase!=='downloading'||!Number.isFinite(state.total_bytes)
     ||!Number.isFinite(state.downloaded_bytes)||state.total_bytes<=0||state.downloaded_bytes<0)return null;
  return Math.max(0,Math.min(100,Math.round(100*state.downloaded_bytes/state.total_bytes)));
}
