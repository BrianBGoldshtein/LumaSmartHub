import {memo,useEffect,useState} from "react";
import {BreakerGame,SnakeGame,RallyGame} from "./classics";
import {SpaceInvadersGame} from "./spaceInvaders";
import {restoreGame,saveGame} from "./gameCheckpoint";
import {GameFrame} from "./GameFrame";
const saved:Partial<Record<"snake"|"breaker"|"rally"|"invaders",SnakeGame|BreakerGame|RallyGame|SpaceInvadersGame>>={};
const SNAKE_SUBDIVISIONS=[...Array.from({length:31},(_,i)=>`M${50+i*20} 40V440`),...Array.from({length:19},(_,i)=>`M30 ${60+i*20}H670`)].join("");
const INVADER_SUBDIVISIONS=[...Array.from({length:31},(_,i)=>`M${(i+1)*20} 0V400`),...Array.from({length:19},(_,i)=>`M0 ${(i+1)*20}H640`)].join("");
const INVADER_SHAPES=[
  "M3 2h4V0h10v2h4v4h3v9h-4v4h-4v-3h-6v3H6v-4H2V6h1z M6 8h3v3H6z M15 8h3v3h-3z",
  "M5 1h4V0h6v2h4v3h3v10h-4v4h-5v-3h-4v3H5v-4H2V5h3z M6 7h3v3H6z M15 7h3v3h-3z",
  "M4 1h5V0h6v1h5v4h2v9h-4v5h-4v-3h-4v3H6v-5H2V5h2z M6 7h3v3H6z M15 7h3v3h-3z",
  "M4 2h4V0h8v2h4v4h2v8h-3v4h-5v-3h-4v3H5v-4H2V6h2z M6 7h3v3H6z M15 7h3v3h-3z",
  "M3 2h5V0h8v2h5v4h2v8h-4v4h-4v-3h-6v3H5v-4H1V6h2z M6 7h3v3H6z M15 7h3v3h-3z",
];
// The formation moves as a single unit. Rebuild the 55 static sprites only
// when an alien is hit, not on every animation frame.
const InvaderSprites=memo(function InvaderSprites({aliveKey}:{aliveKey:string}){
  return <>{[...aliveKey].map((alive,index)=>{
    if(alive!=="1")return null;
    const row=Math.floor(index/11),column=index%11;
    return <g key={index} transform={`translate(${column*48} ${row*28})`} className="invader-sprite"><path d={INVADER_SHAPES[row]} className={`invader-row invader-row-${row}`}/></g>;
  })}</>;
});
type SceneProps={kind:"snake"|"breaker"|"rally"|"invaders";pixel:boolean};
export function ClassicScene(props:SceneProps){return <ClassicRun key={props.kind} {...props}/>;}
function ClassicRun({kind,pixel}:SceneProps){
  const [game]=useState(()=>saved[kind] ||= restoreGame(kind,kind==="snake"?new SnakeGame():kind==="rally"?new RallyGame():kind==="invaders"?new SpaceInvadersGame():new BreakerGame()));
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
  const invaders=game instanceof SpaceInvadersGame;
  return <GameFrame variant={invaders?"invaders":undefined} ratio={pixel?(kind==="snake"?32/20:invaders?32/20:35/23):(kind==="snake"?648/408:invaders?32/20:706/466)} grid={kind==="snake"||invaders?[32,20]:[35,23]}
    score={game instanceof RallyGame?`${game.score[0]} – ${game.score[1]}`:String(game.score).padStart(3,"0")}
    detail={game instanceof SnakeGame?`BEST ${game.best}`:game instanceof BreakerGame?`LEVEL ${game.level}`:invaders?`WAVE ${String(game.wave).padStart(2,"0")} · ${game.lives} LIVES`:undefined}>
    <svg className="kinetic-scene" viewBox={pixel?(kind==="snake"?"30 40 640 400":invaders?"0 0 640 400":"0 0 700 460"):(kind==="snake"?"26 36 648 408":invaders?"0 0 640 400":"-3 -3 706 466")} role="img" aria-label={kind==="snake"?"Snake seeks apples, avoids its body and grows its score":invaders?"Autonomous Space Invaders match: the ship dodges incoming fire and clears advancing waves":kind==="rally"?"Two computer-controlled paddles compete in Pong":"An automatic paddle returns a ball through scored bricks"}>
    {/* Mark collision walls only: open edges remain visibly open for a loss. */}
    {kind==="snake" ? <rect x="29" y="39" width="642" height="402" className="game-boundary"/> : invaders ? <rect x="1" y="1" width="638" height="398" className="game-boundary"/> :
      <path d={kind==="rally"?"M0 0H700M0 460H700":"M0 460V0H700V460"} className="game-boundary"/>}
    {invaders ? <>
      {pixel&&<path className="invader-subdivisions" d={INVADER_SUBDIVISIONS}/>}
      <g className="invader-fleet" transform={`translate(${game.fleetX} ${game.fleetY})`}><InvaderSprites aliveKey={game.alive.map(alive=>alive?"1":"0").join("")}/></g>
      {game.shots.map((shot,index)=><rect key={`${shot.enemy?"e":"p"}-${index}`} x={shot.x-2} y={shot.y-7} width="4" height="12" rx={pixel?0:2} className={shot.enemy?"invader-enemy-shot":"invader-player-shot"}/>)}
      <path d={`M${game.playerX-16} 374v-8h5v-5h5v-5h12v5h5v5h5v8z`} className="invader-ship"/>
      {game.phase==="redeploy"&&<text x="320" y="220" textAnchor="middle" className="invader-wave">REDEPLOYING</text>}
      {game.phase==="lost"&&<text x="320" y="220" textAnchor="middle" className="invader-loss">GAME OVER</text>}
      {game.phase==="wave"&&<text x="320" y="220" textAnchor="middle" className="invader-wave">WAVE CLEAR</text>}
    </> : game instanceof SnakeGame ? <>
      {pixel&&<path className="snake-subdivisions" d={SNAKE_SUBDIVISIONS}/>}
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
