import {useEffect,useState} from "react";
import {BreakerGame,SnakeGame,RallyGame} from "./classics";
import {restoreGame,saveGame} from "./gameCheckpoint";
import {GameFrame} from "./GameFrame";
const saved:Partial<Record<"snake"|"breaker"|"rally",SnakeGame|BreakerGame|RallyGame>>={};
type SceneProps={kind:"snake"|"breaker"|"rally";pixel:boolean};
export function ClassicScene(props:SceneProps){return <ClassicRun key={props.kind} {...props}/>;}
function ClassicRun({kind,pixel}:SceneProps){
  const [game]=useState(()=>saved[kind] ||= restoreGame(kind,kind==="snake"?new SnakeGame():kind==="rally"?new RallyGame():new BreakerGame()));
  const [,redraw]=useState(0);
  useEffect(()=>{
    const save=()=>saveGame(kind,game),timer=window.setInterval(save,10000);
    window.addEventListener("pagehide",save);
    return ()=>{clearInterval(timer);window.removeEventListener("pagehide",save);save();};
  },[kind,game]);
  useEffect(()=>{
    if(matchMedia("(prefers-reduced-motion: reduce)").matches)return;
    let last=performance.now();
    let frame=0;
    const animate=(now:number)=>{const dt=Math.min(.05,(now-last)/1000);last=now;if(!document.hidden){if(game instanceof SnakeGame)game.advance(dt);else game.step(dt);redraw(n=>n+1);}frame=requestAnimationFrame(animate);};
    frame=requestAnimationFrame(animate);
    return ()=>cancelAnimationFrame(frame);
  },[game]);
  // Pixel-shaped sprites keep their geometry, but translate fluidly between grid positions.
  const snap=(n:number)=>n;
  return <GameFrame ratio={pixel?(kind==="snake"?32/20:35/23):(kind==="snake"?648/408:706/466)} grid={kind==="snake"?[32,20]:[35,23]}
    score={game instanceof RallyGame?`${game.score[0]} – ${game.score[1]}`:String(game.score).padStart(3,"0")}
    detail={game instanceof SnakeGame?`BEST ${game.best}`:game instanceof BreakerGame?`LEVEL ${game.level}`:undefined}>
    <svg className="kinetic-scene" viewBox={pixel?(kind==="snake"?"30 40 640 400":"0 0 700 460"):(kind==="snake"?"26 36 648 408":"-3 -3 706 466")} role="img" aria-label={kind==="snake"?"Snake seeks apples, avoids its body and grows its score":kind==="rally"?"Two computer-controlled paddles compete in Pong":"An automatic paddle returns a ball through scored bricks"}>
    {/* Mark collision walls only: open edges remain visibly open for a loss. */}
    {kind==="snake" ? <rect x="29" y="39" width="642" height="402" className="game-boundary"/> :
      <path d={kind==="rally"?"M0 0H700M0 460H700":"M0 460V0H700V460"} className="game-boundary"/>}
    {game instanceof SnakeGame ? <>
      {game.food>=0 && <g transform={`translate(${30+game.route[game.food][0]*20} ${40+game.route[game.food][1]*20})`}><path d={pixel?"M4 4h12v4h4v8h-4v4H4v-4H0V8h4Z":"M10 6C2 0-3 12 3 18Q7 22 10 19Q15 22 18 16C23 6 15 1 10 6Z"} className="ball ball-2"/><path d="M8 4V0h8v4Z" className="ball ball-4"/></g>}
      {game.visualBody().map(([x,y],i)=><rect key={i} x={30+x*20} y={40+y*20} width="20" height="20" rx={pixel?0:4} className={i===0?"rally-ball":"ball ball-0"} opacity={1-i/game.body.length*.6}/>)}
    </> : game instanceof RallyGame ? <>
      <path d="M350 20V440" stroke="currentColor" strokeOpacity=".15" strokeWidth="4" strokeDasharray="8 12"/>
      <rect x="33" y={snap(game.left-42)} width="12" height="84" className="ball ball-0"/><rect x="655" y={snap(game.right-42)} width="12" height="84" className="ball ball-1"/>
      <rect x={snap(game.x-10)} y={snap(game.y-10)} width="20" height="20" rx={pixel?0:3} className="rally-ball"/>
    </> : <>
      {game.bricks.map((alive,i)=>alive && <rect key={i} x={32+i%10*64} y={40+Math.floor(i/10)*28} width="60" height="20" rx={pixel?0:4} className={`ball ball-${Math.floor(i/10)%5}`}/>)}
      <rect x={snap(game.paddle-52)} y="420" width="104" height="12" rx={pixel?0:6} className="ball ball-0"/>
      {pixel?<rect x={snap(game.x-8)} y={snap(game.y-8)} width="16" height="16" className="rally-ball"/>:<circle cx={game.x} cy={game.y} r="8" className="rally-ball"/>}
    </>}
  </svg></GameFrame>;
}
