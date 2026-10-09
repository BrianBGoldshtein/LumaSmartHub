/** Wall only. One timer, restored immediately by actual mouse activity. */
export function installIdleCursor(surface: EventTarget, root: {classList: {add(name:string):void;remove(name:string):void}},
  delay=20_000, schedule:typeof setTimeout=setTimeout, cancel:typeof clearTimeout=clearTimeout){
  let timer:ReturnType<typeof setTimeout>|undefined;
  const active=()=>{
    root.classList.remove('luma-cursor-idle');
    if(timer!==undefined)cancel(timer);
    timer=schedule(()=>{timer=undefined;root.classList.add('luma-cursor-idle');},delay);
  };
  const pointer=(event:Event)=>{
    if((event as PointerEvent).pointerType==='mouse')active();
  };
  surface.addEventListener('pointermove',pointer);
  surface.addEventListener('pointerdown',pointer);
  surface.addEventListener('wheel',active);
  active();
  return ()=>{
    if(timer!==undefined)cancel(timer);
    surface.removeEventListener('pointermove',pointer);
    surface.removeEventListener('pointerdown',pointer);
    surface.removeEventListener('wheel',active);
    root.classList.remove('luma-cursor-idle');
  };
}
