export const sceneKeys=['morning','night','arrive','away'] as const;
export type SceneKey=typeof sceneKeys[number];
export type SceneAction={device:'purifier';action:string;value:boolean|number|string|null;binding:string};
export type SceneDefinition={enabled:boolean;automatic:boolean;actions:SceneAction[];needs_review?:boolean};
export type SceneDevice={id:SceneAction['device'];name:string;override_active:boolean;actions:(SceneAction&{label:string})[]};
export type SceneRun={id:string;scene:SceneKey;source:string;at:string;finished:boolean;interrupted:boolean;steps:{action:SceneAction;status:string}[]};
export type RemoteScenePolicy={revision:string;enabled:boolean;recovery_error:boolean;scenes:Record<SceneKey,{allowed:boolean;needs_review:boolean}>};
export type SceneConfig={revision:string;definitions:Record<SceneKey,SceneDefinition>;devices:SceneDevice[];runs:SceneRun[];busy:boolean;recovery_error:boolean;remote_control:boolean;remote:RemoteScenePolicy;clock_trusted:boolean;calendar_ready:boolean;phone_configured:boolean};
export const sceneLabels:Record<SceneKey,string>={morning:'Morning',night:'Night',arrive:'Arrive',away:'Away'};
export const automaticLabels:Record<SceneKey,string>={morning:'When a scheduled Sleep event ends',night:'When a scheduled Sleep event begins',arrive:'After my paired phone is nearby for 30 seconds',away:'After my paired phone is disconnected for 3 minutes'};
export function emptyScenes():SceneConfig{
  const blank=():SceneDefinition=>({enabled:false,automatic:false,actions:[]});
  const off=()=>({allowed:false,needs_review:false});
  return {revision:'',definitions:{morning:blank(),night:blank(),arrive:blank(),away:blank()},
    devices:[],runs:[],busy:false,recovery_error:false,remote_control:false,
    remote:{revision:'',enabled:false,recovery_error:false,scenes:{morning:off(),night:off(),arrive:off(),away:off()}},
    clock_trusted:false,calendar_ready:false,phone_configured:false};
}
export function sceneDraft(value:SceneDefinition):SceneDefinition{return {enabled:value.enabled,automatic:value.automatic,actions:value.actions.map(item=>({...item}))};}
export function remoteReauthorizationReady(config:SceneConfig,selected:SceneKey[]):boolean{
  return selected.some(key=>config.remote.scenes[key].needs_review&&config.definitions[key].enabled&&config.definitions[key].actions.length>0&&!config.definitions[key].needs_review);
}
export function actionLabel(item:SceneAction,devices:SceneDevice[]):string{
  const device=devices.find(row=>row.id===item.device),choice=device?.actions.find(row=>row.action===item.action&&row.value===item.value&&row.binding===item.binding);
  const name=device?.name||'Purifier';
  return `${name} · ${choice?.label||`${item.action.replaceAll('_',' ')}${item.value===null?'':` · ${item.value}`} · review needed`}`;
}
export function resultLabel(value:string):string{return ({confirmed:'Confirmed by device',unconfirmed:'Unconfirmed · check device',unknown:'Outcome unknown · do not retry blindly',not_started:'Not run',not_sent:'Not sent',unavailable:'Unavailable · not queued',skipped_override:'Skipped · manual override',cancelled:'Cancelled',rejected:'Device rejected command'} as Record<string,string>)[value]||'Outcome unavailable';}
export function sampleScenes():SceneConfig{
  const config=emptyScenes();config.clock_trusted=true;config.calendar_ready=true;config.phone_configured=true;config.revision='sample';config.remote.revision='sample-remote';
  config.devices=[{id:'purifier',name:'Bedroom purifier',override_active:false,actions:[
    {device:'purifier',action:'power',value:false,binding:'sample',label:'Off'},
    {device:'purifier',action:'mode',value:'sleep',binding:'sample',label:'Sleep mode · may turn on'},
  ]}];return config;
}
