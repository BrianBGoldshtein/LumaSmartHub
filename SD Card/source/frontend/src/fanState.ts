export type FanId='fan_1'|'fan_2';
export type IrDevice={id:string;name:string;serial_present:boolean;receive:boolean;send:boolean;measure_carrier:boolean;emitter_selection:boolean};
export type FanButton={key:string;label:string;kind:'absolute'|'toggle'|'relative';checks:number;scene_eligible:boolean};
export type FanReceipt={id:string;button:string;kind:'test'|'manual'|'scene';status:'unknown'|'not_sent'|'sent_unconfirmed';at:string;observed:boolean};
export type FanView={id:FanId;name:string|null;route:{device:IrDevice;emitter:number|null}|null;buttons:FanButton[];last_command:FanReceipt|null;override_until:string|null;needs_output_review:boolean};
export type FanConfig={revision:string;recovery_error:boolean;independent:boolean;fans:FanView[];remote_control:false;busy:boolean};
export const fanButtons:Omit<FanButton,'checks'|'scene_eligible'>[]=[
  {key:'power_on',label:'On',kind:'absolute'},{key:'power_off',label:'Off',kind:'absolute'},{key:'power_toggle',label:'Power toggle',kind:'toggle'},
  ...[1,2,3,4,5,6].map(n=>({key:`speed_${n}`,label:`Speed ${n}`,kind:'absolute' as const})),
  {key:'speed_up',label:'Speed up',kind:'relative'},{key:'speed_down',label:'Speed down',kind:'relative'},
  {key:'oscillation_on',label:'Oscillation on',kind:'absolute'},{key:'oscillation_off',label:'Oscillation off',kind:'absolute'},
  {key:'oscillation_toggle',label:'Oscillation toggle',kind:'toggle'},{key:'horizontal_toggle',label:'Horizontal swing',kind:'toggle'},{key:'vertical_toggle',label:'Vertical swing',kind:'toggle'},
];
export const demoAdapter:IrDevice={id:'usb-ir-'+'a'.repeat(24),name:'Sample USB IR adapter',serial_present:true,send:true,receive:true,measure_carrier:true,emitter_selection:true};
export function emptyFans():FanConfig{return {revision:'preview',recovery_error:false,independent:false,remote_control:false,busy:false,
  fans:(['fan_1','fan_2'] as FanId[]).map(id=>({id,name:null,route:null,buttons:[],last_command:null,override_until:null,needs_output_review:false}))};}
export function fanStatus(fan:FanView){
  if(!fan.route)return 'Choose an output';
  if(fan.needs_output_review)return 'Review USB output after restart';
  if(!fan.buttons.length)return 'Ready to learn buttons';
  const tested=fan.buttons.filter(button=>button.checks>0).length;
  return `${tested} of ${fan.buttons.length} buttons tested`;
}
export function pendingObservation(receipt:FanReceipt|null,now:number){return !!receipt&&receipt.kind==='test'&&receipt.status==='sent_unconfirmed'&&!receipt.observed&&now-Date.parse(receipt.at)>=0&&now-Date.parse(receipt.at)<=120000;}
export function fanOutcome(receipt:FanReceipt|null){
  return receipt?.status==='unknown'?'Last send outcome unknown · check both fans. Nothing was retried.':null;
}
export function demoEligibility(config:FanConfig){
  config.independent=config.fans.every(fan=>!!fan.route&&fan.buttons.some(button=>button.checks>0));
  for(const fan of config.fans)for(const button of fan.buttons)button.scene_eligible=config.independent&&button.kind==='absolute'&&button.checks>=2;
  return config;
}
