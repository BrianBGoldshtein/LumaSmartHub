/** Wall only. Layout/hover refreshes are not physical mouse movement. */
export function installIdleCursor(surface: EventTarget, root: {classList: {add(name:string):void;remove(name:string):void}},
  delay=20_000, schedule:typeof setTimeout=setTimeout, cancel:typeof clearTimeout=clearTimeout,
  changed:(idle:boolean)=>void=()=>{}){
  let timer:ReturnType<typeof setTimeout>|undefined;
  let hidden=false;
  let position:{x:number;y:number}|undefined;
  const active=()=>{
    root.classList.remove('luma-cursor-idle');
    if(hidden){hidden=false;changed(false);}
    if(timer!==undefined)cancel(timer);
    timer=schedule(()=>{timer=undefined;hidden=true;root.classList.add('luma-cursor-idle');changed(true);},delay);
  };
  const move=(event:Event)=>{
    const mouse=event as PointerEvent;
    if(mouse.pointerType!=='mouse')return;
    // Chromium can refresh hover after a carousel/layout change with the same
    // coordinates. Those events must not keep a stationary cursor alive.
    const x=mouse.screenX,y=mouse.screenY;
    if(!Number.isFinite(x)||!Number.isFinite(y))return;
    // Ignore the bridge's reversible 1/256-pixel cursor-image refresh as well
    // as exact duplicates. Real motion accumulates from the last position.
    if(position&&Math.abs(position.x-x)<=1/128&&Math.abs(position.y-y)<=1/128)return;
    const known=position!==undefined;
    position={x,y};
    if(known||(Math.abs(mouse.movementX)>1/128&&Number.isFinite(mouse.movementX))||(Math.abs(mouse.movementY)>1/128&&Number.isFinite(mouse.movementY)))active();
  };
  const down=(event:Event)=>{if((event as PointerEvent).pointerType==='mouse')active();};
  // Capture still sees movement when a dialog/canvas stops bubbling.
  surface.addEventListener('pointermove',move,true);
  surface.addEventListener('pointerdown',down,true);
  surface.addEventListener('wheel',active,true);
  active();
  return ()=>{
    if(timer!==undefined)cancel(timer);
    surface.removeEventListener('pointermove',move,true);
    surface.removeEventListener('pointerdown',down,true);
    surface.removeEventListener('wheel',active,true);
    root.classList.remove('luma-cursor-idle');
  };
}
