export class SnakeGame {
  readonly route:[number,number][]=[];
  body:number[]=[];food=0;head=7;score=0;best=0;pause=0;won=false;
  previousBody:number[]=[];elapsed=0;moveDelay=.15;moves=0;
  private neighbors:number[][]=[];
  readonly random:()=>number;
  constructor(random=Math.random){
    this.random=random;
    for(let x=0;x<32;x++)this.route.push([x,0]);
    for(let y=1;y<20;y++)for(let i=0;i<31;i++)this.route.push([y%2?31-i:i+1,y]);
    for(let y=19;y>0;y--)this.route.push([0,y]);
    const index=new Map(this.route.map(([x,y],i)=>[`${x},${y}`,i]));
    this.neighbors=this.route.map(([x,y])=>[[x+1,y],[x,y+1],[x-1,y],[x,y-1]].map(([nx,ny])=>index.get(`${nx},${ny}`)).filter((i):i is number=>i!==undefined));
    this.body=Array.from({length:8},(_,i)=>this.head-i);this.previousBody=[...this.body];this.placeFood();
  }
  placeFood(){const free=this.route.map((_,i)=>i).filter(i=>!this.body.includes(i));this.food=free[Math.floor(this.random()*free.length)]??-1;}
  private path(start:number,target:number,body:number[]):number[]|null {
    const blocked=new Set(body.slice(0,-1));blocked.delete(start);
    const queue=[start],parents=new Map<number,number>([[start,-1]]);
    for(let cursor=0;cursor<queue.length;cursor++){
      const cell=queue[cursor];
      if(cell===target){const result:number[]=[];let at=target;while(at!==start){result.unshift(at);at=parents.get(at)!;}return result;}
      for(const next of this.neighbors[cell])if(!blocked.has(next) && !parents.has(next)){parents.set(next,cell);queue.push(next);}
    }
    return null;
  }
  private target():number|undefined {
    // Seek the apple by shortest path, but reject routes that trap the grown body.
    const apple=this.path(this.head,this.food,this.body);
    if(apple?.length){
      const projected=[...this.body];let safe=true;
      for(const cell of apple){const grows=cell===this.food;if((grows?projected:projected.slice(0,-1)).includes(cell)){safe=false;break;}projected.unshift(cell);if(!grows)projected.pop();}
      if(safe && (projected.length===640 || this.path(projected[0],projected.at(-1)!,projected)))return apple[0];
    }
    // Follow the vacating tail to buy space when an apple route is unsafe.
    const tail=this.path(this.head,this.body.at(-1)!,this.body);
    if(tail?.length && tail[0]!==this.food)return tail[0];
    return this.neighbors[this.head].find(cell=>!(cell===this.food?this.body:this.body.slice(0,-1)).includes(cell));
  }
  step(){
    this.previousBody=[...this.body];
    if(this.pause>0){if(--this.pause===0){this.head=7;if(!this.won)this.score=0;this.won=false;this.moves=0;this.body=Array.from({length:8},(_,i)=>7-i);this.previousBody=[...this.body];this.placeFood();}return;}
    if(this.body.length===640){this.won=true;this.pause=20;return;}
    let next=this.target();
    if(next!==undefined && this.moves>=12 && this.body.length>1){
      const [x,y]=this.route[this.head],[nx,ny]=this.route[this.body[1]];
      const forward=this.neighbors[this.head].find(cell=>{const [cx,cy]=this.route[cell];return cx===2*x-nx && cy===2*y-ny;});
      if(next!==forward && this.random()<.014){
        next=forward; // Occasionally react one cell too late to a turn; collisions stay real.
      }else if(this.random()<.035){
        const alternatives=this.neighbors[this.head].filter(cell=>cell!==next && !(cell===this.food?this.body:this.body.slice(0,-1)).includes(cell));
        if(alternatives.length)next=alternatives[Math.floor(this.random()*alternatives.length)];
      }
    }
    if(next===undefined || (next===this.food?this.body:this.body.slice(0,-1)).includes(next)){this.won=false;this.pause=20;return;}
    this.moves++;
    this.head=next;this.body.unshift(this.head);
    if(this.head===this.food){this.score+=10;this.best=Math.max(this.best,this.score);this.placeFood();}else this.body.pop();
  }
  advance(dt:number){
    this.elapsed+=dt;
    if(this.elapsed>=this.moveDelay){this.elapsed=0;this.step();this.moveDelay=.125+this.random()*.055+(this.random()<.06?.06:0);}
  }
  visualBody():[number,number][]{
    const fraction=this.pause?1:Math.min(1,this.elapsed/this.moveDelay);
    return this.body.map((cell,i)=>{const to=this.route[cell],from=this.route[this.previousBody[Math.min(i,this.previousBody.length-1)]??cell];return [from[0]+(to[0]-from[0])*fraction,from[1]+(to[1]-from[1])*fraction];});
  }
}
export const BREAKER_LEVEL_LIMIT=20;
const BRICK_MOTIFS=[
  {name:"steps",rows:[0,0,1,1,2,2,3,3],gap:1},
  {name:"wave",rows:[0,1,2,3,3,2,1,0],gap:1},
  {name:"lattice",rows:[0,2,4,1,3,0,2,4],gap:2},
  {name:"ribbon",rows:[0,1,2,3,4,0,1,2],gap:2},
] as const;
export const BRICK_LAYOUTS=BRICK_MOTIFS.flatMap(motif=>Array.from({length:5},(_,shift)=>`${motif.name}-${shift+1}`));
export function brickLayout(layout:number):boolean[]{
  const index=((layout%BREAKER_LEVEL_LIMIT)+BREAKER_LEVEL_LIMIT)%BREAKER_LEVEL_LIMIT;
  const motif=BRICK_MOTIFS[Math.floor(index/5)],shift=index%5;
  // Equal workload and clearance: 32 one-hit bricks, four per row, eight rows.
  // Mirror each pair around the center so no layout favors one paddle side.
  return Array.from({length:80},(_,i)=>{
    const x=i%10,y=Math.floor(i/10),pair=Math.min(x,9-x),start=(motif.rows[y]+shift)%5;
    return pair===start || pair===(start+motif.gap)%5;
  });
}
export class BreakerGame {
  x=350;y=330;vx=155;vy=-205;paddle=350;score=0;level=1;misses=0;best=0;layout=-1;
  paddleVelocity=0;paddleAim=350;
  bricks:boolean[]=[];clearedPause=0;lost=false;pendingLevel=false;
  readonly random:()=>number;
  constructor(random=Math.random){this.random=random;this.newLayout();this.serve();this.paddle=this.x;this.paddleAim=this.paddle;}
  private newLayout(){
    const previous=this.layout;
    // Random starting configuration, then visit every layout once in the run.
    this.layout=previous<0?Math.floor(this.random()*BRICK_LAYOUTS.length):(previous+1)%BRICK_LAYOUTS.length;
    this.bricks=brickLayout(this.layout);
  }
  private serve(){this.x=120+this.random()*460;this.y=330;this.vx=(this.random()<.5?-1:1)*155;this.vy=-205;}
  step(dt:number){
    if(this.clearedPause>0){
      // Let the hand settle after a miss instead of freezing a moving paddle.
      const steps=Math.ceil(dt*240),h=dt/steps;
      for(let k=0;k<steps;k++)[this.paddle,this.paddleVelocity]=smoothPaddle(this.paddle,this.paddleVelocity,this.paddle,h,280,52,648,1800,6);
      this.paddleAim=this.paddle;this.clearedPause-=dt;
      if(this.clearedPause<=0 && this.lost){this.score=0;this.level=1;this.lost=false;this.pendingLevel=false;this.newLayout();this.serve();}return;
    }
    const steps=Math.ceil(dt*240),h=dt/steps,r=8;
    for(let k=0;k<steps;k++){
      const oldX=this.x,oldY=this.y;this.x+=this.vx*h;this.y+=this.vy*h;
      if(this.x<r){this.x=r;this.vx=Math.abs(this.vx);}if(this.x>700-r){this.x=700-r;this.vx=-Math.abs(this.vx);}
      if(this.y<r){this.y=r;this.vy=Math.abs(this.vy);}
      // Follow the visible ball continuously with a short look-ahead, not an
      // exact future intercept. Damping supplies reaction lag and soft reversals.
      const target=reflect(this.x+this.vx*.12,8,692);
      // Soften abrupt aim changes after ricochets, while allowing a quicker
      // controlled response at a lower cruising-speed ceiling. Pong is separate.
      this.paddleAim+=(Math.max(52,Math.min(648,target))-this.paddleAim)*(1-Math.exp(-h/.065));
      [this.paddle,this.paddleVelocity]=smoothPaddle(this.paddle,this.paddleVelocity,this.paddleAim,h,280,52,648,1800,6);
      if(this.vy>0 && this.y+r>=420 && oldY+r<=420 && Math.abs(this.x-this.paddle)<=52+r){this.y=420-r;this.vy=-Math.abs(this.vy);}
      if(this.y>468){this.misses++;this.lost=true;this.clearedPause=1.2;break;}
      // Introduce the next wall only when the live ball is below its footprint.
      // Normal clears preserve the live ball and score; the twentieth ends the run.
      if(this.pendingLevel && this.y>292){
        if(this.level>=BREAKER_LEVEL_LIMIT){this.misses++;this.lost=true;this.pendingLevel=false;this.clearedPause=1.2;break;}
        this.level++;this.newLayout();this.pendingLevel=false;
      }
      for(let i=0;i<this.bricks.length;i++)if(this.bricks[i]){
        const x=32+(i%10)*64,y=40+Math.floor(i/10)*28;
        if(this.x+r>x && this.x-r<x+60 && this.y+r>y && this.y-r<y+20){
          this.bricks[i]=false;this.score+=10;this.best=Math.max(this.best,this.score);
          if(oldY+r<=y || oldY-r>=y+20){this.vy*=-1;this.y=oldY;}else{this.vx*=-1;this.x=oldX;}
          break;
        }
      }
      if(this.bricks.every(b=>!b))this.pendingLevel=true;
    }
  }
}

const approach=(value:number,target:number,amount:number)=>value+Math.max(-amount,Math.min(amount,target-value));
export function smoothPaddle(position:number,velocity:number,target:number,dt:number,maxSpeed:number,min:number,max:number,maxAcceleration=1200,trackingGain=5):[number,number]{
  target=Math.max(min,Math.min(max,target));
  // Matched position/velocity gains keep the unsaturated response critically damped.
  const desired=Math.max(-maxSpeed,Math.min(maxSpeed,(target-position)*trackingGain));
  velocity=approach(velocity,desired,Math.min(maxAcceleration*dt,Math.abs(desired-velocity)*4*trackingGain*dt));
  position+=velocity*dt;
  if(position<min)return [min,Math.max(0,velocity)];
  if(position>max)return [max,Math.min(0,velocity)];
  return [position,velocity];
}
const reflect=(value:number,min:number,max:number)=>{const span=max-min,t=((value-min)%(span*2)+span*2)%(span*2);return min+(t>span?2*span-t:t);};
export const PONG_TEMPO=.78;
// Keep the established paddle tempo; this small ball-only lift is the requested
// livelier rally feel and is versioned separately for checkpoint migration.
export const PONG_BALL_TEMPO=1.12;
export const PONG_TEMPO_VERSION=5;
export const PONG_MAX_SPEED=380*PONG_TEMPO*PONG_BALL_TEMPO;
const PONG_ACCELERATION=1200*PONG_TEMPO*PONG_TEMPO;
export class RallyGame {
  x=350;y=230;vx=240;vy=125;left=230;right=230;score=[0,0];rallies=0;pause=0;matchOver=false;
  leftVelocity=0;rightVelocity=0;
  shotOffset=0;reactionDelay=0;receiverSpeed=250*PONG_TEMPO;tempoVersion=PONG_TEMPO_VERSION;
  readonly random:()=>number;
  constructor(random=Math.random){this.random=random;this.serve(this.random()<.5?-1:1);}
  private prepareReturn(){
    // Commit to one placement per incoming shot, not random jitter each frame.
    this.shotOffset=(this.random()-.5)*58;
    // An occasional overambitious edge shot can genuinely miss the ball.
    if(this.random()<.06)this.shotOffset=(this.random()<.5?-1:1)*(64+this.random()*16);
    this.reactionDelay=(.055+this.random()*.09)/PONG_TEMPO;
    this.receiverSpeed=(230+this.random()*50)*PONG_TEMPO;
  }
  private serve(direction:number){
    this.x=350;this.y=150+this.random()*160;
    const angle=(this.random()<.5?-1:1)*(.25+this.random()*.4),speed=(220+this.random()*20)*PONG_TEMPO*PONG_BALL_TEMPO;
    this.vx=direction*speed*Math.cos(angle);this.vy=speed*Math.sin(angle);this.prepareReturn();
  }
  step(dt:number){
    if(this.pause>0){this.pause-=dt;if(this.pause<=0 && this.matchOver){this.score=[0,0];this.rallies=0;this.matchOver=false;}return;}
    const steps=Math.ceil(dt*240),h=dt/steps;
    for(let k=0;k<steps;k++){
      const aim=(plane:number)=>reflect(this.y+this.vy*(plane-this.x)/this.vx,10,450)+this.shotOffset;
      this.reactionDelay=Math.max(0,this.reactionDelay-h);
      // Finish the previous player's follow-through before the receiver reacts.
      // Only one paddle moves per substep; the idle player never recenters.
      if(this.vx<0){
        if(this.rightVelocity!==0)[this.right,this.rightVelocity]=settlePaddle(this.right,this.rightVelocity,h);
        else if(this.reactionDelay>0)[this.left,this.leftVelocity]=settlePaddle(this.left,this.leftVelocity,h);
        else [this.left,this.leftVelocity]=smoothPaddle(this.left,this.leftVelocity,aim(55),h,this.receiverSpeed,52,408,PONG_ACCELERATION,5*PONG_TEMPO);
      }else{
        if(this.leftVelocity!==0)[this.left,this.leftVelocity]=settlePaddle(this.left,this.leftVelocity,h);
        else if(this.reactionDelay>0)[this.right,this.rightVelocity]=settlePaddle(this.right,this.rightVelocity,h);
        else [this.right,this.rightVelocity]=smoothPaddle(this.right,this.rightVelocity,aim(645),h,this.receiverSpeed,52,408,PONG_ACCELERATION,5*PONG_TEMPO);
      }
      const oldX=this.x;this.x+=this.vx*h;this.y+=this.vy*h;
      if(this.y<10){this.y=20-this.y;this.vy=Math.abs(this.vy);}if(this.y>450){this.y=900-this.y;this.vy=-Math.abs(this.vy);}
      const hitLeft=this.vx<0 && oldX>=55 && this.x<=55 && Math.abs(this.y-this.left)<52;
      const hitRight=this.vx>0 && oldX<=645 && this.x>=645 && Math.abs(this.y-this.right)<52;
      if(hitLeft || hitRight){
        // Flat vertical faces reflect the horizontal component, not the
        // vertical one. Offset/random angle steering could flip vy and send
        // the ball back along its arrival path even on a clean face contact.
        // Preserve the established gradual speed gain/cap without changing
        // the reflected angle. Tangential paddle movement does not rotate a
        // flat, frictionless collision normal.
        const speed=Math.hypot(this.vx,this.vy),scale=Math.min(PONG_MAX_SPEED,speed*1.025)/speed;
        this.vx=-this.vx*scale;this.vy*=scale;
        // Reflect the substep's penetration too: never visibly stick to or
        // pass through the paddle before the next frame.
        this.x=2*(hitLeft?55:645)-this.x;this.rallies++;
        this.prepareReturn();
      }
      if(this.x< -10 || this.x>710){const winner=this.x<0?1:0;this.score[winner]++;this.matchOver=Math.max(...this.score)>=11 && Math.abs(this.score[0]-this.score[1])>=2;this.serve(winner===0?1:-1);this.pause=this.matchOver?3:1;break;}
    }
  }
}
function settlePaddle(position:number,velocity:number,dt:number):[number,number]{
  const next=approach(velocity,0,PONG_ACCELERATION*dt);
  return [Math.max(52,Math.min(408,position+(velocity+next)*.5*dt)),next];
}
