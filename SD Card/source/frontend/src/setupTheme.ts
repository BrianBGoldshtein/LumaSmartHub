import type {Theme} from "./types";
import {isRemoteSetup} from './setupTransport.ts';
import type {SettingsSection} from './settingsRoutes';
export function setupTheme(value:unknown):Theme{return value==="hearth" || value==="neon-grid"?value:"luma-glass";}
export function setupLink(demo:boolean,theme:Theme,target?:"google"|"device"|"onboarding"|"extras"|"users"|"personal",section?:SettingsSection){
  if(isRemoteSetup())return `/remote/settings.html#${target??'close'}/${theme}${section?`/${section}`:''}`;
  const query=new URLSearchParams();
  if(demo){query.set("demo","1");query.set("theme",theme);}
  if(target)query.set("setup",target);
  if(section)query.set("section",section);
  return query.size?`/?${query}`:"/";
}
