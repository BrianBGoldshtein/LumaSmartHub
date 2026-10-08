export type AdminStatus={configured:boolean;unlocked:boolean;bootstrap:boolean;expires_in_seconds:number};
export const ADMIN_NEEDED='luma-primary-admin-needed';
export function adminAccess(value:unknown):'unlock'|'bootstrap'|'locked'{
  if(!value||typeof value!=='object')return 'locked';
  const row=value as Partial<AdminStatus>;
  if(row.configured===true&&row.unlocked===true&&typeof row.expires_in_seconds==='number'
      &&Number.isFinite(row.expires_in_seconds)&&row.expires_in_seconds>0&&row.expires_in_seconds<=300)return 'unlock';
  return row.configured===false&&row.bootstrap===true?'bootstrap':'locked';
}
export function isAdminNeeded(value:unknown):value is {code:'admin_required';fresh:boolean}{
  return !!value&&typeof value==='object'&&(value as Record<string,unknown>).code==='admin_required'
    &&typeof (value as Record<string,unknown>).fresh==='boolean';
}
export function announceAdminNeeded(value:unknown){
  if(isAdminNeeded(value))window.dispatchEvent(new CustomEvent(ADMIN_NEEDED,{detail:{fresh:value.fresh}}));
}
