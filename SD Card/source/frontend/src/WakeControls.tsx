import {wakeDetectorCopy,type WakeMode,type WakeDetectorStatus} from './wakeDetectorState';

export function WakeControls({mode,detector,disabled,positive,negative,onSelect}:{
  mode:WakeMode;detector?:WakeDetectorStatus|null;disabled:boolean;positive:number;negative:number;
  onSelect:(mode:WakeMode)=>void;
}){
  return <div className="voice-calibration" role="region" aria-label="Conversation protection">
    <strong>Conversation protection</strong>
    <p role="status">{wakeDetectorCopy(mode,detector)}</p>
    <p>{positive} prompted wakes · {negative} no-wake checks. Running is not the same as passing these checks.</p>
    <div className="wake-mode-choices">
      {([['acoustic','Use phonetic listener'],['dual_decoder','Use older protected listener'],
         ['standard','Use more sensitive listener']] as const).map(([choice,label])=>
        <button key={choice} aria-pressed={mode===choice} disabled={disabled||mode===choice}
          onClick={()=>onSelect(choice)}>{mode===choice?'Selected · ':''}{label}</button>)}
    </div>
    <small>Say “Hey Luma,” then your command, and pause. Test at your normal distance and repeat the no-wake call check. This does not identify your voice: a real wake spoken on a call can still activate Luma. Turn the microphone off during such calls if needed. No audio is saved.</small>
  </div>;
}
