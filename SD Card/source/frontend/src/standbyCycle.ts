import type { Page } from './types';

// Public surfaces only. Never derive this list from the owner's private cycle.
export const STANDBY_CYCLE: {page:Page;seconds:number}[] = [
  {page:'home',seconds:45},
  {page:'weather',seconds:25},
  {page:'ambient',seconds:18},
];

export function standbyPage(page:Page):'home'|'weather'|'ambient' {
  return page==='weather'||page==='ambient'?page:'home';
}
