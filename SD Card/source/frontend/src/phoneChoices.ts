export type PhoneChoice={path:string;name:string;address:string;paired?:boolean;trusted?:boolean;named?:boolean;rssi?:number|null};
export const PHONE_PAGE_SIZE=6;
const normalized=(value:string)=>value.normalize('NFKD').replace(/\p{M}/gu,'').toLowerCase();

export function phonePage(devices:PhoneChoice[],query:string,page:number){
  const text=normalized(query.trim()),address=text.replace(/[\s:-]/g,'');
  const addressQuery=!!address&&/^[a-f0-9]+$/.test(address);
  // Preserve the authoritative backend order. Never filter anonymous devices
  // unless the user explicitly searches; every result remains reachable.
  const matches=devices.filter(device=>!text||normalized(device.name).includes(text)||
    normalized(device.address).includes(text)||(addressQuery&&device.address.replace(/:/g,'').toLowerCase().includes(address)));
  const pages=Math.max(1,Math.ceil(matches.length/PHONE_PAGE_SIZE));
  const index=Math.min(pages-1,Math.max(0,Number.isFinite(page)?Math.floor(page):0));
  return {rows:matches.slice(index*PHONE_PAGE_SIZE,(index+1)*PHONE_PAGE_SIZE),total:matches.length,
    pages,index,start:matches.length?index*PHONE_PAGE_SIZE+1:0,end:Math.min(matches.length,(index+1)*PHONE_PAGE_SIZE)};
}

export function phoneSignal(rssi:PhoneChoice['rssi']){
  if(typeof rssi!=='number'||!Number.isInteger(rssi)||rssi < -127||rssi > 20)return 'Signal unavailable';
  return `${rssi>=-60?'Strong':rssi>=-75?'Fair':'Weak'} · ${rssi} dBm`;
}
