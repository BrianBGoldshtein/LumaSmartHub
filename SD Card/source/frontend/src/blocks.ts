export type Kind = "I" | "J" | "L" | "O" | "S" | "T" | "Z";
export type Board = (Kind | null)[][];
export type Piece = {kind:Kind; x:number; y:number; rotation:number};
export const COLORS: Record<Kind,string> = {I:"#38cfe4",J:"#477bea",L:"#f39a40",O:"#f6d64a",S:"#6acb62",T:"#b577df",Z:"#e96169"};
export const KINDS:Kind[] = ["I","J","L","O","S","T","Z"];
const SHAPES:Record<Kind,number[][]> = {
  I:[[0,0,0,0],[1,1,1,1],[0,0,0,0],[0,0,0,0]], J:[[1,0,0],[1,1,1],[0,0,0]],
  L:[[0,0,1],[1,1,1],[0,0,0]], O:[[1,1],[1,1]], S:[[0,1,1],[1,1,0],[0,0,0]],
  T:[[0,1,0],[1,1,1],[0,0,0]], Z:[[1,1,0],[0,1,1],[0,0,0]],
};
export const emptyBoard = ():Board => Array.from({length:20},()=>Array<Kind|null>(10).fill(null));
// Classic line clearing: occupancy matters, never piece color.
export const isClearableRow = (row:Board[number]) => row.length===10 && row.every(cell=>cell!==null);
export function shuffledBag(random= Math.random):Kind[] {
  const bag=[...KINDS];
  for(let i=bag.length-1;i>0;i--){const j=Math.floor(random()*(i+1));[bag[i],bag[j]]=[bag[j],bag[i]];}
  return bag;
}
export function cells(piece:Piece):[number,number][] {
  let matrix=SHAPES[piece.kind];
  for(let i=0;i<piece.rotation%4;i++) matrix=matrix[0].map((_,x)=>matrix.map(row=>row[x]).reverse());
  return matrix.flatMap((row,y)=>row.flatMap((cell,x)=>cell ? [[x+piece.x,y+piece.y] as [number,number]]:[]));
}
export function fits(board:Board,piece:Piece) {
  return cells(piece).every(([x,y])=>x>=0 && x<10 && y<20 && (y<0 || board[y][x]===null));
}
// Clockwise SRS kick offsets, with screen coordinates (positive Y points down).
const JLSTZ = [[[0,0],[-1,0],[-1,-1],[0,2],[-1,2]],[[0,0],[1,0],[1,1],[0,-2],[1,-2]],[[0,0],[1,0],[1,-1],[0,2],[1,2]],[[0,0],[-1,0],[-1,1],[0,-2],[-1,-2]]];
const IKICKS = [[[0,0],[-2,0],[1,0],[-2,1],[1,-2]],[[0,0],[-1,0],[2,0],[-1,-2],[2,1]],[[0,0],[2,0],[-1,0],[2,-1],[-1,2]],[[0,0],[1,0],[-2,0],[1,2],[-2,-1]]];
export function rotate(board:Board,piece:Piece):Piece {
  if(piece.kind==="O") return piece;
  for(const [dx,dy] of (piece.kind==="I" ? IKICKS : JLSTZ)[piece.rotation]) {
    const rotated={...piece,rotation:(piece.rotation+1)%4,x:piece.x+dx,y:piece.y+dy};
    if(fits(board,rotated)) return rotated;
  }
  return piece;
}
export function landing(board:Board,piece:Piece):Piece {
  let result={...piece};
  while(fits(board,{...result,y:result.y+1})) result={...result,y:result.y+1};
  return result;
}
export function lock(board:Board,piece:Piece):{board:Board;rows:number[];topOut:boolean} {
  const next=board.map(row=>[...row]);
  const occupied=cells(piece);
  if(!fits(board,piece) || occupied.some(([,y])=>y<0)) return {board:next,rows:[],topOut:true};
  occupied.forEach(([x,y])=>{next[y][x]=piece.kind;});
  return {board:next,rows:next.flatMap((row,y)=>isClearableRow(row)?[y]:[]),topOut:false};
}
export function clearRows(board:Board):Board {
  const kept=board.filter(row=>!isClearableRow(row));
  return [...Array.from({length:20-kept.length},()=>Array<Kind|null>(10).fill(null)),...kept.map(row=>[...row])];
}
function score(board:Board,clears:number) {
  const heights=Array.from({length:10},(_,x)=>{const top=board.findIndex(row=>row[x]!==null);return top<0?0:20-top;});
  let holes=0;
  for(let x=0;x<10;x++) for(let y=20-heights[x];y<20;y++) if(board[y][x]===null) holes++;
  const bumps=heights.slice(1).reduce((n,h,x)=>n+Math.abs(h-heights[x]),0);
  return clears*40-heights.reduce((a,b)=>a+b,0)*.5-holes*9-bumps*.5-Math.max(...heights)*.4;
}
function bestTarget(board:Board,active:Piece) {
  let best={x:active.x,rotation:active.rotation,value:-Infinity};
  for(let rotation=0;rotation<(active.kind==="O"?1:4);rotation++) for(let x=-3;x<10;x++) {
    const candidate={...active,x,rotation};
    if(!fits(board,candidate)) continue;
    const result=lock(board,landing(board,candidate));
    if(result.topOut) continue;
    const value=score(clearRows(result.board),result.rows.length);
    if(value>best.value) best={x,rotation,value};
  }
  return best;
}
export class BlocksGame {
  pieceId=0;decisionTicks=0;fallProgress=0;
  board=emptyBoard(); queue:Kind[]=[]; active:Piece; lines=0; points=0; cleared:number[]=[];
  phase:"move"|"fall"|"lock"|"clear"|"over"="move"; ticks=0; target:{x:number;rotation:number;value:number};
  random:()=>number;
  constructor(random=Math.random) {this.random=random;this.refill();this.active=this.spawn();this.target=bestTarget(this.board,this.active);this.decisionTicks=2+Math.floor(this.random()*3);}
  refill() {while(this.queue.length<7) this.queue.push(...shuffledBag(this.random));}
  spawn():Piece {this.refill();const kind=this.queue.shift()!;return {kind,x:kind==="O"?4:3,y:0,rotation:0};}
  next() {this.pieceId++;this.fallProgress=0;this.active=this.spawn();this.phase=fits(this.board,this.active)?"move":"over";this.ticks=0;this.target=bestTarget(this.board,this.active);this.decisionTicks=2+Math.floor(this.random()*3);}
  // Start at the former 22,000-point pace (2.5x). Keep the same absolute
  // score slope and 18,000-point ramp span; do not multiply the ramp itself.
  speedMultiplier() {return Math.min(4,2.5+this.points/12000);}
  visualY() {return Math.min(this.active.y+this.fallProgress,landing(this.board,this.active).y);}
  private descend(distance:number) {
    this.fallProgress+=distance;
    while(this.fallProgress>=1){
      if(!fits(this.board,{...this.active,y:this.active.y+1})){this.fallProgress=0;return false;}
      this.active.y++;this.fallProgress-=1;
    }
    if(!fits(this.board,{...this.active,y:this.active.y+1})){this.fallProgress=0;return false;}
    return true;
  }
  step() {
    if(this.phase==="over") {if(++this.ticks>20){this.board=emptyBoard();this.lines=0;this.points=0;this.next();}return;}
    if(this.phase==="clear") {if(++this.ticks>=4){this.board=clearRows(this.board);this.cleared=[];this.next();}return;}
    if(this.phase==="move") {
      // Gentle drift while thinking/steering (~2.37 cells/s at score zero).
      // Gravity remains real: a late decision can run out of vertical room.
      if(!this.descend(.09*this.speedMultiplier())){this.phase="lock";this.ticks=0;return;}
      // 190–380 ms to inspect a new piece, independent of score.
      if(this.decisionTicks>0){this.decisionTicks--;return;}
      if(this.active.rotation!==this.target.rotation){const rotated=rotate(this.board,this.active);if(rotated!==this.active){this.active=rotated;this.decisionTicks=this.random()<.35?1:0;return;}}
      const dx=Math.sign(this.target.x-this.active.x);
      if(dx && fits(this.board,{...this.active,x:this.active.x+dx})){this.active.x+=dx;this.decisionTicks=this.random()<.35?1:0;return;}
      this.phase="fall";return; // Drift already consumed this tick; never double gravity at handoff.
    }
    // A small post-decision lift: ~1.17x drift (~2.76 cells/s at score zero).
    if(this.phase!=="lock" && this.descend(.105*this.speedMultiplier())){this.phase="fall";this.ticks=0;return;}
    this.phase="lock";
    if(++this.ticks<4) return;
    const result=lock(this.board,this.active);
    if(result.topOut){this.phase="over";this.ticks=0;return;}
    this.board=result.board;this.cleared=result.rows;
    // Legacy color-match saves can contain more than four already-full rows.
    this.lines+=result.rows.length;this.points+=[0,100,300,500,800][Math.min(4,result.rows.length)];
    if(result.rows.length){this.phase="clear";this.ticks=0;}else this.next();
  }
}
