export type Cooling={available:boolean;mode:string;usb_power:string;qualified:boolean;probe:string;reason:string;
  on_celsius?:number;off_celsius?:number;standby_override?:boolean;fault?:boolean;fault_code?:string|null};

export function fanControls(status:Cooling|null,busy:boolean,demo:boolean,ack:boolean){
  const retest=!!status&&!status.available;
  return {
    // The backend explicitly supports reinitialization via an acknowledged
    // probe after a latched fault. "available=false" must not deadlock recovery.
    testDisabled:busy||demo||!ack||!status||!!status.standby_override||status.probe==='running',
    confirmDisabled:busy||demo||!ack||!status||!!status.standby_override||status.probe!=='confirm',
    automaticDisabled:busy||demo||!status?.available||!status.qualified||status.probe==='running',
    testLabel:retest?'Retry physical fan test':'Test five-second USB interruption',
  };
}
