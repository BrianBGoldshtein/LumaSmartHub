export const setupSteps=["welcome","network","space","privacy","extras","calendar","phone","voice","remote","review"] as const;
export type SetupStep=typeof setupSteps[number];
export const optionalSteps:SetupStep[]=["extras","calendar","phone","voice","remote"];
export type SetupProgress={version:1;step:SetupStep;statuses:Partial<Record<SetupStep,"reviewed"|"later">>};
export function restoreSetup(value:unknown):SetupProgress {
  const raw=value && typeof value==="object"?value as Record<string,unknown>:{};
  const step=setupSteps.includes(raw.step as SetupStep)?raw.step as SetupStep:"welcome";
  const statuses:SetupProgress["statuses"]={};
  if(raw.statuses && typeof raw.statuses==="object")for(const key of setupSteps){
    const state=(raw.statuses as Record<string,unknown>)[key];
    if(state==="reviewed" || state==="later")statuses[key]=state;
  }
  return {version:1,step,statuses};
}
export function demoTransition(progress:SetupProgress,action:string,step?:SetupStep):SetupProgress {
  const next=restoreSetup(progress);
  if(action==="visit" && step)next.step=step;
  else if((action==="continue" || action==="later") && step===next.step && step!=="review"){
    if(action==="later" && !optionalSteps.includes(step))throw Error("Only optional steps can be skipped");
    next.statuses[step]=action==="later"?"later":"reviewed";
    next.step=setupSteps[setupSteps.indexOf(step)+1];
  }else if(action==="skip_optional" && optionalSteps.includes(next.step)){
    for(const key of optionalSteps.slice(optionalSteps.indexOf(next.step)))next.statuses[key]??="later";
    next.step="review";
  }else if(action==="finish" && next.step==="review")next.statuses.review="reviewed";
  else throw Error("Invalid setup transition");
  return next;
}
export const setupCopy:Record<SetupStep,{title:string;description:string;label:string}>={
  extras:{title:"Choose your extras.",description:"Optional · Start with daily rhythm. Add more whenever you like.",label:"Extras"},
  welcome:{title:"Make room for Luma.",description:"A few essentials. The rest, at your pace.",label:"Welcome"},
  network:{title:"Get connected.",description:"Choose campus Wi-Fi. You can also continue offline.",label:"Wi-Fi"},
  space:{title:"Set the scene.",description:"Your location, display and speaker. Save any changes below.",label:"Your space"},
  privacy:{title:"Private by default.",description:"Your calendar stays hidden until your nearby phone or PIN unlocks it.",label:"Privacy"},
  calendar:{title:"Your days. Your colors.",description:"Optional · Connect Google, choose agenda calendars and your Sleep schedule.",label:"Calendar"},
  phone:{title:"Your phone is the key.",description:"Optional · Pair nearby, then approve notification sharing on your iPhone.",label:"Nearby iPhone"},
  voice:{title:"Say “Hey Luma.”",description:"Optional · Check your microphone and try the guided calibration phrases.",label:"Local voice"},
  remote:{title:"A private connection.",description:"Optional · Add Siri Shortcut controls. Your calendar still needs nearby-phone or PIN access.",label:"Siri Shortcuts"},
  review:{title:"Ready for your room.",description:"Start with what’s configured. Come back for the rest whenever you like.",label:"Review"},
};
