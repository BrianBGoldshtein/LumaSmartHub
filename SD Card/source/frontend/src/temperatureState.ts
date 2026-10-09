export type DeviceTemperature={celsius:number|null;status:'normal'|'warm'|'hot'|'unavailable';sampled_at:string};
export function temperatureView(reading:DeviceTemperature|null|undefined,now=Date.now()){
  const date=reading?Date.parse(reading.sampled_at):NaN;
  const value=reading?.celsius;
  if(!Number.isFinite(date)||date>now+5000||now-date>30000||typeof value!=='number'||!Number.isFinite(value)||value<=0||value>125||reading?.status==='unavailable'){
    return {value:'—',label:'Sensor unavailable',status:'unavailable'};
  }
  return {value:`${value.toFixed(1)}°C`,label:value>=80?'High · check cooling':value>=70?'Warm':'Normal',status:value>=80?'hot':value>=70?'warm':'normal'};
}
