import type {Theme} from "./types";
import {isRemoteSetup} from './setupTransport.ts';
export function setupTheme(value:unknown):Theme{return value==="hearth" || value==="neon-grid"?value:"luma-glass";}
export function setupLink(demo:boolean,theme:Theme,target?:"google"|"device"|"onboarding"|"extras"|"users"|"personal"){
  if(isRemoteSetup())return `/remote/settings.html#${target??'close'}/${theme}`;
  const query=new URLSearchParams();
  if(demo){query.set("demo","1");query.set("theme",theme);}
  if(target)query.set("setup",target);
  return query.size?`/?${query}`:"/";
}
