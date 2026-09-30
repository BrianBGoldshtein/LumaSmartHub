import type {CSSProperties,ReactNode} from "react";

// One physical-size score rail, outside the playfield, for every game/theme.
export function GameFrame({score,detail,ratio,children,variant,grid=[35,23]}:{score:ReactNode;detail?:ReactNode;ratio:number;children:ReactNode;variant?:"blocks"|"invaders";grid?:[number,number]}){
  return <div className={`game-frame${variant?` game-frame-${variant}`:""}`} style={{"--game-ratio":ratio,"--game-columns":grid[0],"--game-rows":grid[1]} as CSSProperties}>
    <div className="game-hud"><strong aria-label="Score">{score}</strong>{detail && <span>{detail}</span>}</div>
    <div className="game-field">{children}</div>
  </div>;
}
