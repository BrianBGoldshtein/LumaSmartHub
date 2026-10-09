/** Keep the theme's preferred size unless measured digits would overflow. */
export function fitClockFont(desired:number,natural:number,available:number,step=.1):number{
  if(![desired,natural,available,step].every(Number.isFinite)||desired<=0||natural<=0||available<=0||step<=0)return desired;
  if(natural<=available)return desired;
  const fit=desired*available/natural;
  return Math.floor(fit/step)*step||fit;
}
