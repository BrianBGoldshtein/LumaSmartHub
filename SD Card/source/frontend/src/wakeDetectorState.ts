export type WakeMode='acoustic'|'dual_decoder'|'standard';
export type WakeDetectorStatus={mode:WakeMode;phase:'inactive'|'ready'|'waiting_asset'|'preparing_asset'|'suspended'|'failed';error:string|null};

export function wakeDetectorCopy(mode:WakeMode,status?:WakeDetectorStatus|null):string {
  if(mode==='standard')return 'More sensitive · command grammar only. Ordinary conversation is more likely to activate Luma.';
  if(mode==='dual_decoder')return 'Older protected listener · both speech decoders must spell “Hey Luma” near the start. Unfamiliar pronunciation can be missed.';
  if(!status||status.mode!==mode)return 'Phonetic listener selected · waiting for the voice service to report its state.';
  if(status.phase==='ready')return 'Phonetic listener running · checks the sounds of “Hey Luma,” not the speech decoder’s spelling.';
  if(status.phase==='waiting_asset'||status.phase==='preparing_asset')return 'Preparing the signed wake model. Voice commands wait; no more-sensitive fallback is used.';
  if(status.phase==='suspended')return 'Phonetic listener paused for the owner-voice comparison.';
  if(status.phase==='failed')return status.error==='keyword_alignment_unavailable'
    ?'The command timing check failed. Luma discarded the phrase and will retry.'
    :'The phonetic listener could not run. Luma will retry; it will not switch to a more-sensitive listener.';
  return 'Phonetic listener is starting. Wait for its running status before testing commands.';
}
