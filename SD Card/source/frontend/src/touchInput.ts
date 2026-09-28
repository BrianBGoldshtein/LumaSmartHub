export type KeyboardMode="text"|"digits"|"decimal";
export function validInput(value:string,mode:KeyboardMode){
  return mode==="digits"?/^[0-9]*$/.test(value):mode==="decimal"?/^-?[0-9]*\.?[0-9]*$/.test(value):!/[\u0000-\u001f\u007f]/.test(value);
}
export function editInput(value:string,key:string,start=value.length,end=start,maxLength=64,mode:KeyboardMode="text"){
  start=Math.max(0,Math.min(value.length,start));end=Math.max(start,Math.min(value.length,end));
  let next=value,caret=start;
  if(key==="Clear"){next="";caret=0;}
  else if(key==="Backspace"){
    if(start===end && start>0)start-=value.codePointAt(start-2)!>0xffff?2:1;
    next=value.slice(0,start)+value.slice(end);caret=start;
  }else{next=value.slice(0,start)+key+value.slice(end);caret=start+key.length;}
  if(next.length>maxLength || !validInput(next,mode))return {value,caret:end};
  return {value:next,caret};
}
export function coordinates(latitude:string,longitude:string){
  const lat=latitude.trim(),lon=longitude.trim();
  if(!lat && !lon)return {latitude:null,longitude:null};
  if(!lat || !lon || !Number.isFinite(Number(lat)) || !Number.isFinite(Number(lon)) || Math.abs(Number(lat))>90 || Math.abs(Number(lon))>180)throw Error("Enter a latitude from −90 to 90 and longitude from −180 to 180, or leave both blank.");
  return {latitude:Number(lat),longitude:Number(lon)};
}
