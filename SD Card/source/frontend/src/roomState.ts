export type PurifierDevice={id:string;name:string;model:string};
export type PurifierCapabilities={power:boolean;speeds:number[];modes:string[];display:boolean};
export type PurifierState={power:boolean;mode:string;speed:number|null;display:boolean|null;display_setting:boolean|null;pm25:number|null;air_quality_level:number|null;filter_percent:number};
export type PurifierAction='power'|'speed'|'mode'|'display';
export type PurifierReceipt={id:string;device_id:string;action:PurifierAction;value:boolean|number|string;status:'confirmed'|'unconfirmed'|'rejected'|'not_sent';accepted:boolean|null;at:string;override_until:string};
export type PurifierView={device:PurifierDevice;health:string;fresh:boolean;reported_at:string|null;state:PurifierState|null;capabilities:PurifierCapabilities|null;last_command:PurifierReceipt|null};
export type RoomConfig={revision:string;connected:boolean;selected:PurifierDevice|null;recovery_error:boolean;purifier:PurifierView|null;remote_control:boolean};
export const emptyRoom=():RoomConfig=>({revision:'',connected:false,selected:null,recovery_error:false,purifier:null,remote_control:false});
export function purifierFresh(view:PurifierView|null,now=Date.now()):boolean{
  const at=Date.parse(view?.reported_at||'');
  return !!view?.fresh&&view.health==='ready'&&Number.isFinite(at)&&now>=at&&now-at<=300000;
}
export function purifierStatus(view:PurifierView|null,now=Date.now()):string{
  if(!view)return 'Choose a purifier';
  if(purifierFresh(view,now))return 'Reported state checked';
  return ({needs_reconnect:'Reconnect VeSync',rate_limited:'Provider limit · waiting',unconfirmed:'Command outcome unconfirmed',recovery_required:'Settings need recovery'} as Record<string,string>)[view.health] || (view.state?'Saved reading · check needed':'Reading unavailable');
}
export function commandStatus(receipt:PurifierReceipt|null):string{
  if(!receipt)return 'No command sent from Luma.';
  return ({confirmed:'Last command matched a device readback.',unconfirmed:'Last command is unconfirmed. Check the purifier before trying again.',rejected:'Last command was not accepted.',not_sent:'Last command was not sent.'})[receipt.status];
}
export function supportsPurifier(view:PurifierView|null,action:PurifierAction,value:boolean|number|string,now=Date.now()):boolean{
  if(!purifierFresh(view,now)||!view?.capabilities)return false;
  const caps=view.capabilities;
  if(action==='power'||action==='display')return typeof value==='boolean'&&caps[action]===true;
  if(action==='speed')return typeof value==='number'&&Number.isInteger(value)&&caps.speeds.includes(value);
  return typeof value==='string'&&caps.modes.includes(value);
}
export const samplePurifier:PurifierDevice={id:'purifier-aaaaaaaaaaaaaaaaaaaaaaaa',name:'Bedroom purifier',model:'Core300S'};
export function sampleRoom():RoomConfig{
  return {revision:'sample-only',connected:true,selected:{...samplePurifier},recovery_error:false,remote_control:false,
    purifier:{device:{...samplePurifier},health:'ready',fresh:true,reported_at:new Date().toISOString(),last_command:null,
      capabilities:{power:true,speeds:[1,2,3],modes:['manual','sleep','auto'],display:true},
      state:{power:true,mode:'auto',speed:1,display:true,display_setting:true,pm25:8,air_quality_level:1,filter_percent:86}}};
}
