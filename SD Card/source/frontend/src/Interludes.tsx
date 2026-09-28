import { useEffect, useState } from "react";
import type {CSSProperties} from "react";
import { BlocksGame, COLORS, cells, landing } from "./blocks";
import type { Kind } from "./blocks";
import type { Theme } from "./types";
import {ClassicScene} from "./ClassicScenes";
import {GameFrame} from "./GameFrame";
import {restoreGame,saveGame} from "./gameCheckpoint";
import {bob,createPendulums,stepBalls,stepPendulums} from "./physics";
import type {Ball,Pendulum} from "./physics";

export function LumaGlow() {
  return <span className="luma-glow" aria-hidden="true"><i /><i /><i /></span>;
}

// Keep the board between interludes; it advances only while visible.
let savedGame: BlocksGame | undefined;
function Tile({x,y,kind,ghost=false,flash=false}:{x:number;y:number;kind:Kind;ghost?:boolean;flash?:boolean}) {
  return <g transform={`translate(${x*20} ${y*20})`} style={{"--piece-color":`var(--game-${kind},${COLORS[kind]})`} as CSSProperties}><rect x="1" y="1" width="18" height="18" rx="1.5" className={`game-tile${ghost?" is-ghost":""}${flash?" is-clearing":""}`}/></g>;
}
function Blocks() {
  const [game] = useState(()=>savedGame ||= restoreGame("blocks",new BlocksGame()));
  const [,redraw] = useState(0);
  useEffect(()=>{
    const save=()=>saveGame("blocks",game),timer=window.setInterval(save,10000);
    window.addEventListener("pagehide",save);
    return ()=>{clearInterval(timer);window.removeEventListener("pagehide",save);save();};
  },[game]);
  useEffect(()=>{
    if(matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer=window.setInterval(()=>{game.step();redraw(n=>n+1);},95);
    return ()=>clearInterval(timer);
  },[game]);
  const live=game.phase!=="clear" && game.phase!=="over";
  const ghost=landing(game.board,game.active);
  return <GameFrame variant="blocks" ratio={15/20} score={String(game.points).padStart(3,"0")}><div className="blocks-layout"><svg className="blocks-board" viewBox="0 0 200 400" role="img" aria-label="Randomized falling blocks playing on a ten by twenty board">
    <g>
      <rect width="200" height="400" className="block-board-surface"/>
      <path className="block-cell-grid" d={[...Array.from({length:9},(_,i)=>`M${(i+1)*20} 0V400`),...Array.from({length:19},(_,i)=>`M0 ${(i+1)*20}H200`)].join("")}/>
      <path d="M0 0V400H200V0" className="game-boundary"/>
      {game.board.flatMap((row,y)=>row.map((kind,x)=>kind && <Tile key={`${x}-${y}`} x={x} y={y} kind={kind} flash={game.cleared.includes(y)}/>))}
      {live && cells(ghost).filter(([,y])=>y>=0).map(([x,y])=><Tile key={`ghost-${x}-${y}`} x={x} y={y} kind={ghost.kind} ghost/>)}
      {live && <g key={game.pieceId} className="falling-piece" style={{transform:`translate(${game.active.x*20}px, ${game.visualY()*20}px)`}}>{cells({...game.active,x:0,y:0}).filter(([,y])=>y+game.active.y>=0).map(([x,y],i)=><Tile key={i} x={x} y={y} kind={game.active.kind}/>)}</g>}
    </g>
    </svg><svg className="blocks-preview" viewBox="0 0 80 400" aria-label="Next five pieces">
    {game.queue.slice(0,5).map((kind,index)=>{
      const shape=cells({kind,x:0,y:0,rotation:0}),xs=shape.map(([x])=>x),ys=shape.map(([,y])=>y);
      const x=-Math.min(...xs)*20,y=(2+index*4-Math.min(...ys))*20;
      return <g key={index} className="next-piece" transform={`translate(${x} ${y})`}>{shape.map(([x,y])=><Tile key={`${x}-${y}`} x={x} y={y} kind={kind}/>)}</g>;
    })}
  </svg><span className="block-preview-label">NEXT</span></div></GameFrame>;
}
function PixelDisk({x,y,r,className}:{x:number;y:number;r:number;className:string}) {
  const pixels:string[]=[];
  for(let dy=-r;dy<r;dy+=4)for(let dx=-r;dx<r;dx+=4)if(Math.hypot(dx+2,dy+2)<=r)pixels.push(`M${Math.round((x+dx)/4)*4} ${Math.round((y+dy)/4)*4}h4v4h-4z`);
  return <path className={className} d={pixels.join("")}/>;
}
function Balls({pixel}:{pixel:boolean}) {
  const [balls,setBalls]=useState<Ball[]>(()=>Array.from({length:12},(_,i)=>({x:85+(i%4)*175,y:70+Math.floor(i/4)*145,vx:(i%2?1:-1)*(30+i*3),vy:35-(i%5)*14,r:28+(i%3)*11})));
  useEffect(()=>{
    if(matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    let last=performance.now();
    const timer=window.setInterval(()=>{const now=performance.now(),dt=Math.min(.05,(now-last)/1000);last=now;setBalls(previous=>stepBalls(previous,dt));},32);
    return ()=>clearInterval(timer);
  },[]);
  return <svg className="kinetic-scene balls-scene" viewBox="0 0 700 430" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Luminous colored spheres drift, bounce and collide across the screen">
    <defs><radialGradient id="orb-light" cx="30%" cy="25%" r="75%"><stop stopColor="#fff" stopOpacity=".5"/><stop offset=".4" stopColor="#fff" stopOpacity=".02"/><stop offset="1" stopColor="#000" stopOpacity=".4"/></radialGradient></defs>
    {balls.map((b,i)=>pixel ? <PixelDisk key={i} x={b.x} y={b.y} r={b.r} className={`ball ball-${i%5}`}/> : <g key={i}>{[3,2,1].map(t=><circle key={t} cx={b.x-b.vx*t*.13} cy={b.y-b.vy*t*.13} r={b.r+t*3} className={`ball ball-${i%5}`} opacity={.035}/>) }<circle cx={b.x} cy={b.y} r={b.r} className={`ball ball-${i%5}`}/><circle cx={b.x} cy={b.y} r={b.r} fill="url(#orb-light)"/></g>)}
  </svg>;
}
function gearPath(teeth:number,r:number) {
  const points:string[]=[];
  for(let t=0;t<teeth;t++)for(const [fraction,radius] of [[-.5,r-5],[-.28,r-5],[-.18,r+5],[.18,r+5],[.28,r-5]]){
    const a=(t+fraction)/teeth*Math.PI*2;points.push(`${Math.cos(a)*radius},${Math.sin(a)*radius}`);
  }
  return "M"+points.join("L")+"Z";
}
function Gears() {
  const gears=[{x:350,y:230,r:100,n:25,duration:50,direction:"normal",phase:0},...Array.from({length:6},(_,i)=>({x:350+184*Math.cos(i*Math.PI/3),y:230+184*Math.sin(i*Math.PI/3),r:84,n:21,duration:42,direction:"reverse",phase:(46/21)*i*60+180-180/21})),{x:-18,y:230,r:100,n:25,duration:50,direction:"normal",phase:0},{x:718,y:230,r:100,n:25,duration:50,direction:"normal",phase:0}];
  return <svg className="kinetic-scene gears-scene" viewBox="0 0 700 460" preserveAspectRatio="xMidYMid slice" role="img" aria-label="An immersive field of interlocking gears turns at linked speeds">
    <defs><linearGradient id="metal-light" x2="1" y2="1"><stop stopColor="#fff" stopOpacity=".25"/><stop offset=".4" stopColor="#fff" stopOpacity="0"/><stop offset="1" stopColor="#000" stopOpacity=".25"/></linearGradient></defs>
    {gears.map((g,i)=><g key={i} transform={`translate(${g.x} ${g.y})`}><g className={`gear gear-${i%3}`} style={{animationDuration:g.duration+"s",animationDirection:g.direction}}><g transform={`rotate(${g.phase})`}><path d={gearPath(g.n,g.r)}/><path d={gearPath(g.n,g.r)} fill="url(#metal-light)" className="metal-light"/><circle r={g.r*.68} className="gear-cutout"/>{[0,120,240].map(angle=><path key={angle} d={`M0 0L${g.r*.76} 0`} transform={`rotate(${angle})`} className="gear-spoke"/>)}<circle r={g.r*.17} className="gear-hub"/></g></g><circle r="5" className="gear-axle"/></g>)}
  </svg>;
}
function useTime() {
  const [time,setTime]=useState(0);
  useEffect(()=>{
    if(matchMedia("(prefers-reduced-motion: reduce)").matches)return;
    const start=performance.now();
    const timer=window.setInterval(()=>setTime((performance.now()-start)/1000),40);
    return ()=>clearInterval(timer);
  },[]);
  return time;
}
function Pendulums({pixel}:{pixel:boolean}) {
  const [pendulums,setPendulums]=useState<Pendulum[]>(()=>createPendulums());
  useEffect(()=>{
    if(matchMedia("(prefers-reduced-motion: reduce)").matches)return;
    let last=performance.now();
    const timer=window.setInterval(()=>{const now=performance.now(),dt=Math.min(.05,(now-last)/1000);last=now;setPendulums(previous=>stepPendulums(previous,dt));},32);
    return ()=>clearInterval(timer);
  },[]);
  return <svg className="kinetic-scene pendulum-scene" viewBox="60 20 580 390" preserveAspectRatio="xMidYMid slice" role="img" aria-label="Gravity-driven pendulums exchange energy through elastic collisions">
    <path d="M80 50H620" className="pendulum-rail"/>
    {pendulums.map((p,i)=>{const x=p.pivot,{x:endX,y:endY}=bob(p);
      return <g key={i}><path d={`M${x} 50L${endX} ${endY}`} className="pendulum-string"/><circle cx={x} cy="50" r="4" className="gear-hub"/>{pixel ? <PixelDisk x={endX} y={endY} r={17} className={`ball ball-${i%5}`}/> : <circle cx={endX} cy={endY} r="17" className={`ball ball-${i%5}`}/>}</g>;
    })}
  </svg>;
}
function Stars() {
  const time=useTime();
  const [stars]=useState(()=>Array.from({length:160},()=>({angle:Math.random()*Math.PI*2,offset:Math.random(),speed:.04+Math.random()*.04})));
  return <svg className="kinetic-scene stars-scene" viewBox="0 0 700 460" preserveAspectRatio="xMidYMid slice" role="img" aria-label="A gentle flight through a field of stars">
    {stars.map((star,i)=>{const z=(star.offset+time*star.speed)%1,r=z*z*430;return <rect key={i} x={Math.round((350+Math.cos(star.angle)*r)/4)*4} y={Math.round((230+Math.sin(star.angle)*r)/4)*4} width={z>.65?4:2} height={z>.65?4:2} className={`ball ball-${i%5}`} opacity={Math.min(1,z*2)}/>;})}
  </svg>;
}
function Rally({pixel}:{pixel:boolean}) {
  return <ClassicScene kind="rally" pixel={pixel}/>;
}
function Sunset() {
  return <div className="hearth-interlude" aria-hidden="true"><div className="hearth-sun"/><div className="ridge"/><div className="ridge ridge-two"/><div className="ember-field">{Array.from({length:12},(_,i)=><i key={i} style={{left:`${i*8}%`,animationDelay:`${i*-.7}s`,animationDuration:`${6+i*.4}s`}}/>)}</div></div>;
}
const scenes:Record<Theme,string[]> = {"neon-grid":["blocks","rally","snake","breaker","stars","balls"],"luma-glass":["pendulums","balls","breaker","gears","stars","rally","glow","blocks","snake"],hearth:["gears","pendulums","snake","balls","sunset","breaker","stars","blocks","rally"]};
export function AmbientVisual({theme}:{theme:Theme}) {
  const [visit]=useState(()=>{try{return Number(sessionStorage.getItem("luma-ambient-visit") || 0);}catch{return 0;}});
  const forced=new URLSearchParams(location.search).get("scene");
  const scene=forced && ["blocks","balls","gears","glow","sunset","rally","stars","pendulums","snake","breaker"].includes(forced) ? forced : scenes[theme][visit%scenes[theme].length];
  useEffect(()=>{if(!forced)try{sessionStorage.setItem("luma-ambient-visit",String(visit+1));}catch{/* Optional scene memory. */}},[visit,forced]);
  return <div className={`ambient-visual scene-${scene}${["snake","breaker","rally","blocks"].includes(scene)?" is-game":""}`} data-scene={scene}><div className="scene-light"/>{scene==="snake" || scene==="breaker"?<ClassicScene kind={scene} pixel={theme==="neon-grid"}/>:scene==="blocks"?<Blocks/>:scene==="balls"?<Balls pixel={theme==="neon-grid"}/>:scene==="gears"?<Gears/>:scene==="sunset"?<Sunset/>:scene==="pendulums"?<Pendulums pixel={theme==="neon-grid"}/>:scene==="stars"?<Stars/>:scene==="rally"?<Rally pixel={theme==="neon-grid"}/>:<div className="glass-interlude"><LumaGlow/></div>}</div>;
}
